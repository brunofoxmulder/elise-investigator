from __future__ import annotations

import re

from activity_reader_dev63 import ActivityTraceReader as Dev63ActivityTraceReader
from activity_reader_dev70 import _functional_entries
from activity_reader_dev61 import _sorted_usable
from activity_reader_dev60 import _native_message, _native_source, _origin
from targeted_memory_enricher_v2 import TargetedMemoryEnricherV2

_RAW_PROVIDER_TRIGGER = re.compile(r"^\s*triggered\s+by\b", re.IGNORECASE)
_COVER_TERMINALS = {"open", "closed"}
_COVER_MOVING = {"opening", "closing"}


def _raw_provider_reason(value: object) -> bool:
    return isinstance(value, str) and bool(_RAW_PROVIDER_TRIGGER.match(value))


def _cover_partial_episode_carrier(fact, entries, entity_id):
    """Return the immediately preceding attributed cover movement row when safe.

    Home Assistant can finish a partial cover movement in state ``open`` even when the
    motor was *closing* (for example 90 % -> 30 %). The historical dev.61 carrier only
    accepted opening->open and closing->closed, so a valid partial reposition could lose
    its automation context at the terminal ``open`` row.

    This fallback is deliberately cover-only and adjacency-only: same entity, immediately
    previous usable state row, movement state opening/closing, terminal state open/closed.
    No elapsed-time correlation is used.
    """
    if not entity_id.startswith("cover.") or not isinstance(fact, dict):
        return fact
    terminal = str(fact.get("state") or "").casefold()
    if terminal not in _COVER_TERMINALS:
        return fact

    usable = _sorted_usable(entries, entity_id)
    try:
        index = usable.index(fact)
    except ValueError:
        return fact
    if index + 1 >= len(usable):
        return fact

    previous = usable[index + 1]
    movement = str(previous.get("state") or "").casefold()
    if movement not in _COVER_MOVING:
        return fact
    if terminal == "closed" and movement != "closing":
        return fact

    origin, _, _ = _origin(previous)
    if origin != "unknown" or _native_message(previous) or _native_source(previous):
        return previous
    return fact


class ActivityTraceReaderV2(Dev63ActivityTraceReader):
    """Activity/Logbook evidence reader with V2 causal semantics.

    The evidence plumbing intentionally stops at dev.63: Activity fact selection,
    explicit HA context linkage and cover movement attribution are reused. The causal
    policy chain dev.68 -> dev.70 -> dev.71 -> dev.72 -> dev.73 is not inherited.

    V2 adds only bounded evidence rules:
    - collapse newer same-functional-state refresh rows when a real boundary is visible;
    - use TargetedMemoryEnricherV2 as the single trace semantic resolver/renderer;
    - disable the legacy one-upstream-hop prose concatenation;
    - for covers only, recover attribution from the immediately preceding movement row
      when a partial reposition ends in HA state ``open``.
    """

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            TargetedMemoryEnricherV2(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )

    async def _record_from_entries(
        self,
        entity_id,
        entries,
        *,
        end_time,
        hours: int,
        allow_upstream: bool,
    ):
        functional = _functional_entries(entries, entity_id)
        record = await super()._record_from_entries(
            entity_id,
            functional,
            end_time=end_time,
            hours=hours,
            # V2 forbids the legacy post-resolver text mutation performed by dev.61.
            allow_upstream=False,
        )
        if record is None:
            return None

        # Cover-only terminal episode recovery. This runs only when the normal Activity
        # and explicit-context readers still report unknown, so validated attribution for
        # lamps, switches, users and already-correct covers is untouched.
        if entity_id.startswith("cover.") and record.origin_type == "unknown":
            trigger = record.trigger if isinstance(record.trigger, dict) else {}
            fact = trigger.get("ha_activity_fact")
            if isinstance(fact, dict):
                attribution = _cover_partial_episode_carrier(fact, functional, entity_id)
                if attribution is not fact:
                    origin_type, source_entity_id, source_name = _origin(attribution)
                    if origin_type != "unknown":
                        record.origin_type = origin_type
                        record.source_entity_id = source_entity_id
                        record.source_name = source_name
                        record.trigger["ha_activity_attribution"] = dict(attribution)
                        record.trigger["cover_episode_attribution"] = "adjacent_movement_row"
                        source_hint = _native_source(attribution)
                        record.trigger["ha_activity_source_hint"] = source_hint

                        message = _native_message(attribution)
                        if message:
                            record.reason = message
                            record.reason_code = "ha_2026_9_activity_native"

                        if (
                            origin_type in {"automation", "script"}
                            and self.trace_helper is not None
                        ):
                            trace_reason, run_id, human_cause = await self.trace_helper._trace_reason(
                                record, source_entity_id, source_name, origin_type
                            )
                            if trace_reason:
                                record.reason = trace_reason
                                record.reason_code = "ha_logbook+exact_trace"
                                record.trace_run_id = run_id
                                if human_cause:
                                    record.trigger["human_cause"] = human_cause

                        if not record.reason and source_hint:
                            record.reason = source_hint
                            record.reason_code = "ha_2026_9_activity_source_hint"

        # Provider prose is evidence only. V2 never exposes Home Assistant's English
        # `triggered by ...` sentence as its human causal explanation.
        if (
            record.origin_type in {"automation", "script"}
            and _raw_provider_reason(record.reason)
        ):
            trigger = record.trigger if isinstance(record.trigger, dict) else {}
            trigger["suppressed_native_reason"] = record.reason
            trigger["suppressed_native_reason_code"] = record.reason_code
            record.trigger = trigger
            record.reason = None
            record.reason_code = None

        return record
