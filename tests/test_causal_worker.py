import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecorder
from causal_worker import CausalRecorderWorker


class DummyStream:
    async def events(self):
        if False:
            yield None


class DummyEnricher:
    async def enrich(self, change, record):
        return record


def state_event(entity_id, old, new, *, user_id=None, attrs=None):
    attributes = attrs or {"friendly_name": entity_id}
    return {
        "event_type": "state_changed",
        # These tests exercise capture/queue behavior, not retention expiry. A
        # fixed wall-clock timestamp eventually crosses the recorder's 12 h
        # retention boundary and makes the test fail for the wrong reason.
        "time_fired": datetime.now(timezone.utc).isoformat(),
        "data": {
            "entity_id": entity_id,
            "old_state": {
                "state": old,
                "attributes": attributes,
                "context": {"id": "old"},
            },
            "new_state": {
                "state": new,
                "attributes": attributes,
                "context": {"id": "new", "user_id": user_id},
            },
        },
    }


class TestCausalWorker(unittest.IsolatedAsyncioTestCase):
    async def test_effect_is_committed_before_enrichment(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = CausalRecorder(Path(tmp) / "journal.sqlite3", retention_hours=12)
            worker = CausalRecorderWorker(DummyStream(), recorder, DummyEnricher())
            await worker._capture_event(state_event("light.entree", "on", "off"))
            self.assertEqual(recorder.count(), 1)
            stored = recorder.latest("light.entree")
            self.assertEqual(stored.after_value, "off")
            self.assertEqual(stored.confidence, "indeterminate")
            self.assertEqual(worker.queue.qsize(), 1)
            recorder.close()

    async def test_direct_user_is_confirmed_without_enrichment_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = CausalRecorder(Path(tmp) / "journal.sqlite3", retention_hours=12)
            worker = CausalRecorderWorker(DummyStream(), recorder, DummyEnricher())
            await worker._capture_event(state_event("light.salon", "off", "on", user_id="abc"))
            stored = recorder.latest("light.salon")
            self.assertEqual(stored.origin_type, "user")
            self.assertEqual(stored.confidence, "confirmed")
            self.assertEqual(worker.queue.qsize(), 0)
            recorder.close()

    async def test_sensor_is_recorded_without_expensive_enrichment(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = CausalRecorder(Path(tmp) / "journal.sqlite3", retention_hours=12)
            worker = CausalRecorderWorker(DummyStream(), recorder, DummyEnricher())
            await worker._capture_event(state_event("sensor.temperature", "20", "20.1"))
            self.assertEqual(recorder.count(), 1)
            self.assertEqual(worker.queue.qsize(), 0)
            recorder.close()


if __name__ == "__main__":
    unittest.main()
