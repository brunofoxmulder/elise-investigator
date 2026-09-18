"""Native HA Logbook attribution, replayed through the current RC13 reader.

Fixtures reproduce the observed field structure with generic entity names.
No Home Assistant instance or cloud service is contacted.
"""

import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "elise_investigator/app"))

from activity_reader_dev60 import _origin
from activity_reader_rc13 import ActivityTraceReaderRC13
from causal_response import answer_from_record
from memory_response_dev34 import cause_found


def entry(entity="light.fixture", state="off", **overrides):
    return {
        "entity_id": entity,
        "state": state,
        "when": "2026-09-18T10:18:01+00:00",
        "context_entity_id": "assist_satellite.fixture",
        "context_entity_id_name": "Fixture voice",
        "context_state": "listening",
        **overrides,
    }


class FakeHA:
    def __init__(self, entries):
        self.entries = entries

    async def get_logbook(self, *args):
        return deepcopy(self.entries)


class NativeAssistOriginTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_reader_explains_native_voice_on_and_off(self):
        for state in ("on", "off"):
            with self.subTest(state=state):
                fact = entry(state=state)
                record = await ActivityTraceReaderRC13(FakeHA([fact])).investigate(fact["entity_id"])
                self.assertEqual(record.origin_type, "user")
                self.assertTrue(cause_found(record))
                self.assertIsNone(record.source_entity_id)
                self.assertEqual(record.event_time, fact["when"])
                self.assertEqual(record.after_value, state)
                self.assertEqual(record.trigger["ha_activity_fact"], fact)
                self.assertNotIn("context_user_id", fact)
                answer = answer_from_record(record, now=datetime(2026, 9, 18, 10, 19, tzinfo=timezone.utc))
                self.assertIn("commande utilisateur Home Assistant", answer)

    async def test_native_origin_rule_is_independent_of_target_domain(self):
        for entity, state in (("switch.fixture", "on"), ("climate.fixture", "off"),
                              ("cover.fixture", "closed")):
            with self.subTest(entity=entity):
                record = await ActivityTraceReaderRC13(FakeHA([entry(entity, state)])).investigate(entity)
                self.assertEqual(record.origin_type, "user")
                self.assertTrue(cause_found(record))

    def test_automation_and_script_keep_priority_with_inherited_user(self):
        for domain in ("automation", "script"):
            with self.subTest(domain=domain):
                source = f"{domain}.fixture"
                fact = entry(context_entity_id=source, context_user_id="fixture-user")
                self.assertEqual(_origin(fact), (domain, source, "Fixture voice"))

    def test_authenticated_user_contract_is_preserved(self):
        self.assertEqual(_origin(entry(context_entity_id=None, context_user_id="fixture-user")),
                         ("user", None, None))

    def test_satellite_without_listening_proof_remains_unknown(self):
        for state in (None, "", "idle", "processing", "responding", "unavailable"):
            with self.subTest(state=state):
                self.assertEqual(_origin(entry(context_state=state)), ("unknown", None, None))

    def test_similar_name_or_wrong_domain_does_not_prove_voice_origin(self):
        for source in (None, "", "assist_satellite.", "sensor.assist_satellite_fixture",
                       "conversation.fixture", "light.fixture"):
            with self.subTest(source=source):
                self.assertEqual(_origin(entry(context_entity_id=source)), ("unknown", None, None))

    async def test_nearby_satellite_event_is_not_used_as_proof(self):
        fact = entry(context_entity_id=None, context_state=None)
        nearby = {"entity_id": "assist_satellite.fixture", "state": "listening",
                  "when": "2026-09-18T10:18:00+00:00"}
        record = await ActivityTraceReaderRC13(FakeHA([nearby, fact])).investigate("light.fixture")
        self.assertEqual(record.origin_type, "unknown")
        self.assertFalse(cause_found(record))

    async def test_previous_voice_command_does_not_explain_new_unknown_change(self):
        old = entry(state="on", when="2026-09-18T10:18:00+00:00")
        current = entry(context_entity_id=None, context_state=None)
        record = await ActivityTraceReaderRC13(FakeHA([old, current])).investigate("light.fixture")
        self.assertEqual(record.origin_type, "unknown")
        self.assertEqual(record.event_time, current["when"])
        self.assertFalse(cause_found(record))

    def test_raw_evidence_is_not_modified(self):
        fact = entry()
        original = deepcopy(fact)
        _origin(fact)
        self.assertEqual(fact, original)


if __name__ == "__main__":
    unittest.main()
