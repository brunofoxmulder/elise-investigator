"""RC12 causal semantics, with exact-event persistence after proof resolution."""
from __future__ import annotations

import logging
from copy import deepcopy

from activity_reader_rc12 import ActivityTraceReaderRC12
from activity_reader_dev60 import _dt
from causal_resolver_rc11 import unique_effect_command_rc11
from causal_resolver_rc12 import resolve_cause_rc12
from cover_cause_v2 import periodic_position_decision
from proof_archive_rc13 import POLICY, PROOF_KEY
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_rc12 import TargetedMemoryEnricherRC12

_LOGGER = logging.getLogger(__name__)


class ProofEnricherRC13(TargetedMemoryEnricherRC12):
    async def _reason_from_detail(self, record, source_entity_id, source_name, source_kind, detail, run_id):
        # Same resolution order and renderer as RC12, evaluated once. Persistence
        # observes the result; it cannot supply inputs to the causal resolver.
        result = self._result(record, source_entity_id, source_name, source_kind, detail)
        registry = await self._registry_entry(record.entity_id)
        cause = resolve_cause_rc12(result, registry)
        if not isinstance(cause, dict):
            return None, run_id, None
        if record.entity_id.startswith("cover.") and cause.get("origin") == "automation_trigger":
            command = unique_effect_command_rc11(result, registry)
            trigger = cause.get("detail") if isinstance(cause.get("detail"), dict) else None
            enriched = periodic_position_decision(result, command or {}, trigger)
            if isinstance(enriched, dict):
                cause = enriched
        text = await self.renderer.render(cause)
        if text and run_id:
            try:
                command = unique_effect_command_rc11(result, registry)
                if isinstance(command, dict):
                    carrier = (record.trigger or {}).get("ha_activity_attribution") or {}
                    observed = _dt(carrier.get("when"))
                    nodes = (detail.get("trace") or {}).get(command.get("path"), [])
                    nodes = nodes if isinstance(nodes, list) else [nodes]
                    times = [_dt(node.get("timestamp")) for node in nodes if isinstance(node, dict)]
                    matches = [t for t in times if t is not None and observed is not None
                               and 0 <= (observed - t).total_seconds() <= 5]
                    if len(matches) != 1:
                        return text, run_id, _compact_human_cause(cause)
                    record.trigger = dict(record.trigger or {})
                    # Evaluated facts and command provenance, not whole configurations.
                    record.trigger[PROOF_KEY] = deepcopy({
                        "policy": POLICY, "run_id": run_id, "source": source_entity_id,
                        "command": command, "cause": cause,
                        "execution_time": matches[0].isoformat(),
                        "trace_context": detail.get("context"),
                        "trace_timestamp": detail.get("timestamp"),
                    })
            except Exception as exc:
                _LOGGER.warning("Proof snapshot unavailable (%s)", type(exc).__name__)
        return text or None, run_id, _compact_human_cause(cause)


class ActivityTraceReaderRC13(ActivityTraceReaderRC12):
    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.archive = None
        self.archive_failures = 0
        if trace_investigator is not None:
            self.trace_helper = ProofEnricherRC13(ha, trace_investigator)

    async def _record_from_entries(self, entity_id, entries, **kwargs):
        record = await super()._record_from_entries(entity_id, entries, **kwargs)
        if record is not None and self.archive is not None:
            try:
                if record.reason_code == "ha_logbook+exact_trace":
                    self.archive.save(record)
                elif not record.reason:
                    self.archive.restore(record)
            except Exception as exc:
                # A full/unavailable local disk cannot break a live RC12 explanation.
                self.archive_failures += 1
                _LOGGER.warning("Proof archive unavailable (%s)", type(exc).__name__)
        return record
