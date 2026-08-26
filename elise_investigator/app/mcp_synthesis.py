from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

_ENTITY_REF_RE = re.compile(r"\b(?:automation|script)\.[A-Za-z0-9_]+\b")


def _unwrap_tool_result(value: Any) -> dict[str, Any]:
    """Return the structured payload emitted by FastMCP without inventing data."""
    if not isinstance(value, dict):
        return {}

    for key in ("structuredContent", "structured_content"):
        candidate = value.get(key)
        if isinstance(candidate, dict):
            return candidate

    content = value.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    return value


def _tool_payload(findings: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    for finding in findings:
        if finding.get("tool") != tool_name or finding.get("success") is not True:
            continue
        return _unwrap_tool_result(finding.get("result"))
    return {}


def _entity_record(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return {}

    states = data.get("states")
    if isinstance(states, dict):
        record = states.get(entity_id)
        if isinstance(record, dict):
            return record

    if data.get("entity_id") == entity_id or "state" in data:
        return data
    return {}


def _position(record: dict[str, Any]) -> int | float | None:
    attrs = record.get("attributes")
    if not isinstance(attrs, dict):
        return None
    value = attrs.get("current_position")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _friendly_name(record: dict[str, Any], entity_id: str) -> str:
    attrs = record.get("attributes")
    if isinstance(attrs, dict):
        name = attrs.get("friendly_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return entity_id


def _state_word(entity_id: str, state: str | None, position: int | float | None) -> str:
    domain = entity_id.split(".", 1)[0]
    state_text = str(state or "").strip().lower()

    if domain == "cover":
        if position is not None:
            if position <= 0:
                return "fermé (position 0 %)"
            if position >= 100:
                return "ouvert (position 100 %)"
            pretty = int(position) if float(position).is_integer() else position
            return f"ouvert à {pretty} %"
        return {
            "closed": "fermé",
            "open": "ouvert",
            "closing": "en fermeture",
            "opening": "en ouverture",
        }.get(state_text, f"dans l'état {state_text or 'inconnu'}")

    if domain == "light":
        return {"on": "allumé", "off": "éteint"}.get(
            state_text, f"dans l'état {state_text or 'inconnu'}"
        )
    if domain in {"switch", "input_boolean"}:
        return {"on": "activé", "off": "désactivé"}.get(
            state_text, f"dans l'état {state_text or 'inconnu'}"
        )
    if domain == "binary_sensor":
        return {"on": "actif", "off": "inactif"}.get(
            state_text, f"dans l'état {state_text or 'inconnu'}"
        )
    if domain == "climate" and state_text == "off":
        return "à l'arrêt"
    return f"dans l'état {state_text or 'inconnu'}"


def _event_time(record: dict[str, Any]) -> str | None:
    for key in ("last_changed", "last_updated", "timestamp", "when"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _timestamp_sort_key(value: str | None) -> float:
    if not value:
        return float("-inf")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def _history_events(payload: dict[str, Any], entity_id: str) -> list[dict[str, Any]]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return []
    entities = data.get("entities")
    if not isinstance(entities, list):
        return []

    states: list[dict[str, Any]] = []
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("entity_id") != entity_id:
            continue
        raw_states = entity.get("states")
        if isinstance(raw_states, list):
            states = [item for item in raw_states if isinstance(item, dict)]
        break

    states.sort(key=lambda item: _timestamp_sort_key(_event_time(item)), reverse=True)
    recent: list[dict[str, Any]] = []
    signatures: set[tuple[str, str]] = set()
    for item in states:
        state = str(item.get("state") or "")
        pos = _position(item)
        signature = (state, str(pos))
        if signature in signatures:
            continue
        signatures.add(signature)
        recent.append(
            {
                "state": state or None,
                "current_position": pos,
                "time": _event_time(item),
            }
        )
        if len(recent) >= 4:
            break
    return recent


def _configuration_candidates(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    candidates: dict[str, dict[str, str | None]] = {}

    def add(entity_id: str, name: str | None = None) -> None:
        if not entity_id.startswith(("automation.", "script.")):
            return
        if entity_id not in candidates:
            candidates[entity_id] = {"entity_id": entity_id, "name": name}
        elif name and not candidates[entity_id].get("name"):
            candidates[entity_id]["name"] = name

    def visit(value: Any) -> None:
        if len(candidates) >= 8:
            return
        if isinstance(value, dict):
            entity_id = value.get("entity_id")
            name = next(
                (
                    value.get(key)
                    for key in ("friendly_name", "name", "alias", "title")
                    if isinstance(value.get(key), str) and value.get(key).strip()
                ),
                None,
            )
            if isinstance(entity_id, str):
                add(entity_id, str(name).strip() if name else None)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            for match in _ENTITY_REF_RE.findall(value):
                add(match)

    visit(payload)
    return list(candidates.values())[:8]


def synthesize_mcp_findings(
    entity_id: str, question: str, findings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Turn read-only MCP facts into French prose without assigning causal certainty."""
    state_payload = _tool_payload(findings, "ha_get_state")
    history_payload = _tool_payload(findings, "ha_get_history")
    search_payload = _tool_payload(findings, "ha_search")

    current = _entity_record(state_payload, entity_id)
    name = _friendly_name(current, entity_id) if current else entity_id
    current_state = str(current.get("state") or "") if current else ""
    current_position = _position(current) if current else None
    history = _history_events(history_payload, entity_id)
    candidates = _configuration_candidates(search_payload)

    facts: list[dict[str, Any]] = []
    answer_parts: list[str] = []

    if current:
        description = _state_word(entity_id, current_state, current_position)
        facts.append(
            {
                "type": "current_state",
                "entity_id": entity_id,
                "state": current_state or None,
                "current_position": current_position,
                "description": f"{name} est actuellement {description}.",
            }
        )
        answer_parts.append(f"{name} est actuellement {description}.")

    if history:
        latest = history[0]
        facts.append(
            {
                "type": "recent_history",
                "entity_id": entity_id,
                "events": history,
            }
        )
        if len(history) >= 2:
            previous = history[1]
            before = _state_word(
                entity_id,
                previous.get("state"),
                previous.get("current_position"),
            )
            after = _state_word(
                entity_id,
                latest.get("state"),
                latest.get("current_position"),
            )
            if before != after:
                answer_parts.append(
                    f"L’historique récent montre un passage de {before} à {after}."
                )

    if candidates:
        labels = [
            str(item.get("name") or item.get("entity_id")) for item in candidates[:3]
        ]
        suffix = "" if len(candidates) <= 3 else f" et {len(candidates) - 3} autre(s)"
        answer_parts.append(
            "La configuration contient "
            f"{len(candidates)} automatisation(s) ou script(s) candidat(s), notamment "
            + ", ".join(labels)
            + suffix
            + ". Ce sont des pistes de configuration, pas une cause prouvée."
        )

    asks_why = "pourquoi" in question.casefold()
    if asks_why:
        answer_parts.append(
            "Cette recherche MCP locale établit les faits et les pistes, mais n’attribue "
            "pas encore la cause : une trace d’exécution corrélée au changement serait "
            "nécessaire pour renforcer la preuve."
        )
    else:
        answer_parts.append(
            "Cette synthèse locale décrit les faits observés sans modifier le verdict causal d’Investigator."
        )

    if not current and not history and not candidates:
        answer_parts = [
            "La recherche MCP locale n’a pas fourni assez de données structurées pour produire une synthèse utile."
        ]

    return {
        "source": "Recherche MCP locale",
        "mode": "deterministic_local_synthesis",
        "read_only": True,
        "uses_llm": False,
        "status": "observed" if (current or history) else "partial",
        "causal_verdict": None,
        "investigator_status_unchanged": True,
        "answer": " ".join(answer_parts),
        "facts": facts,
        "configuration_leads": candidates,
        "policy": (
            "La synthèse MCP locale ne peut pas créer ni augmenter un verdict causal "
            "confirmed/probable/indeterminate."
        ),
    }
