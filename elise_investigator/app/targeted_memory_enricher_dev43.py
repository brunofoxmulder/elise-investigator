from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord
from combined_trigger_condition_factors import combined_trigger_condition_factors
from targeted_memory_enricher_dev41 import TargetedMemoryEnricher as Dev41TargetedMemoryEnricher


class TargetedMemoryEnricher(Dev41TargetedMemoryEnricher):
    """Dev.43: attach a proven conjunction when trigger predicates repeat as true conditions.

    The existing deterministic reason remains untouched. A combined factor set is
    only allowed when at least two supported predicates are both configured as
    triggers and are proven true on the executed path leading to the target.
    """

    async def _label_factors(self, factors: list[dict[str, Any]]) -> None:
        for factor in factors:
            entity_id = str(factor.get("proof_entity_id") or "")
            if not entity_id:
                continue
            try:
                state = await self.ha.get_state(entity_id)
            except Exception:
                continue
            if not isinstance(state, dict):
                continue
            attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            if attrs.get("friendly_name"):
                factor["label"] = str(attrs["friendly_name"])
            if attrs.get("unit_of_measurement"):
                factor["unit"] = str(attrs["unit_of_measurement"])

    async def _reason_from_detail(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
        run_id: str | None,
    ):
        result = await super()._reason_from_detail(
            record, source_entity_id, source_name, source_kind, detail, run_id
        )
        # Never replace factors that existed before this enrichment. Dev.43 is
        # additive and only supersedes the single dev.41 projection generated from
        # the same trace later in the call chain.
        if not record.factors and result[0]:
            factors = combined_trigger_condition_factors(detail, record.entity_id)
            if len(factors) >= 2:
                await self._label_factors(factors)
                record.factors = factors
        return result

    async def enrich(self, records: list[CausalRecord]) -> bool:
        had_factors = {
            item.record_id: bool(item.factors)
            for item in records
            if item.record_id is not None
        }
        changed = await super().enrich(records)
        combined_changed = False
        for original in records:
            if original.record_id is None or had_factors.get(original.record_id):
                continue
            if not original.factors or len(original.factors) < 2:
                continue
            current = self.recorder.get(original.record_id)
            if current is None:
                continue
            current.factors = original.factors
            self.recorder.update(current)
            combined_changed = True
        return changed or combined_changed
