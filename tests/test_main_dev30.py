import json
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_settings import CausalSettings
from main_dev30 import (
    EffectiveTransitionInvestigator,
    _patch_manual_ui,
    _record_payload,
    structured_why,
)
from models import InvestigationResult


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


class FakeInvestigator:
    def __init__(self, result=None):
        self.result = result
        self.calls = 0

    async def investigate(self, request):
        self.calls += 1
        if self.result is not None:
            return self.result
        return InvestigationResult(
            status="indeterminate",
            entity_id=request.entity_id,
            entity_name="Lampe salon",
            event_type="current_state_only",
            event_time=None,
            observed={"before": None, "after": "on", "attribute": None},
            cause={"type": "unknown", "entity_id": None, "name": None, "system_confirmed": False},
            answer_text="La cause ne peut pas être déterminée.",
        )


class TestEffectiveTransitionSelection(unittest.TestCase):
    def test_latest_real_transition_wins_over_later_same_state_refresh(self):
        investigator = EffectiveTransitionInvestigator(object())
        history = [
            {"state": "off", "last_updated": "2026-08-28T11:58:00+00:00", "attributes": {}},
            {"state": "on", "last_updated": "2026-08-28T11:59:00+00:00", "attributes": {"brightness": 180}},
            {"state": "on", "last_updated": "2026-08-28T11:59:02+00:00", "attributes": {"brightness": 200}},
            {"state": "on", "last_updated": "2026-08-28T11:59:04+00:00", "attributes": {"brightness": 220}},
        ]
        previous, event = investigator._choose_event(
            history,
            observed_time=None,
            observed_value="on",
            attribute=None,
        )
        self.assertEqual(previous["state"], "off")
        self.assertEqual(event["last_updated"], "2026-08-28T11:59:00+00:00")

    def test_latest_effective_transition_is_used_when_no_value_clue_is_given(self):
        investigator = EffectiveTransitionInvestigator(object())
        history = [
            {"state": "off", "last_updated": "2026-08-28T11:50:00+00:00", "attributes": {}},
            {"state": "on", "last_updated": "2026-08-28T11:51:00+00:00", "attributes": {}},
            {"state": "on", "last_updated": "2026-08-28T11:52:00+00:00", "attributes": {"brightness": 100}},
            {"state": "off", "last_updated": "2026-08-28T11:53:00+00:00", "attributes": {}},
            {"state": "off", "last_updated": "2026-08-28T11:54:00+00:00", "attributes": {}},
        ]
        previous, event = investigator._choose_event(
            history,
            observed_time=None,
            observed_value=None,
            attribute=None,
        )
        self.assertEqual(previous["state"], "on")
        self.assertEqual(event["state"], "off")
        self.assertEqual(event["last_updated"], "2026-08-28T11:53:00+00:00")


class TestDev30WhyRoute(unittest.IsolatedAsyncioTestCase):
    async def test_structured_why_uses_journal_before_deep_search(self):
        record = CausalRecord(
            entity_id="light.salle_de_bain",
            entity_name="Lampe salle de bain",
            event_time="2026-08-28T12:01:00+00:00",
            event_kind="turned_on",
            before_value="off",
            after_value="on",
            origin_type="automation",
            source_entity_id="automation.salle_de_bain",
            source_name="Allumer salle de bain selon l'heure et la présence",
            reason="un mouvement a été détecté",
            confidence="confirmed",
        )
        recorder = FakeRecorder(record)
        investigator = FakeInvestigator()
        request = FakeRequest(
            {
                "causal_recorder": recorder,
                "causal_settings": CausalSettings(deep_fallback=True),
                "causal_investigator": investigator,
            },
            {"entity_id": "light.salle_de_bain", "observed_value": "on"},
        )
        response = await structured_why(request)
        body = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(body["result_source"], "causal_recorder")
        self.assertEqual(body["reason"], "un mouvement a été détecté")
        self.assertNotIn("automation", json.dumps(body).lower())
        self.assertNotIn("Allumer salle de bain", json.dumps(body))
        self.assertEqual(investigator.calls, 0)

    async def test_structured_why_respects_disabled_deep_fallback(self):
        recorder = FakeRecorder(None)
        investigator = FakeInvestigator()
        request = FakeRequest(
            {
                "causal_recorder": recorder,
                "causal_settings": CausalSettings(deep_fallback=False),
                "causal_investigator": investigator,
            },
            {"entity_id": "light.salon", "observed_value": "on"},
        )
        response = await structured_why(request)
        body = json.loads(response.text)
        self.assertEqual(body["status"], "indeterminate")
        self.assertEqual(body["result_source"], "causal_recorder_empty")
        self.assertEqual(investigator.calls, 0)

    async def test_deep_fallback_never_leaks_automation_name_to_llm_payload(self):
        result = InvestigationResult(
            status="confirmed",
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_type="state_change",
            event_time="2026-08-28T12:02:00+00:00",
            observed={"before": "off", "after": "on", "attribute": None},
            cause={
                "type": "automation",
                "entity_id": "automation.secret_name",
                "name": "Nom technique à ne pas envoyer",
                "system_confirmed": True,
            },
            answer_text="Cause confirmée. La cause est Nom technique à ne pas envoyer.",
        )
        request = FakeRequest(
            {
                "causal_recorder": FakeRecorder(None),
                "causal_settings": CausalSettings(deep_fallback=True),
                "causal_investigator": FakeInvestigator(result),
            },
            {"entity_id": "light.salon", "observed_value": "on"},
        )
        response = await structured_why(request)
        body = json.loads(response.text)
        serialized = json.dumps(body, ensure_ascii=False)
        self.assertEqual(body["result_source"], "deep_investigation_fallback")
        self.assertNotIn("Nom technique à ne pas envoyer", serialized)
        self.assertNotIn("automation.secret_name", serialized)


class TestDev30Presentation(unittest.TestCase):
    def test_manual_badge_is_french(self):
        html = "function renderInvestigation(d){statusEl.textContent='Cause '+d.status;}"
        patched = _patch_manual_ui(html)
        self.assertIn("confirmed:'confirmée'", patched)
        self.assertIn("indeterminate:'indéterminée'", patched)

    def test_record_llm_projection_does_not_expose_automation_implementation(self):
        record = CausalRecord(
            entity_id="light.entree",
            entity_name="Lampe entrée",
            event_time="2026-08-28T12:00:00+00:00",
            event_kind="turned_off",
            after_value="off",
            origin_type="automation",
            source_entity_id="automation.entree",
            source_name="Extinction entrée technique",
            reason="il n'y avait plus de mouvement",
            confidence="confirmed",
        )
        payload = _record_payload(record)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertIn("plus de mouvement", text)
        self.assertNotIn("automation.entree", text)
        self.assertNotIn("Extinction entrée technique", text)


if __name__ == "__main__":
    unittest.main()
