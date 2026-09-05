from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from targeted_memory_enricher_dev57 import TargetedMemoryEnricher


class TestDev57ActivityTraceFallback(unittest.IsolatedAsyncioTestCase):
    def test_native_activity_reason_has_priority(self):
        self.assertEqual(
            TargetedMemoryEnricher._native_reason({"context_source": "state of sensor.battery"}),
            "state of sensor.battery",
        )

    async def test_trace_fallback_is_bounded_to_activity_identified_source(self):
        ha = object()
        investigator = object()
        enricher = TargetedMemoryEnricher(ha, investigator)
        enricher._trace_helper._trace_reason = AsyncMock(
            return_value=("la condition batterie a été satisfaite", "run-1", {"kind": "state"})
        )
        anchor = object()
        reason, run_id, human, backend = await enricher._targeted_trace_reason(
            anchor, "automation", "automation.charge_aspirateur", "Charge aspirateur"
        )
        self.assertEqual(reason, "la condition batterie a été satisfaite")
        self.assertEqual(run_id, "run-1")
        self.assertEqual(human, {"kind": "state"})
        enricher._trace_helper._trace_reason.assert_awaited_once_with(
            anchor, "automation.charge_aspirateur", "Charge aspirateur", "automation"
        )

    async def test_unknown_origin_never_reads_trace(self):
        enricher = TargetedMemoryEnricher(object(), object())
        enricher._trace_helper._trace_reason = AsyncMock()
        result = await enricher._targeted_trace_reason(
            object(), "unknown", None, None
        )
        self.assertEqual(result, (None, None, None, None))
        enricher._trace_helper._trace_reason.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
