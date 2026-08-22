from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ha_client import HAReadOnlyClient, HomeAssistantError
from models import Evidence, InvestigationRequest, InvestigationResult

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _Candidate:
    entity_id: str
    domain: str
    name: str | None
    enabled: bool
    item_id: str
    config: dict[str, Any] | None
    trace: dict[str, Any] | None = None
    trace_distance_s: float | None = None
    target_proven: bool = False


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _walk_contains(obj: Any, needle: str) -> bool:
    if isinstance(obj, str):
        return needle in obj
    if isinstance(obj, dict):
        return any(_walk_contains(k, needle) or _walk_contains(v, needle) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(_walk_contains(v, needle) for v in obj)
    return False


def _extract_trace_start(trace: dict[str, Any]) -> datetime | None:
    ts = trace.get("timestamp")
    if isinstance(ts, dict):
        return _dt(ts.get("start"))
    return _dt(trace.get("start"))


def _trace_run_id(trace: dict[str, Any]) -> str | None:
    run_id = trace.get("run_id")
    return str(run_id) if run_id is not None else None


def _logbook_time(entry: dict[str, Any]) -> datetime | None:
    return _dt(entry.get("when") or entry.get("timestamp") or entry.get("time"))


def _history_time(entry: dict[str, Any], *, attribute: str | None = None) -> datetime | None:
    # last_updated is essential for attribute-only changes; last_changed is primary-state only.
    return _dt(entry.get("last_updated") or entry.get("last_changed"))


def _state_value(entry: dict[str, Any], attribute: str | None) -> Any:
    if attribute:
        attrs = entry.get("attributes") or {}
        return attrs.get(attribute) if isinstance(attrs, dict) else None
    return entry.get("state")


def _same_value(actual: Any, expected: Any) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    if str(actual) == str(expected):
        return True
    try:
        return abs(float(actual) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return False


def _event_kind(previous: dict[str, Any] | None, current: dict[str, Any], attribute: str | None) -> str:
    state = current.get("state")
    prev_state = previous.get("state") if previous else None
    if state == "unavailable":
        return "availability_lost"
    if prev_state == "unavailable" and state != "unavailable":
        return "availability_recovered"
    if attribute:
        prev_attrs = (previous or {}).get("attributes") or {}
        cur_attrs = current.get("attributes") or {}
        return "attribute_change" if prev_attrs.get(attribute) != cur_attrs.get(attribute) else "attribute_update"
    if previous and prev_state == state:
        return "state_update"
    return "state_change"


def _extract_trace_trigger(detail: dict[str, Any]) -> dict[str, Any] | None:
    direct = detail.get("trigger")
    if isinstance(direct, dict) and direct:
        return direct
    trace_nodes = detail.get("trace")
    if isinstance(trace_nodes, dict):
        for path, nodes in trace_nodes.items():
            if not str(path).startswith("trigger"):
                continue
            if not isinstance(nodes, list):
                nodes = [nodes]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                changed = node.get("changed_variables") or {}
                trigger = changed.get("trigger") if isinstance(changed, dict) else None
                if isinstance(trigger, dict):
                    return trigger
                result = node.get("result")
                if isinstance(result, dict) and isinstance(result.get("trigger"), dict):
                    return result["trigger"]
    return None


def _extract_service_actions(obj: Any, target_entity: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            domain = value.get("domain")
            service = value.get("service")
            target = value.get("target")
            if domain and service and _walk_contains(target, target_entity):
                found.append({"service": f"{domain}.{service}", "target": target, "data": value.get("service_data") or value.get("data")})
            for child in value.values():
                walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)
    walk(obj)
    # Stable de-duplication for repeated representations of the same action.
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in found:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _human_status(status: str) -> str:
    return {"confirmed": "confirmée", "probable": "probable", "indeterminate": "indéterminée"}.get(status, status)


class Investigator:
    def __init__(self, ha: HAReadOnlyClient, *, default_window_minutes: int = 30, max_reverse_candidates: int = 25):
        self.ha = ha
        self.default_window_minutes = default_window_minutes
        self.max_reverse_candidates = max_reverse_candidates
        self._config_cache: tuple[datetime, dict[str, Any]] | None = None
        self._all_states_cache: tuple[datetime, list[dict[str, Any]]] | None = None

    async def _ha_config(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if self._config_cache and (now - self._config_cache[0]).total_seconds() < 300:
            return self._config_cache[1]
        data = await self.ha.get_config()
        self._config_cache = (now, data)
        return data

    async def _timezone(self) -> ZoneInfo:
        cfg = await self._ha_config()
        name = cfg.get("time_zone") or "UTC"
        try:
            return ZoneInfo(str(name))
        except Exception:
            return ZoneInfo("UTC")

    async def _normalize_observed_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = _dt(value)
        if parsed is None:
            # Friendly support for HTML datetime-local values without seconds/offset.
            try:
                parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=await self._timezone())
        return parsed

    async def _all_states(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        if self._all_states_cache and (now - self._all_states_cache[0]).total_seconds() < 30:
            return self._all_states_cache[1]
        states = await self.ha.get_all_states()
        self._all_states_cache = (now, states)
        return states

    def _choose_event(
        self,
        history: list[dict[str, Any]],
        *,
        observed_time: datetime | None,
        observed_value: Any,
        attribute: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if not history:
            return None, None
        indexed: list[tuple[int, dict[str, Any], datetime]] = []
        for i, row in enumerate(history):
            when = _history_time(row, attribute=attribute)
            if when:
                indexed.append((i, row, when))
        if not indexed:
            return (history[-2] if len(history) > 1 else None), history[-1]

        matching = [x for x in indexed if _same_value(_state_value(x[1], attribute), observed_value)]
        pool = matching or indexed
        if observed_time:
            chosen = min(pool, key=lambda x: abs((x[2] - observed_time).total_seconds()))
        else:
            # With no explicit time, latest recorded update is the most honest default.
            chosen = max(pool, key=lambda x: x[2])
        idx = chosen[0]
        previous = history[idx - 1] if idx > 0 else None
        return previous, chosen[1]

    def _nearest_logbook(self, entries: list[dict[str, Any]], event_time: datetime | None) -> dict[str, Any] | None:
        if not entries:
            return None
        if not event_time:
            return entries[-1]
        with_time = [(entry, _logbook_time(entry)) for entry in entries]
        with_time = [(e, t) for e, t in with_time if t]
        if not with_time:
            return entries[-1]
        return min(with_time, key=lambda pair: abs((pair[1] - event_time).total_seconds()))[0]

    def _source_from_logbook(self, entry: dict[str, Any] | None) -> dict[str, Any] | None:
        if not entry:
            return None
        # HA logbook has evolved over time; support both current context fields and older names.
        user_id = entry.get("context_user_id") or entry.get("user_id")
        context_entity = (
            entry.get("context_entity_id")
            or entry.get("context_entity")
            or entry.get("source_entity_id")
        )
        context_name = entry.get("context_entity_id_name") or entry.get("source_name")
        if user_id:
            return {
                "type": "user",
                "entity_id": None,
                "name": "Utilisateur Home Assistant",
                "system_confirmed": True,
                "detail": "Le contexte Logbook contient un utilisateur.",
            }
        if isinstance(context_entity, str) and context_entity.startswith("automation."):
            return {
                "type": "automation",
                "entity_id": context_entity,
                "name": context_name,
                "system_confirmed": True,
                "detail": "Le Logbook rattache l'événement à cette automatisation.",
            }
        if isinstance(context_entity, str) and context_entity.startswith("script."):
            return {
                "type": "script",
                "entity_id": context_entity,
                "name": context_name,
                "system_confirmed": True,
                "detail": "Le Logbook rattache l'événement à ce script.",
            }
        return None

    async def _config_id_for_entity(self, entity_id: str) -> tuple[str, str] | None:
        state = await self.ha.get_state(entity_id)
        domain, slug = entity_id.split(".", 1)
        attrs = state.get("attributes") or {}
        if domain == "automation":
            item_id = attrs.get("id")
            if item_id is None:
                return None
            return domain, str(item_id)
        if domain == "script":
            return domain, str(attrs.get("id") or slug)
        return None

    async def _best_trace_for_source(self, source_entity_id: str, event_time: datetime | None) -> dict[str, Any] | None:
        resolved = await self._config_id_for_entity(source_entity_id)
        if not resolved:
            return None
        domain, item_id = resolved
        traces = await self.ha.list_traces(domain, item_id)
        if not traces:
            return None
        if event_time:
            timed = [(t, _extract_trace_start(t)) for t in traces]
            timed = [(t, dt) for t, dt in timed if dt]
            if timed:
                summary, start = min(timed, key=lambda pair: abs((pair[1] - event_time).total_seconds()))
                # A trace can legitimately precede device state confirmation by seconds/minutes.
                if abs((start - event_time).total_seconds()) > 300:
                    return None
            else:
                summary = traces[-1]
        else:
            summary = traces[-1]
        run_id = _trace_run_id(summary)
        if not run_id:
            return None
        detail = await self.ha.get_trace(domain, item_id, run_id)
        if detail is None:
            return {"summary": summary, "detail": None, "expired": True, "domain": domain, "item_id": item_id}
        return {"summary": summary, "detail": detail, "expired": False, "domain": domain, "item_id": item_id}

    def _trace_mentions_target(self, trace_bundle: dict[str, Any] | None, entity_id: str) -> bool:
        if not trace_bundle:
            return False
        detail = trace_bundle.get("detail")
        return _walk_contains(detail, entity_id) if detail else False

    async def _reverse_search(self, entity_id: str, event_time: datetime | None) -> list[_Candidate]:
        states = await self._all_states()
        relevant = [s for s in states if str(s.get("entity_id", "")).split(".", 1)[0] in {"automation", "script", "scene"}]
        # Examine enabled/runnable first, then disabled entities only as context.
        relevant.sort(key=lambda s: (s.get("state") == "off", s.get("entity_id", "")))
        semaphore = asyncio.Semaphore(8)

        async def inspect(state: dict[str, Any]) -> _Candidate | None:
            eid = str(state.get("entity_id", ""))
            domain, slug = eid.split(".", 1)
            attrs = state.get("attributes") or {}
            async with semaphore:
                if domain == "automation":
                    item_id = str(attrs.get("id") or "")
                    if not item_id:
                        return None
                    cfg = await self.ha.get_automation_config(item_id)
                elif domain == "script":
                    item_id = str(attrs.get("id") or slug)
                    cfg = await self.ha.get_script_config(slug)
                else:
                    item_id = slug
                    cfg = await self.ha.get_scene_config(slug)
            if not cfg or not _walk_contains(cfg, entity_id):
                return None
            return _Candidate(
                entity_id=eid,
                domain=domain,
                name=attrs.get("friendly_name"),
                enabled=state.get("state") != "off" if domain == "automation" else True,
                item_id=item_id,
                config=cfg,
            )

        # Keep reverse search bounded. We fetch configs until enough matching candidates are found.
        out: list[_Candidate] = []
        batch_size = 20
        for start in range(0, len(relevant), batch_size):
            batch = relevant[start : start + batch_size]
            results = await asyncio.gather(*(inspect(s) for s in batch), return_exceptions=True)
            for result in results:
                if isinstance(result, _Candidate):
                    out.append(result)
                    if len(out) >= self.max_reverse_candidates:
                        break
            if len(out) >= self.max_reverse_candidates:
                break

        # Upgrade candidates with direct trace evidence where possible.
        async def enrich(candidate: _Candidate) -> None:
            if candidate.domain not in {"automation", "script"} or not candidate.enabled:
                return
            try:
                traces = await self.ha.list_traces(candidate.domain, candidate.item_id)
            except HomeAssistantError:
                return
            if not traces:
                return
            timed = [(t, _extract_trace_start(t)) for t in traces]
            timed = [(t, dt) for t, dt in timed if dt]
            if not timed:
                return
            if event_time:
                summary, start_dt = min(timed, key=lambda pair: abs((pair[1] - event_time).total_seconds()))
                distance = abs((start_dt - event_time).total_seconds())
                if distance > 300:
                    return
            else:
                summary, start_dt = max(timed, key=lambda pair: pair[1])
                distance = 0.0
            run_id = _trace_run_id(summary)
            if not run_id:
                return
            detail = await self.ha.get_trace(candidate.domain, candidate.item_id, run_id)
            candidate.trace = detail or {"trace_expired": True, "summary": summary}
            candidate.trace_distance_s = distance
            candidate.target_proven = bool(detail and _walk_contains(detail, entity_id))

        await asyncio.gather(*(enrich(c) for c in out), return_exceptions=True)
        return out

    def _friendly_event(self, event_type: str, entity_name: str | None, before: Any, after: Any, attribute: str | None) -> str:
        label = entity_name or "L'entité"
        if event_type == "availability_lost":
            return f"{label} est devenue indisponible."
        if event_type == "availability_recovered":
            return f"{label} est redevenue disponible avec la valeur {after}."
        if event_type == "attribute_change":
            return f"{label} est restée dans son état principal, mais l'attribut {attribute} est passé de {before} à {after}."
        if event_type == "attribute_update":
            return f"{label} a été mise à jour sans changement de l'attribut {attribute} ({after})."
        if event_type == "state_update":
            return f"{label} a été mise à jour sans changement de son état principal ({after})."
        return f"{label} est passée de {before} à {after}."

    def _build_answer(self, result: InvestigationResult) -> str:
        status_fr = _human_status(result.status)
        event_sentence = result.observed.get("description") or "Événement observé."
        cause_type = result.cause.get("type")
        cause_name = result.cause.get("name") or result.cause.get("entity_id")
        if cause_type == "user":
            cause_sentence = "La cause est une action utilisateur identifiée par le contexte Home Assistant."
        elif cause_type in {"automation", "script"} and cause_name:
            cause_sentence = f"La cause est {cause_name}."
        elif cause_type == "sensor":
            cause_sentence = "Home Assistant confirme l'événement du capteur, mais pas ce qui l'a physiquement provoqué."
        elif cause_type == "recovery":
            cause_sentence = "Il s'agit d'un retour de disponibilité ; aucune commande physique n'est prouvée."
        elif cause_type == "user_declaration":
            cause_sentence = "La cause est déclarée par l'utilisateur mais n'est pas confirmée par les traces système conservées."
        else:
            cause_sentence = "Aucune cause système ne peut être établie avec les preuves conservées."
        limit = f" Limite : {result.limits[0]}" if result.limits else ""
        return f"Cause {status_fr}. {event_sentence} {cause_sentence}{limit}".strip()

    async def investigate(self, request: InvestigationRequest) -> InvestigationResult:
        entity_id = request.entity_id.strip()
        if "." not in entity_id or " " in entity_id:
            raise ValueError("entity_id invalide")

        now = datetime.now(timezone.utc)
        observed_time = await self._normalize_observed_time(request.observed_time)
        window_minutes = request.window_minutes or self.default_window_minutes
        window_minutes = max(5, min(int(window_minutes), 180))

        state_task = self.ha.get_state(entity_id)
        registry_task = self.ha.get_entity_registry(entity_id)
        state, registry = await asyncio.gather(state_task, registry_task)
        attrs = state.get("attributes") or {}
        entity_name = attrs.get("friendly_name") or (registry or {}).get("name") or (registry or {}).get("original_name")

        if observed_time:
            start = observed_time - timedelta(minutes=window_minutes)
            end = observed_time + timedelta(minutes=window_minutes)
            if end > now + timedelta(minutes=1):
                end = now + timedelta(minutes=1)
        else:
            end = now
            start = end - timedelta(minutes=window_minutes)

        history_task = self.ha.get_history(entity_id, start, end, significant_only=False)
        logbook_task = self.ha.get_logbook(entity_id, start, end)
        history, logbook = await asyncio.gather(history_task, logbook_task)

        previous, event = self._choose_event(
            history,
            observed_time=observed_time,
            observed_value=request.observed_value,
            attribute=request.attribute,
        )

        evidence: list[Evidence] = []
        limits: list[str] = []
        chain: list[dict[str, Any]] = []
        candidates_out: list[dict[str, Any]] = []

        if event:
            event_time_dt = _history_time(event, attribute=request.attribute)
            if not observed_time and event_time_dt and event_time_dt < start:
                # History may return the boundary state from before the requested window.
                event = None

        if event:
            event_time_dt = _history_time(event, attribute=request.attribute)
            before_value = _state_value(previous, request.attribute) if previous else None
            after_value = _state_value(event, request.attribute)
            event_type = _event_kind(previous, event, request.attribute)
            evidence.append(
                Evidence(
                    kind="history",
                    summary=f"Événement enregistré par le Recorder: {before_value} → {after_value}",
                    timestamp=event_time_dt.isoformat() if event_time_dt else None,
                    strength="direct",
                    raw={"previous": previous, "event": event},
                )
            )
        else:
            event_time_dt = observed_time or _dt(state.get("last_updated") or state.get("last_changed"))
            before_value = None
            after_value = request.observed_value if request.observed_value is not None else _state_value(state, request.attribute)
            event_type = "current_state_only"
            limits.append("Aucun événement historique correspondant n'a été retrouvé dans la fenêtre examinée.")

        observed = {
            "before": before_value,
            "after": after_value,
            "attribute": request.attribute,
            "description": self._friendly_event(event_type, entity_name, before_value, after_value, request.attribute),
        }

        nearest_log = self._nearest_logbook(logbook, event_time_dt)
        if nearest_log:
            log_time = _logbook_time(nearest_log)
            delta = abs((log_time - event_time_dt).total_seconds()) if log_time and event_time_dt else None
            # Treat very distant logbook entry as context only, never direct cause.
            strength = "direct" if delta is None or delta <= 30 else "supporting"
            evidence.append(
                Evidence(
                    kind="logbook",
                    summary=nearest_log.get("message") or nearest_log.get("name") or "Entrée Logbook",
                    timestamp=log_time.isoformat() if log_time else None,
                    strength=strength,
                    raw=nearest_log,
                )
            )
        source = self._source_from_logbook(nearest_log) if (nearest_log and (delta is None or delta <= 30)) else None

        # Sensor events: upstream physical actor is inherently outside HA evidence.
        domain = entity_id.split(".", 1)[0]
        if event_type == "availability_recovered":
            cause = {
                "type": "recovery",
                "entity_id": None,
                "name": "Retour de disponibilité",
                "system_confirmed": True,
            }
            status = "confirmed"
            limits.append("Le retour d'état ne prouve pas qu'une action physique a eu lieu sur l'appareil.")
        elif domain in {"binary_sensor", "sensor", "event"} and source is None:
            cause = {
                "type": "sensor",
                "entity_id": entity_id,
                "name": entity_name,
                "system_confirmed": True,
            }
            status = "confirmed"
            limits.append("La cause physique en amont du capteur (personne, objet, phénomène) n'est pas identifiable par Home Assistant seul.")
        elif source:
            cause = source
            status = "confirmed"
        else:
            cause = {"type": "unknown", "entity_id": None, "name": None, "system_confirmed": False}
            status = "indeterminate"

        # If a direct automation/script source exists, try to add its exact trace.
        if source and source.get("entity_id") and source.get("type") in {"automation", "script"}:
            trace_bundle = await self._best_trace_for_source(source["entity_id"], event_time_dt)
            if trace_bundle:
                if trace_bundle.get("detail"):
                    detail = trace_bundle["detail"]
                    target_proven = _walk_contains(detail, entity_id)
                    evidence.append(
                        Evidence(
                            kind="trace",
                            summary="Trace d'exécution retrouvée" + (" et cible confirmée" if target_proven else ""),
                            timestamp=_extract_trace_start(trace_bundle.get("summary") or {}).isoformat()
                            if _extract_trace_start(trace_bundle.get("summary") or {})
                            else None,
                            source=source["entity_id"],
                            strength="direct" if target_proven else "supporting",
                            raw=detail,
                        )
                    )
                    trigger = _extract_trace_trigger(detail)
                    actions = _extract_service_actions(detail, entity_id)
                    chain.append({"kind": source.get("type"), "entity_id": source["entity_id"], "proven": True})
                    if trigger:
                        source["trigger_source"] = trigger
                        chain.insert(0, {"kind": "trigger", "detail": trigger, "proven": True})
                    if actions:
                        source["commands"] = actions
                        for action in actions:
                            chain.append({"kind": "command", **action, "proven": True})
                    elif target_proven:
                        chain.append({"kind": "action_target", "entity_id": entity_id, "proven": True})
                elif trace_bundle.get("expired"):
                    limits.append("La trace détaillée de cette exécution n'est plus conservée par Home Assistant.")

        # Reverse search is strictly fallback when no direct system source was found.
        if status == "indeterminate":
            reverse = await self._reverse_search(entity_id, event_time_dt)
            for candidate in reverse:
                item = {
                    "entity_id": candidate.entity_id,
                    "name": candidate.name,
                    "domain": candidate.domain,
                    "enabled_now": candidate.enabled,
                    "trace_near_event": candidate.trace is not None,
                    "trace_target_proven": candidate.target_proven,
                    "trace_distance_seconds": candidate.trace_distance_s,
                }
                candidates_out.append(item)
            traced = [c for c in reverse if c.enabled and c.target_proven]
            if traced:
                # One or several branches may be true; never force exclusivity.
                status = "confirmed"
                if len(traced) == 1:
                    c = traced[0]
                    cause = {
                        "type": c.domain,
                        "entity_id": c.entity_id,
                        "name": c.name,
                        "system_confirmed": True,
                        "exclusive": len(reverse) == 1,
                    }
                else:
                    cause = {
                        "type": "multiple",
                        "entity_id": None,
                        "name": "Plusieurs exécutions prouvées",
                        "system_confirmed": True,
                        "exclusive": False,
                        "sources": [c.entity_id for c in traced],
                    }
                    limits.append("Plusieurs causes peuvent être vraies simultanément ; l'exclusivité n'est pas démontrée.")
                for c in traced:
                    evidence.append(
                        Evidence(
                            kind="trace",
                            summary=f"Trace proche de l'événement et action vers {entity_id}",
                            source=c.entity_id,
                            strength="direct",
                            raw=c.trace,
                        )
                    )
            else:
                enabled_candidates = [c for c in reverse if c.enabled]
                if len(enabled_candidates) == 1:
                    c = enabled_candidates[0]
                    status = "probable"
                    cause = {
                        "type": c.domain,
                        "entity_id": c.entity_id,
                        "name": c.name,
                        "system_confirmed": False,
                        "detail": "Configuration candidate unique, sans trace d'exécution probante.",
                    }
                    limits.append("La configuration prouve seulement que cette source pouvait agir sur l'entité, pas qu'elle l'a fait lors de cet événement.")
                elif reverse:
                    limits.append("La recherche inverse trouve des candidats, mais aucune exécution précise n'est prouvée.")

        # User declaration enriches provenance but never upgrades system evidence.
        if request.user_declaration:
            evidence.append(
                Evidence(
                    kind="user_declaration",
                    summary=request.user_declaration,
                    strength="declared",
                    source="user",
                )
            )
            if status == "indeterminate":
                cause = {
                    "type": "user_declaration",
                    "entity_id": None,
                    "name": "Déclaration utilisateur",
                    "system_confirmed": False,
                    "detail": request.user_declaration,
                }
                limits.append("La déclaration utilisateur n'est pas une preuve système rétroactive.")

        # Temporal-proximity guardrail is explicit in metadata.
        meta = {
            "engine": "elise-investigator-core",
            "version": "0.1.0-beta.1",
            "read_only": True,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "identity": {
                "unique_id": (registry or {}).get("unique_id"),
                "platform": (registry or {}).get("platform"),
                "device_id": (registry or {}).get("device_id"),
                "entity_id_is_mutable": True,
            },
            "rules": {
                "event_first": True,
                "config_is_not_execution": True,
                "temporal_proximity_is_not_causality": True,
                "command_is_not_state_change": True,
                "trace_retention_is_limited": True,
            },
        }

        result = InvestigationResult(
            status=status,
            entity_id=entity_id,
            entity_name=entity_name,
            event_type=event_type,
            event_time=event_time_dt.isoformat() if event_time_dt else None,
            observed=observed,
            cause=cause,
            chain=chain,
            evidence=evidence,
            candidates=candidates_out,
            limits=list(dict.fromkeys(limits)),
            meta=meta,
        )
        result.answer_text = self._build_answer(result)
        return result
