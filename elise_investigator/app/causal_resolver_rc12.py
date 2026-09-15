from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from causal_resolver_rc9 import resolve_cause_rc9, unique_effect_command_rc9
from models import InvestigationResult
from trace_command_projection_rc11 import project_exact_effect_commands_rc11
from trigger_semantics import complete_confirmed_trace_chain


def resolve_cause_rc12(
    result: InvestigationResult,
    registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Complete missing runtime facts after exact RC11 command projection.

    Preserve every existing cause first. Only a uniquely identified executed
    effect may unlock chain completion; the start trigger still comes exclusively
    from the runtime trace. RC9/V2 retain all temporal-barrier and cause policies.
    """
    projected = project_exact_effect_commands_rc11(result, registry)
    existing = resolve_cause_rc9(projected)
    if isinstance(existing, dict):
        return existing
    if unique_effect_command_rc9(projected) is None:
        return None

    # Projection copies evidence but shares the dataclass's chain. Detach it before
    # completing facts so this diagnostic cannot mutate the caller or raw evidence.
    completed = replace(projected, chain=deepcopy(projected.chain))
    complete_confirmed_trace_chain(completed)
    return resolve_cause_rc9(completed)
