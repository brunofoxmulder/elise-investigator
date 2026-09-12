from __future__ import annotations

from typing import Any

from models import InvestigationResult


def periodic_position_decision(
    result: InvestigationResult,
    command: dict[str, Any],
    trigger: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Describe a proven periodic cover positioning decision without promoting guards.

    This is intentionally narrow: cover domain only, proven time_pattern trigger only,
    and an executed ``cover.set_cover_position`` command already selected by the V2
    resolver as the unique effect command. The requested position is action evidence,
    not a guessed cause or a condition promoted from configuration.
    """
    if result.entity_id.split(".", 1)[0] != "cover":
        return None
    if not isinstance(trigger, dict):
        return None
    platform = str(trigger.get("platform") or trigger.get("trigger") or "").casefold()
    if platform != "time_pattern":
        return None
    if str(command.get("domain") or "") != "cover":
        return None
    if str(command.get("service") or "") != "set_cover_position":
        return None

    data = command.get("data")
    position = data.get("position") if isinstance(data, dict) else None
    try:
        numeric_position = float(position)
    except (TypeError, ValueError):
        return None
    if not 0 <= numeric_position <= 100:
        return None

    return {
        "kind": "cover_periodic_position",
        "origin": "cover_periodic_position",
        "path": "trigger+effect_command",
        "command_path": command.get("path"),
        "proven": True,
        "detail": {
            "trigger": dict(trigger),
            "requested_position": numeric_position,
        },
        "effect_command": {
            "path": command.get("path"),
            "domain": command.get("domain"),
            "service": command.get("service"),
        },
    }
