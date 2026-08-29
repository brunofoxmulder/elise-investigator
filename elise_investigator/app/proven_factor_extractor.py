from __future__ import annotations

from typing import Any

from causal_factors import structured_factor
from causal_recorder import CausalRecord


def factor_from_proven_human_cause(
    reason: str | None,
    human_cause: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Project one already-proven human cause into the generic factor contract.

    This deliberately does not reinterpret the trace. Dev.36+ has already selected
    one proven cause and rendered ``reason``. Dev.41 only preserves that same fact
    in ``factors`` so existing answers remain byte-for-byte driven by ``reason``.
    """
    if not reason or not isinstance(human_cause, dict):
        return None
    if human_cause.get("proven") is not True:
        return None

    kind = str(human_cause.get("kind") or "proven_cause")
    return structured_factor(
        kind=kind,
        role="cause",
        proven=True,
        label=reason,
        proof_origin=human_cause.get("origin"),
        proof_path=human_cause.get("path"),
        proof_command_path=human_cause.get("command_path"),
        proof_detail=human_cause.get("detail"),
    )


def attach_first_proven_factor(record: CausalRecord) -> bool:
    """Attach a single factor only when the record already contains proven cause proof.

    Existing ``factors`` are never replaced. This makes the change additive and
    idempotent, and prevents dev.41 from changing current response semantics.
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
