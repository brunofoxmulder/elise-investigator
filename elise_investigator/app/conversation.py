from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from models import InvestigationRequest


@dataclass(slots=True)
class ConversationResolutionError(ValueError):
    message: str
    candidates: list[dict[str, str]]

    def __str__(self) -> str:
        return self.message


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9_.:'\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _words(value: Any) -> list[str]:
    return re.findall(r"[a-z0-9]+", _norm(value))


_STOPWORDS = {
    "elise",
    "pourquoi",
    "comment",
    "est",
    "ce",
    "que",
    "qui",
    "quoi",
    "la",
    "le",
    "les",
    "un",
    "une",
    "de",
    "du",
    "des",
    "d",
    "l",
    "a",
    "au",
    "aux",
    "ma",
    "mon",
    "mes",
    "vient",
    "juste",
    "maintenant",
    "encore",
    "se",
    "s",
    "etre",
    "ete",
    "faire",
    "fait",
    "passer",
    "passee",
    "passe",
    "allumer",
    "allumee",
    "allume",
    "allumage",
    "eteindre",
    "eteinte",
    "eteint",
    "ouvrir",
    "ouverte",
    "ouvert",
    "fermer",
    "fermee",
    "ferme",
    "vers",
    "heure",
    "heures",
    "minute",
    "minutes",
    "aujourd",
    "hui",
    "hier",
}


def _content_tokens(value: Any) -> set[str]:
    return {token for token in _words(value) if token not in _STOPWORDS and not token.isdigit()}


def _entity_rows(states: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in states:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or entity_id).strip()
        rows.append({"entity_id": entity_id, "name": name, "domain": entity_id.split(".", 1)[0]})
    return rows


def resolve_entity(question: str, states: list[dict[str, Any]]) -> dict[str, str]:
    """Resolve a natural-language entity mention conservatively.

    Exact entity IDs and full friendly-name phrases win. Token matching is only a fallback,
    and ties stay ambiguous instead of being guessed.
    """
    qnorm = _norm(question)
    qtokens = _content_tokens(question)
    scored: list[tuple[tuple[int, int, int], dict[str, str]]] = []

    for row in _entity_rows(states):
        entity_id = row["entity_id"]
        name = row["name"]
        id_norm = _norm(entity_id)
        name_norm = _norm(name)
        name_tokens = _content_tokens(name)

        if id_norm and id_norm in qnorm:
            score = (0, -len(id_norm), 0)
        elif name_norm and re.search(rf"(?<![a-z0-9]){re.escape(name_norm)}(?![a-z0-9])", qnorm):
            score = (1, -len(name_norm), 0)
        elif name_tokens and name_tokens.issubset(qtokens):
            # Prefer the most specific name, then the one with the least extra wording.
            score = (2, -len(name_tokens), len(_words(name)))
        else:
            continue
        scored.append((score, row))

    if not scored:
        raise ConversationResolutionError(
            "Je n'ai pas reconnu avec certitude l'objet Home Assistant dans cette question.",
            [],
        )

    scored.sort(key=lambda item: (item[0], item[1]["name"].casefold(), item[1]["entity_id"]))
    best_score = scored[0][0]
    best = [row for score, row in scored if score == best_score]
    unique = {(row["entity_id"], row["name"]): row for row in best}
    best = list(unique.values())

    if len(best) != 1:
        raise ConversationResolutionError(
            "Plusieurs objets correspondent à la question ; je préfère ne pas deviner.",
            [{"entity_id": row["entity_id"], "name": row["name"]} for row in best[:8]],
        )
    return best[0]


def parse_observed_value(question: str) -> str | None:
    q = _norm(question)
    phrase_map = (
        (("s'allum", "allum", "allume"), "on"),
        (("s'etein", "eteint", "eteinte", "extinction"), "off"),
        (("s'ouvr", "ouvert", "ouverte", "ouverture"), "open"),
        (("se ferm", "ferme", "fermee", "fermeture"), "closed"),
    )
    for fragments, value in phrase_map:
        if any(fragment in q for fragment in fragments):
            return value

    mode_match = re.search(r"\b(?:en|mode)\s+(cool|heat|off|auto|dry|fan_only)\b", q)
    if mode_match:
        return mode_match.group(1)
    return None


def _parse_explicit_date(qnorm: str, now: datetime) -> datetime.date:
    date_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", qnorm)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        raw_year = date_match.group(3)
        year = now.year if raw_year is None else int(raw_year)
        if year < 100:
            year += 2000
        return datetime(year, month, day).date()
    if "hier" in qnorm:
        return (now - timedelta(days=1)).date()
    return now.date()


def parse_observed_time(question: str, tz: ZoneInfo, *, now: datetime | None = None) -> str | None:
    """Parse simple conversational time hints without inventing precision.

    Supported examples: "vers 22h05", "à 20:05", "hier vers 18h", "22/08 à 20h05",
    and "il y a 10 minutes". A bare "vient de" intentionally stays unset so the
    investigator can use the latest recorded event.
    """
    current = now.astimezone(tz) if now else datetime.now(tz)
    q = _norm(question)

    relative = re.search(r"\bil y a\s+(\d{1,3})\s*(?:min|mins|minute|minutes)\b", q)
    if relative:
        return (current - timedelta(minutes=int(relative.group(1)))).isoformat()

    time_match = re.search(r"\b(\d{1,2})(?:\s*[h:]\s*(\d{1,2}))\b", q)
    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None

    try:
        target_date = _parse_explicit_date(q, current)
    except ValueError:
        return None
    target = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=tz,
    )

    # Around midnight, a clock time several hours in the future almost always refers to
    # the previous evening unless the user explicitly supplied a date/day word.
    explicit_day = "hier" in q or "aujourd" in q or bool(re.search(r"\b\d{1,2}[/-]\d{1,2}", q))
    if not explicit_day and target > current + timedelta(hours=2):
        target -= timedelta(days=1)
    return target.isoformat()


async def build_investigation_request(
    question: str,
    *,
    ha,
) -> tuple[InvestigationRequest, dict[str, Any]]:
    text = str(question or "").strip()
    if not text:
        raise ValueError("La question est vide.")

    states = await ha.get_all_states()
    entity = resolve_entity(text, states)
    cfg = await ha.get_config()
    tz_name = str(cfg.get("time_zone") or "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    observed_time = parse_observed_time(text, tz)
    observed_value = parse_observed_value(text)
    request = InvestigationRequest(
        entity_id=entity["entity_id"],
        observed_time=observed_time,
        observed_value=observed_value,
    )
    interpretation = {
        "question": text,
        "entity_id": entity["entity_id"],
        "entity_name": entity["name"],
        "observed_time": observed_time,
        "observed_value": observed_value,
        "time_zone": tz.key,
    }
    return request, interpretation
