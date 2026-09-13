from __future__ import annotations

from typing import Any

from causal_resolver_rc9 import resolve_cause_rc9, unique_effect_command_rc9
from models import InvestigationResult
from trace_command_projection_rc11 import project_exact_effect_commands_rc11


def unique_effect_command_rc11(
    result: InvestigationResult,
    registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    projected = project_exact_effect_commands_rc11(result, registry)
    return unique_effect_command_rc9(projected)


def resolve_cause_rc11(
    result: InvestigationResult,
    registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Feed exact runtime/config evidence into the unchanged RC9 resolver chain."""
    projected = project_exact_effect_commands_rc11(result, registry)
    return resolve_cause_rc9(projected)

