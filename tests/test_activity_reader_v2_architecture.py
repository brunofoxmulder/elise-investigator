from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev63 import ActivityTraceReader as Dev63ActivityTraceReader
from activity_reader_v2 import ActivityTraceReaderV2
from causal_recorder import CausalRecord
from targeted_memory_enricher_v2 import TargetedMemoryEnricherV2


class _HA:
    async def get_state(self, entity_id):
        return {"entity_id": entity_id, "attributes": {}}


class _TraceInvestigator:
    pass


def _record(*, origin="automation", reason=None, reason_code=None):
    return CausalRecord(
        entity_id="light.test",
        event_time="2026-09-11T10:00:00+00:00",
        event_kind="turned_on",
        after_value="on",
        origin_type=origin,
        source_entity_id="automation.test" if origin == "automation" else None,
        source_name="Automation test" if origin == "automation" else None,
        reason=reason,
        reason_code=reason_code,
        trigger={},
        confidence="confirmed",
    )


class ActivityReaderV2ArchitectureTests(unittest.IsolatedAsyncioTestCase):
    def test_reader_uses_v2_enricher_not_dev71_72_73_policy_chain(self):
        reader = ActivityTraceReaderV2(_HA(), _TraceInvestigator())
        self.assertIsInstance(reader.trace_helper, TargetedMemoryEnricherV2)
        self.assertTrue(issubclass(ActivityTraceReaderV2, Dev63ActivityTraceReader))

    async def test_raw_provider_trigger_text_is_suppressed_at_v2_boundary(self):
        record = _record(
            reason="triggered by state of binary_sensor.motion",
            reason_code="ha_2026_9_activity_native",
        )
        reader = ActivityTraceReaderV2(_HA())
        with patch.object(
            Dev63ActivityTraceReader,
            "_record_from_entries",
            new=AsyncMock(return_value=record),
        ):
            result = await reader._record_from_entries(
                "light.test",
                [],
                end_time=datetime.now(timezone.utc),
                hours=12,
                allow_upstream=True,
            )
        self.assertIsNone(result.reason)
        self.assertIsNone(result.reason_code)
        self.assertEqual(
            result.trigger.get("suppressed_native_reason"),
            "triggered by state of binary_sensor.motion",
        )

    async def test_valid_v2_reason_is_preserved(self):
        record = _record(reason="un mouvement a été détecté", reason_code="v2_exact_trace")
        reader = ActivityTraceReaderV2(_HA())
        with patch.object(
            Dev63ActivityTraceReader,
            "_record_from_entries",
            new=AsyncMock(return_value=record),
        ):
            result = await reader._record_from_entries(
                "light.test",
                [],
                end_time=datetime.now(timezone.utc),
                hours=12,
                allow_upstream=True,
            )
        self.assertEqual(result.reason, "un mouvement a été détecté")
        self.assertEqual(result.reason_code, "v2_exact_trace")

    async def test_direct_user_reason_is_never_filtered(self):
        record = _record(origin="user", reason=None, reason_code="logbook_user_context")
        reader = ActivityTraceReaderV2(_HA())
        with patch.object(
            Dev63ActivityTraceReader,
            "_record_from_entries",
            new=AsyncMock(return_value=record),
        ):
            result = await reader._record_from_entries(
                "light.test",
                [],
                end_time=datetime.now(timezone.utc),
                hours=12,
                allow_upstream=True,
            )
        self.assertEqual(result.origin_type, "user")
        self.assertEqual(result.reason_code, "logbook_user_context")


if __name__ == "__main__":
    unittest.main()
