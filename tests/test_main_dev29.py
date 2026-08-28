import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_settings import CausalSettings
from main_dev29 import recorder_first_ask
from models import InvestigationRequest, InvestigationResult


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
    def __init__(self):
        self.calls = 0

    async def investigate(self, request):
        self.calls += 1
        return InvestigationResult(
            status="confirmed",
            entity_id=request.entity_id,
            entity_name="Lampe entrée",
            event_type="state_change",
            event_time="2026-08-28T10:00:00+00:00",
            observed={"before": "on", "after": "off"},
            cause={"type": "automation", "entity_id": "automation.entree", "system_confirmed": True},
            answer_text="Réponse enquête approfondie",
        )


def resolved():
    return (
        InvestigationRequest(entity_id="light.entree", observed_value="off"),
        {
            "question": "Pourquoi la lampe entrée s'est éteinte ?",
            "entity_id": "light.entree",
            "entity_name": "Lampe entrée",
            "observed_time": None,
            "observed_value": "off",
            "time_zone": "Europe/Paris",
        },
    )


class TestMainDev29(unittest.IsolatedAsyncioTestCase):
    async def test_journal_hit_never_calls_deep_investigator(self):
        record = CausalRecord(
            entity_id="light.entree",
            entity_name="Lampe entrée",
            event_time="2026-08-28T10:00:00+00:00",
            event_kind="turned_off",
            after_value="off",
            origin_type="automation",
            reason="il n'y avait plus de mouvement",
            confidence="confirmed",
        )
        recorder = FakeRecorder(record)
        investigator = FakeInvestigator()
        request = FakeRequest(
            {
                "ha": object(),
                "causal_recorder": recorder,
                "causal_settings": CausalSettings(deep_fallback=True),
                "investigator": investigator,
            },
            {"question": "Pourquoi la lampe entrée s'est éteinte ?"},
        )
        with patch("main_dev29.base.build_investigation_request", new=AsyncMock(return_value=resolved())):
            response = await recorder_first_ask(request)
        body = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(body["source"], "causal_recorder")
        self.assertIn("plus de mouvement", body["answer_text"])
        self.assertEqual(investigator.calls, 0)
        self.assertEqual(recorder.calls[0][0], "light.entree")
        self.assertEqual(recorder.calls[0][1]["observed_value"], "off")

    async def test_empty_journal_with_fallback_disabled_stops_without_deep_search(self):
        recorder = FakeRecorder(None)
        investigator = FakeInvestigator()
        request = FakeRequest(
            {
                "ha": object(),
                "causal_recorder": recorder,
                "causal_settings": CausalSettings(deep_fallback=False),
                "investigator": investigator,
            },
            {"question": "Pourquoi la lampe entrée s'est éteinte ?"},
        )
        with patch("main_dev29.base.build_investigation_request", new=AsyncMock(return_value=resolved())):
            response = await recorder_first_ask(request)
        body = json.loads(response.text)
        self.assertEqual(body["source"], "causal_recorder_empty")
        self.assertEqual(body["status"], "indeterminate")
        self.assertEqual(investigator.calls, 0)

    async def test_empty_journal_with_fallback_enabled_uses_existing_investigator(self):
        recorder = FakeRecorder(None)
        investigator = FakeInvestigator()
        request = FakeRequest(
            {
                "ha": object(),
                "causal_recorder": recorder,
                "causal_settings": CausalSettings(deep_fallback=True),
                "investigator": investigator,
            },
            {"question": "Pourquoi la lampe entrée s'est éteinte ?"},
        )
        with patch("main_dev29.base.build_investigation_request", new=AsyncMock(return_value=resolved())):
            response = await recorder_first_ask(request)
        body = json.loads(response.text)
        self.assertEqual(body["source"], "deep_investigation_fallback")
        self.assertEqual(body["answer_text"], "Réponse enquête approfondie")
        self.assertEqual(investigator.calls, 1)


if __name__ == "__main__":
    unittest.main()
