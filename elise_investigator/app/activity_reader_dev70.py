from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from activity_reader_dev60 import _dt, _usable
from activity_reader_dev68 import ActivityTraceReader as Dev68ActivityTraceReader
from targeted_memory_enricher_dev70 import TargetedMemoryEnricher as Dev70TargetedTraceHelper


def _functional_entries(entries: list[dict[str, Any]], entity_id: str) -> list[dict[str, Any]]:
    """Drop only newer same-state refresh rows when a real prior state boundary exists.

    The oldest row of the current identical-state run is the actual transition into the
    current functional state. This keeps the terminal `open`/`closed` fact while allowing
    the immediately preceding `opening`/`closing` row to carry native attribution.
    No arbitrary time window is used. If the state boundary is not visible, nothing is
    changed and the reader fails closed as before.
    """
    usable = [entry for entry in entries if isinstance(entry, dict) and _usable(entry, entity_id)]
    usable.sort(
        key=lambda entry: _dt(entry.get("when")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    if len(usable) < 2:
        return entries

    state = str(usable[0].get("state") or "").casefold()
    run: list[dict[str, Any]] = []
    boundary_found = False
    for entry in usable:
        if str(entry.get("state") or "").casefold() == state:
            run.append(entry)
            continue
        boundary_found = True
        break

    if not boundary_found or len(run) <= 1:
        return entries

    keep = run[-1]
    remove_ids = {id(entry) for entry in run[:-1]}
    return [entry for entry in entries if id(entry) not in remove_ids or entry is keep]


class ActivityTraceReader(Dev68ActivityTraceReader):
    """dev.70: dev.68 causal logic + deterministic functional-state row selection."""

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            Dev70TargetedTraceHelper(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )

    async def _record_from_entries(
        self,
        entity_id: str,
        entries: list[dict[str, Any]],
        *,
        end_time,
        hours: int,
        allow_upstream: bool,
    ):
        return await super()._record_from_entries(
            entity_id,
            _functional_entries(entries, entity_id),
            end_time=end_time,
            hours=hours,
            allow_upstream=allow_upstream,
        )
