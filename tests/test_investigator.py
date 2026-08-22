import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
sys.path.insert(0, str(APP))

from investigator import Investigator
from models import InvestigationRequest


class FakeHA:
    def __init__(self, *, history, logbook, states=None):
        self.history = history
        self.logbook = logbook
        self.states = states or []

    async def get_config(self): return {"time_zone": "Europe/Paris", "version": "2026.8.2"}
    async def get_state(self, entity_id):
        for x in self.states:
            if x["entity_id"] == entity_id: return x
        return {"entity_id": entity_id, "state": "on", "attributes": {"friendly_name": "Test"}, "last_changed": "2026-08-22T16:00:00+00:00", "last_updated": "2026-08-22T16:00:00+00:00"}
    async def get_all_states(self): return self.states
    async def get_entity_registry(self, entity_id): return {"entity_id": entity_id, "unique_id": "stable", "platform": "test"}
    async def get_history(self, *a, **k): return self.history
    async def get_logbook(self, *a, **k): return self.logbook
    async def list_traces(self, *a, **k): return []
    async def get_trace(self, *a, **k): return None
    async def get_automation_config(self, *a, **k): return None
    async def get_script_config(self, *a, **k): return None
    async def get_scene_config(self, *a, **k): return None


class InvestigatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_user_beats_reverse_search(self):
        hist = [
            {"state":"on","attributes":{"friendly_name":"Lampe"},"last_changed":"2026-08-22T16:20:00+00:00","last_updated":"2026-08-22T16:20:00+00:00"},
            {"state":"off","attributes":{"friendly_name":"Lampe"},"last_changed":"2026-08-22T16:22:00+00:00","last_updated":"2026-08-22T16:22:00+00:00"},
        ]
        log = [{"entity_id":"light.test","when":"2026-08-22T16:22:00+00:00","context_user_id":"abc","message":"turned off"}]
        inv = Investigator(FakeHA(history=hist, logbook=log))
        result = await inv.investigate(InvestigationRequest(entity_id="light.test", observed_time="2026-08-22T18:22:00+02:00"))
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.cause["type"], "user")
        self.assertEqual(result.observed["before"], "on")
        self.assertEqual(result.observed["after"], "off")

    async def test_sensor_upstream_is_not_invented(self):
        hist = [
            {"state":"off","attributes":{"friendly_name":"Mouvement"},"last_changed":"2026-08-22T16:52:30+00:00","last_updated":"2026-08-22T16:52:30+00:00"},
            {"state":"on","attributes":{"friendly_name":"Mouvement"},"last_changed":"2026-08-22T16:52:37+00:00","last_updated":"2026-08-22T16:52:37+00:00"},
        ]
        inv = Investigator(FakeHA(history=hist, logbook=[]))
        result = await inv.investigate(InvestigationRequest(entity_id="binary_sensor.motion", observed_time="2026-08-22T18:52:37+02:00"))
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.cause["type"], "sensor")
        self.assertTrue(any("cause physique" in x.lower() for x in result.limits))

    async def test_user_declaration_does_not_become_system_proof(self):
        hist = [
            {"state":"cool","attributes":{"friendly_name":"Clim","temperature":21},"last_changed":"2026-08-22T15:52:00+00:00","last_updated":"2026-08-22T15:52:00+00:00"},
            {"state":"cool","attributes":{"friendly_name":"Clim","temperature":20},"last_changed":"2026-08-22T15:52:00+00:00","last_updated":"2026-08-22T16:13:52+00:00"},
        ]
        inv = Investigator(FakeHA(history=hist, logbook=[]))
        result = await inv.investigate(InvestigationRequest(entity_id="climate.salon", observed_time="2026-08-22T18:13:52+02:00", attribute="temperature", observed_value=20, user_declaration="Je l'ai fait à la voix"))
        self.assertEqual(result.cause["type"], "user_declaration")
        self.assertFalse(result.cause["system_confirmed"])
        self.assertEqual(result.event_type, "attribute_change")


if __name__ == "__main__":
    unittest.main()
