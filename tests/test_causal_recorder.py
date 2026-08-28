import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from causal_recorder import CausalRecord, CausalRecorder


class TestCausalRecorder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "causal.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_latest_record_survives_reopen(self):
        now = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)
        with CausalRecorder(self.path, retention_hours=12) as recorder:
            recorder.record(
                CausalRecord(
                    entity_id="light.entree",
                    entity_name="Lampe entrée",
                    event_time=(now - timedelta(minutes=2)).isoformat(),
                    event_kind="turned_off",
                    before_value="on",
                    after_value="off",
                    origin_type="automation",
                    reason="il n'y avait plus de mouvement",
                    reason_code="no_motion",
                    confidence="confirmed",
                    trace_run_id="run-123",
                ),
                now=now,
            )
            self.assertEqual(recorder.count(), 1)

        with CausalRecorder(self.path, retention_hours=12) as recorder:
            item = recorder.latest("light.entree")
            self.assertIsNotNone(item)
            self.assertEqual(item.entity_name, "Lampe entrée")
            self.assertEqual(item.after_value, "off")
            self.assertEqual(item.reason, "il n'y avait plus de mouvement")
            self.assertEqual(item.trace_run_id, "run-123")
            self.assertEqual(item.confidence, "confirmed")

    def test_retention_prunes_old_records_only(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        with CausalRecorder(self.path, retention_hours=12) as recorder:
            recorder.record(
                CausalRecord(
                    entity_id="light.old",
                    event_time=(now - timedelta(hours=13)).isoformat(),
                    event_kind="turned_on",
                    after_value="on",
                ),
                now=now,
            )
            self.assertEqual(recorder.count(), 0)
            recorder.record(
                CausalRecord(
                    entity_id="light.recent",
                    event_time=(now - timedelta(hours=11, minutes=59)).isoformat(),
                    event_kind="turned_on",
                    after_value="on",
                ),
                now=now,
            )
            self.assertEqual(recorder.count(), 1)
            self.assertIsNotNone(recorder.latest("light.recent"))

    def test_change_retention_prunes_immediately(self):
        now = datetime.now(timezone.utc)
        with CausalRecorder(self.path, retention_hours=24) as recorder:
            recorder.record(
                CausalRecord(
                    entity_id="switch.test",
                    event_time=(now - timedelta(hours=13)).isoformat(),
                    event_kind="turned_off",
                    after_value="off",
                ),
                now=now,
            )
            self.assertEqual(recorder.count(), 1)
            recorder.set_retention_hours(12)
            self.assertEqual(recorder.count(), 0)

    def test_llm_payload_hides_automation_and_trace_details(self):
        item = CausalRecord(
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-08-28T09:12:00+00:00",
            event_kind="positioned",
            after_value=40,
            attribute="current_position",
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon_avec_soleil_et_saison",
            source_name="Gestion volet salon avec soleil et saison",
            reason="position du soleil et luminosité",
            trigger={"platform": "time_pattern", "minutes": "/10"},
            factors=[{"name": "luminosité", "value": 52000}],
            confidence="confirmed",
            trace_run_id="secret-internal-run-id",
            trace_path="action/0/choose/2",
        )
        payload = item.llm_payload()
        self.assertEqual(
            payload,
            {
                "entity": "Volet salon",
                "event": "positioned",
                "time": "2026-08-28T09:12:00+00:00",
                "confidence": "confirmed",
                "value": 40,
                "attribute": "current_position",
                "reason": "position du soleil et luminosité",
            },
        )
        text = str(payload)
        self.assertNotIn("automation.gestion", text)
        self.assertNotIn("secret-internal-run-id", text)
        self.assertNotIn("time_pattern", text)

    def test_direct_sources_are_minimal(self):
        alexa = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-08-28T10:03:18+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="alexa",
            confidence="confirmed",
        )
        self.assertEqual(alexa.llm_payload()["source"], "Alexa")
        self.assertNotIn("reason", alexa.llm_payload())

        user = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-08-28T10:05:00+00:00",
            event_kind="turned_off",
            after_value="off",
            origin_type="user",
            confidence="confirmed",
        )
        self.assertEqual(user.llm_payload()["source"], "utilisateur")

    def test_enrichment_updates_same_row(self):
        now = datetime.now(timezone.utc)
        with CausalRecorder(self.path, retention_hours=12) as recorder:
            item = recorder.record(
                CausalRecord(
                    entity_id="light.entree",
                    event_time=now.isoformat(),
                    event_kind="turned_off",
                    after_value="off",
                ),
                now=now,
            )
            original_id = item.record_id
            item.origin_type = "automation"
            item.reason = "il n'y avait plus de mouvement"
            item.confidence = "confirmed"
            recorder.update(item)
            self.assertEqual(recorder.count(), 1)
            stored = recorder.get(original_id)
            self.assertEqual(stored.record_id, original_id)
            self.assertEqual(stored.reason, "il n'y avait plus de mouvement")
            self.assertEqual(stored.confidence, "confirmed")

    def test_find_best_uses_time_and_value_without_ignoring_clue(self):
        now = datetime.now(timezone.utc)
        with CausalRecorder(self.path, retention_hours=12) as recorder:
            for minutes, value in ((10, "on"), (5, "off"), (1, "on")):
                recorder.record(
                    CausalRecord(
                        entity_id="light.entree",
                        event_time=(now - timedelta(minutes=minutes)).isoformat(),
                        event_kind="turned_on" if value == "on" else "turned_off",
                        after_value=value,
                    ),
                    now=now,
                )
            latest_off = recorder.find_best("light.entree", observed_value="off")
            self.assertEqual(latest_off.after_value, "off")
            timed_on = recorder.find_best(
                "light.entree",
                observed_time=(now - timedelta(minutes=9)).isoformat(),
                observed_value="on",
            )
            self.assertEqual(timed_on.after_value, "on")
            self.assertLess(abs((timed_on.normalized_time() - (now - timedelta(minutes=10))).total_seconds()), 1)
            self.assertIsNone(recorder.find_best("light.entree", observed_value="unseen"))

    def test_retention_bounds_are_enforced(self):
        with self.assertRaises(ValueError):
            CausalRecorder(self.path, retention_hours=0)
        with self.assertRaises(ValueError):
            CausalRecorder(self.path, retention_hours=73)


if __name__ == "__main__":
    unittest.main()
