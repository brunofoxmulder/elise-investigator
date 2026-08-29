from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord, CausalRecorder
from targeted_memory_enricher_dev43 import TargetedMemoryEnricher as Dev43TargetedMemoryEnricher
from targeted_memory_enricher_dev44 import TargetedMemoryEnricher

BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
ENTITY = "cover.volet_salon_2"


def iso(seconds: float) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


class DummyHA:
    pass


class DummyInvestigator:
    pass


class TestDev44CoverTerminalStartRetry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")
        self.enricher = TargetedMemoryEnricher(DummyHA(), DummyInvestigator()).bind_recorder(self.recorder)

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def _record(self, **kwargs):
        return self.recorder.record(CausalRecord(entity_id=ENTITY, entity_name="Volet salon", confidence="confirmed", **kwargs))

    async def test_unknown_opening_start_is_retried_when_terminal_arrives(self):
        start = self._record(
            event_time=iso(1.821), event_kind="opening", before_value="open", after_value="opening", origin_type="unknown"
        )
        terminal = self._record(
            event_time=iso(14.989), event_kind="opened", before_value="opening", after_value="open", origin_type="unknown"
        )

        calls = []

        async def fake_dev43_enrich(instance, records):
            calls.append([item.record_id for item in records])
            if len(calls) == 1:
                current = instance.recorder.get(start.record_id)
                current.origin_type = "automation"
                current.source_entity_id = "automation.gestion_volet_salon_avec_soleil_et_saison"
                current.source_name = "Gestion volet salon avec soleil et saison"
                current.reason = "le soleil n'était plus dans la zone nécessitant de protéger le salon"
                instance.recorder.update(current)
            return True

        with patch.object(Dev43TargetedMemoryEnricher, "enrich", new=fake_dev43_enrich):
            self.assertTrue(await self.enricher.enrich([terminal]))

        self.assertEqual(calls, [[start.record_id], [terminal.record_id]])

    async def test_resolved_start_is_not_retried(self):
        self._record(
            event_time=iso(1.821), event_kind="opening", before_value="open", after_value="opening",
            origin_type="automation", source_entity_id="automation.gestion_volet_salon_avec_soleil_et_saison",
            reason="cause déjà prouvée"
        )
        terminal = self._record(
            event_time=iso(14.989), event_kind="opened", before_value="opening", after_value="open", origin_type="unknown"
        )

        mocked = AsyncMock(return_value=True)
        with patch.object(Dev43TargetedMemoryEnricher, "enrich", mocked):
            self.assertTrue(await self.enricher.enrich([terminal]))
        self.assertEqual(mocked.await_count, 1)

    async def test_incoherent_opening_to_closed_never_retries_start(self):
        self._record(
            event_time=iso(1.821), event_kind="opening", before_value="open", after_value="opening", origin_type="unknown"
        )
        terminal = self._record(
            event_time=iso(14.989), event_kind="closed", before_value="opening", after_value="closed", origin_type="unknown"
        )

        mocked = AsyncMock(return_value=False)
        with patch.object(Dev43TargetedMemoryEnricher, "enrich", mocked):
            await self.enricher.enrich([terminal])
        self.assertEqual(mocked.await_count, 1)


if __name__ == "__main__":
    unittest.main()
