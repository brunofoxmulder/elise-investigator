from __future__ import annotations

import re

from activity_reader_dev72 import ActivityTraceReader as Dev72ActivityTraceReader


_RAW_PROVIDER_TRIGGER = re.compile(r"^\s*triggered\s+by\b", re.IGNORECASE)


def _is_raw_provider_trigger_text(value: object) -> bool:
    """Return True only for HA/provider trigger prose that must never reach the UI.

    The phrase remains useful evidence, but it is not a user-facing causal sentence.
    Matching the text itself rather than one reason_code closes both observed terrain
    paths (`ha_2026_9_activity_native` and `ha_2026_9_activity_source_hint`) and future
    equivalent codes without touching exact-trace reasons.
    """
    return isinstance(value, str) and bool(_RAW_PROVIDER_TRIGGER.match(value))


class ActivityTraceReader(Dev72ActivityTraceReader):
    """dev.73: dev.72 semantics + terminal native-provider prose firewall."""

    async def _record_from_entries(
        self,
        entity_id,
        entries,
        *,
        end_time,
        hours: int,
        allow_upstream: bool,
    ):
        record = await super()._record_from_entries(
            entity_id,
            entries,
            end_time=end_time,
            hours=hours,
            allow_upstream=allow_upstream,
        )
        if record is None:
            return None

        if (
            record.origin_type in {"automation", "script"}
            and _is_raw_provider_trigger_text(record.reason)
        ):
            # Keep the native provider sentence only as evidence. At this point the
            # exact-trace helper has already had its chance to replace it with a proven
            # semantic reason. If it could not, fail closed and let the presentation
            # layer fall back to the identified automation/script rather than leak raw
            # provider English or invent a stronger explanation.
            trigger = record.trigger if isinstance(record.trigger, dict) else {}
            trigger["suppressed_native_reason"] = record.reason
            trigger["suppressed_native_reason_code"] = record.reason_code
            record.trigger = trigger
            record.reason = None
            record.reason_code = None

        return record
