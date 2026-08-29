from __future__ import annotations

from typing import Any

from causal_factors import structured_factor
from causal_recorder import CausalRecord


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        ordered = []
        for key in ("days", "hours", "minutes", "seconds"):
            if value.get(key) is not None:
                ordered.append(f"{key}={value[key]}")
        return ",".join(ordered) or None
    return None


def _numeric_relation(detail: dict[str, Any]) -> tuple[str | None, Any]:
    """Describe the already-proven numeric fact without re-deciding causality."""
    above = detail.get("above")
    below = detail.get("below")
    result = detail.get("condition_result")

    if result is False:
        actual = _number(detail.get("actual"))
        above_n = _number(above)
        below_n = _number(below)
        if above is not None and below is not None:
            if actual is None:
                return None, None
            if above_n is not None and actual <= above_n:
                return "not_above", above
            if below_n is not None and actual >= below_n:
                return "not_below", below
            # A false two-sided condition with unusable/inconsistent runtime data
            # stays descriptive but does not guess which boundary was decisive.
            return None, None
        if above is not None:
            return "not_above", above
        if below is not None:
            return "not_below", below
        return None, None

    if result is True:
        if above is not None and below is None:
            return "above", above
        if below is not None and above is None:
            return "below", below
        return None, None

    # Trigger-style numeric details may not carry condition_result. Preserve the
    # configured relation only when one boundary is unambiguous.
    if above is not None and below is None:
        return "above", above
    if below is not None and above is None:
        return "below", below
    return None, None


def _structured_semantics(human_cause: dict[str, Any]) -> dict[str, Any]:
    """Project fields already present in the selected proof into neutral semantics.

    This function never opens a trace and never chooses whether something is a
    cause. That decision has already been made upstream by the deterministic
    selector. It only carries useful values from the selected proof into the
    stable factor contract.
    """
    detail = human_cause.get("detail")
    if not isinstance(detail, dict):
        detail = {}

    platform = str(detail.get("platform") or "")
    relation: str | None = None
    value: Any = detail.get("actual")
    threshold: Any = None

    if platform == "numeric_state":
        relation, threshold = _numeric_relation(detail)
    elif platform == "state":
        wanted = detail.get("to")
        if detail.get("condition_result") is False and wanted is not None:
            relation = "not_equal"
            threshold = wanted
        elif detail.get("condition_result") is True and wanted is not None:
            relation = "equal"
            threshold = wanted
        elif wanted is not None:
            relation = "changed_to"
            value = wanted
    elif platform == "event" and detail.get("event") is not None:
        relation = "event"
        value = detail.get("event")

    if value is None and detail.get("to") is not None:
        value = detail.get("to")

    return {
        "relation": relation,
        "value": value,
        "threshold": threshold,
        "unit": human_cause.get("unit"),
        "duration": _duration(detail.get("for")),
    }


def factor_from_proven_human_cause(
    reason: str | None,
    human_cause: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Project one already-proven human cause into the generic factor contract.

    Dev.36+ has already selected one proven cause and rendered ``reason``. Dev.42
    still does not reinterpret the trace: it only enriches dev.41's factor with
    relation/value/threshold/unit/duration when those fields are already present
    in that selected proof.
    """
    if not reason or not isinstance(human_cause, dict):
        return None
    if human_cause.get("proven") is not True:
        return None

    kind = str(human_cause.get("kind") or "proven_cause")
    semantic = _structured_semantics(human_cause)
    return structured_factor(
        kind=kind,
        role="cause",
        proven=True,
        label=reason,
        relation=semantic["relation"],
        value=semantic["value"],
        threshold=semantic["threshold"],
        unit=semantic["unit"],
        duration=semantic["duration"],
        proof_origin=human_cause.get("origin"),
        proof_path=human_cause.get("path"),
        proof_command_path=human_cause.get("command_path"),
        proof_detail=human_cause.get("detail"),
    )


def attach_first_proven_factor(record: CausalRecord) -> bool:
    """Attach a single factor only when the record already contains proven cause proof.

    Existing ``factors`` are never replaced. This makes the change additive and
    idempotent, and prevents dev.42 from changing current response semantics.
    """
    if record.origin_type not in {"automation", "script"} or not record.reason:
        return False
    if record.factors:
        return False

    proof = record.trigger if isinstance(record.trigger, dict) else {}
    factor = factor_from_proven_human_cause(record.reason, proof.get("human_cause"))
    if factor is None:
        return False
    record.factors = [factor]
    return True
