from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord, CausalRecorder
from targeted_memory_enricher_dev45 import TargetedMemoryEnricher

BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
ENTITY = "cover.volet_salon_2"
AUTOMATION = "automation.gestion_volet_salon_avec_soleil_et_saison"


def iso(seconds: float) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


class DummyHA:
    async def get_logbook(self, entity_id, start, end):
        return [{
            "entity_id": ENTITY,
            "when": iso(2.01),
            "state": "opening",
            "context_id": "start-context",
            "context_event_type": "automation_triggered",
            "context_entity_id": AUTOMATION,
            "context_entity_id_name": "Gestion volet salon avec soleil et saison",
        }]


class DummyInvestigator:
    async def _best_trace_for_source(self, source_entity_id, event_time):
        return {
            "summary": {"run_id": "run-dev45"},
            "detail": {
                "trace": {
                    "action/4": [{
                        "timestamp": iso(1.72),
                        "result": {"params": {
                            "domain": "cover",
                            "service": "set_cover_position",
                            "target": {"entity_id": ENTITY},
                            "service_data": {"position": 100},
                        }},
                    }]
                },
                "config": {"actions": []},
            },
        }


class TestDev45CoverTargetFallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")
        self.enricher = TargetedMemoryEnricher(DummyHA(), DummyInvestigator()).bind_recorder(self.recorder)

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def _record(self, **kwargs):
        return self.recorder.record(CausalRecord(entity_id=ENTITY, entity_name="Volet salon", confidence="confirmed", **kwargs))

    async def test_terminal_gets_proven_calculated_target_when_business_reason_unavailable(self):
        start = self._record(event_time=iso(2.01), event_kind="opening", before_value="open", after_value="opening", origin_type="unknown")
        terminal = self._record(event_time=iso(15.17), event_kind="opened", before_value="opening", after_value="open", origin_type="unknown")

        self.assertTrue(await self.enricher.enrich([terminal]))

        start_after = self.recorder.get(start.record_id)
        terminal_after = self.recorder.get(terminal.record_id)
        self.assertEqual(start_after.origin_type, "automation")
        self.assertEqual(start_after.reason_code, "cover_episode_proven_set_position_target")
        self.assertIn("100 %", start_after.reason)
        self.assertEqual(terminal_after.origin_type, "automation")
        self.assertEqual(terminal_after.reason, start_after.reason)
        self.assertEqual(terminal_after.reason_code, "cover_episode_continuity")
        self.assertEqual(terminal_after.trace_run_id, "run-dev45")

    async def test_no_fallback_without_unique_set_position_proof(self):
        source = self._record(
            event_time=iso(2.01), event_kind="opening", before_value="open", after_value="opening",
            origin_type="automation", source_entity_id=AUTOMATION
        )
        detail = {"trace": {}}
        self.assertIsNone(TargetedMemoryEnricher._unique_set_position(detail, ENTITY))
        self.assertIsNone(source.reason)


if __name__ == "__main__":
    unittest.main()
