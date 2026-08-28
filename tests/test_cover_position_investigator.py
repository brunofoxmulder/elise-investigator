import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from cover_position_investigator import CoverPositionInvestigator
from models import Evidence, InvestigationRequest, InvestigationResult


class FakeHA:
    def __init__(self, history):
        self.history = history

    async def get_history(self, entity_id, start, end, significant_only=False):
        return list(self.history)


class ProbeCoverInvestigator(CoverPositionInvestigator):
    def __init__(self, ha, anchor_result):
        super().__init__(ha)
        self.anchor_result = anchor_result
        self.anchor_requests = []

    async def _anchor_investigate(self, request):
        self.anchor_requests.append(request)
        return self.anchor_result


def trace_evidence(position=50):
    return Evidence(
        kind="trace",
        summary="trace",
        source="automation.gestion_volet",
        strength="direct",
        raw={
            "trace": {
                "action/0": [
                    {
                        "result": {
                            "params": {
                                "domain": "cover",
                                "service": "set_cover_position",
                                "target": {"entity_id": "cover.volet_terrasse"},
                                "service_data": {"position": position},
                            }
                        }
                    }
                ]
            }
        },
    )


def confirmed_anchor(position=50):
    return InvestigationResult(
        status="confirmed",
        entity_id="cover.volet_terrasse",
        entity_name="Volet terrasse",
        event_type="state_change",
        event_time="2026-08-28T14:03:56+00:00",
        observed={"before": "open", "after": "closing", "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.gestion_volet",
            "name": "Gestion volet",
            "system_confirmed": True,
        },
        chain=[{"kind": "automation", "entity_id": "automation.gestion_volet", "proven": True}],
        evidence=[trace_evidence(position)],
        limits=[],
        meta={},
    )


def position_result(before=100, after=50):
    return InvestigationResult(
        status="indeterminate",
        entity_id="cover.volet_terrasse",
        entity_name="Volet terrasse",
        event_type="attribute_change",
        event_time="2026-08-28T14:04:10+00:00",
        observed={
            "before": before,
            "after": after,
            "attribute": "current_position",
            "description": "position changée",
        },
        cause={"type": "unknown", "entity_id": None, "name": None, "system_confirmed": False},
        chain=[],
        evidence=[],
        candidates=[],
        limits=[],
        meta={
            "window": {
                "start": "2026-08-28T13:59:10+00:00",
                "end": "2026-08-28T14:09:10+00:00",
            }
        },
    )


def closing_history():
    return [
        {
            "state": "open",
            "attributes": {"current_position": 100},
            "last_updated": "2026-08-28T14:03:50+00:00",
        },
        {
            "state": "closing",
            "attributes": {"current_position": 100},
            "last_updated": "2026-08-28T14:03:56+00:00",
        },
        {
            "state": "open",
            "attributes": {"current_position": 50},
            "last_updated": "2026-08-28T14:04:10+00:00",
        },
    ]


class TestPartialCoverPosition(unittest.IsolatedAsyncioTestCase):
    async def test_partial_position_uses_adjacent_motion_start_and_matching_runtime_command(self):
        investigator = ProbeCoverInvestigator(FakeHA(closing_history()), confirmed_anchor(50))
        request = InvestigationRequest(
            entity_id="cover.volet_terrasse",
            observed_time="2026-08-28T14:04:10+00:00",
            observed_value=50,
            attribute="current_position",
        )
        result = position_result()

        await investigator._apply_cover_episode(request, result)

        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.cause["entity_id"], "automation.gestion_volet")
        self.assertEqual(result.observed["after"], 50)
        self.assertEqual(result.observed["attribute"], "current_position")
        episode = result.meta["cover_position_episode"]
        self.assertTrue(episode["recognized"])
        self.assertTrue(episode["effect_command_proven"])
        self.assertTrue(episode["causal_anchor_used"])
        self.assertEqual(episode["direction"], "closing")
        self.assertEqual(episode["after_position"], 50.0)
        self.assertEqual(len(investigator.anchor_requests), 1)
        self.assertEqual(investigator.anchor_requests[0].observed_value, "closing")
        self.assertIsNone(investigator.anchor_requests[0].attribute)

    async def test_wrong_runtime_position_never_upgrades_certainty(self):
        investigator = ProbeCoverInvestigator(FakeHA(closing_history()), confirmed_anchor(60))
        request = InvestigationRequest(
            entity_id="cover.volet_terrasse",
            observed_time="2026-08-28T14:04:10+00:00",
            observed_value=50,
            attribute="current_position",
        )
        result = position_result()

        await investigator._apply_cover_episode(request, result)

        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.cause["type"], "unknown")
        episode = result.meta["cover_position_episode"]
        self.assertFalse(episode["effect_command_proven"])
        self.assertFalse(episode["causal_anchor_used"])

    async def test_non_adjacent_motion_is_not_borrowed(self):
        history = closing_history()
        history.insert(
            2,
            {
                "state": "open",
                "attributes": {"current_position": 100},
                "last_updated": "2026-08-28T14:04:00+00:00",
            },
        )
        investigator = ProbeCoverInvestigator(FakeHA(history), confirmed_anchor(50))
        request = InvestigationRequest(
            entity_id="cover.volet_terrasse",
            observed_time="2026-08-28T14:04:10+00:00",
            observed_value=50,
            attribute="current_position",
        )
        result = position_result()

        await investigator._apply_cover_episode(request, result)

        self.assertEqual(result.status, "indeterminate")
        self.assertNotIn("cover_position_episode", result.meta)
        self.assertEqual(investigator.anchor_requests, [])


if __name__ == "__main__":
    unittest.main()
