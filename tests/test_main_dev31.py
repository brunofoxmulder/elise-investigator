import json
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from main_dev31 import (
    VERSION,
    _journal_only_for_request,
    _patch_manual_ui_route,
    stable_investigate,
)
from models import InvestigationRequest


class FakeRequest:
    def __init__(self, app, payload):
        self.app = app
        self._payload = payload

    async def json(self):
        return self._payload


class FakeRecorder:
    def __init__(self, record=None):
        self.record = record
        self.calls = []

    def find_best(self, entity_id, **kwargs):
        self.calls.append((entity_id, kwargs))
        return self.record


class ExplodingInvestigator:
    async def investigate(self, request):
        raise AssertionError("deep investigation must never run on stable /investigate")


class TestDev31StableInvestigate(unittest.IsolatedAsyncioTestCase):
    async def test_historical_investigate_path_reads_journal_and_preserves_why_contract(self):
        record = CausalRecord(
            entity_id="light.salle_de_bain",
            entity_name="Lampe salle de bain",
            event_time="2026-08-28T13:20:00+00:00",
            event_kind="turned_on",
            before_value="off",
            after_value="on",
            origin_type="automation",
            source_entity_id="automation.salle_de_bain",
            source_name="Nom technique secret",
            reason="un mouvement a été détecté",
            confidence="confirmed",
        )
        request = FakeRequest(
            {
                "causal_recorder": FakeRecorder(record),
                "causal_investigator": ExplodingInvestigator(),
            },
            {"entity_id": "light.salle_de_bain", "observed_value": "on"},
        )
        response = await stable_investigate(request)
        body = json.loads(response.text)
        serialized = json.dumps(body, ensure_ascii=False)

        self.assertEqual(response.status, 200)
        self.assertEqual(body["status"], "confirmed")
        self.assertEqual(body["entity_id"], "light.salle_de_bain")
        self.assertEqual(body["result_source"], "causal_recorder")
        self.assertEqual(body["version"], VERSION)
        self.assertIn("mouvement", body["answer_text"])
        self.assertNotIn("Nom technique secret", serialized)
        self.assertNotIn("automation.salle_de_bain", serialized)

    async def test_no_record_returns_immediately_without_deep_fallback(self):
        request = FakeRequest(
            {
                "causal_recorder": FakeRecorder(None),
                "causal_investigator": ExplodingInvestigator(),
            },
            {"entity_id": "cover.volet_salon_2"},
        )
        response = await stable_investigate(request)
        body = json.loads(response.text)

        self.assertEqual(response.status, 200)
        self.assertEqual(body["status"], "indeterminate")
        self.assertEqual(body["entity_id"], "cover.volet_salon_2")
        self.assertEqual(body["result_source"], "causal_recorder_empty")

    async def test_automation_without_functional_reason_does_not_leak_implementation(self):
        record = CausalRecord(
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-08-28T13:21:00+00:00",
            event_kind="positioned",
            before_value=30,
            after_value=40,
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon",
            source_name="Gestion volet salon avec soleil et saison",
            reason=None,
            confidence="confirmed",
        )
        payload = _journal_only_for_request(
            {"causal_recorder": FakeRecorder(record)},
            InvestigationRequest(entity_id="cover.volet_salon_2", observed_value=40),
        )
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["status"], "confirmed")
        self.assertIn("raison fonctionnelle précise", payload["answer_text"])
        self.assertNotIn("automatisation", payload["answer_text"].lower())
        self.assertNotIn("gestion_volet_salon", serialized)
        self.assertNotIn("Gestion volet salon", serialized)


class TestDev31ManualSeparation(unittest.TestCase):
    def test_manual_ui_uses_dedicated_deep_endpoint(self):
        html = "fetch(api('api/v1/investigate'),{method:'POST'});statusEl.textContent='Cause '+d.status;"
        patched = _patch_manual_ui_route(html)
        self.assertIn("api('api/v1/investigate/deep')", patched)
        self.assertNotIn("api('api/v1/investigate'),", patched)
        self.assertIn("confirmed:'confirmée'", patched)


if __name__ == "__main__":
    unittest.main()
