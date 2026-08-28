import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from cover_episode_investigator import CoverEpisodeInvestigator
from models import Evidence, InvestigationRequest, InvestigationResult


class FakeHA:
    def __init__(self, history):
        self.history = history

    async def get_history(self, entity_id, start, end, significant_only=False):
        return list(self.history)


class ProbeInvestigator(CoverEpisodeInvestigator):
    def __init__(self, ha, anchor_result):
        super().__init__(ha)
        self.anchor_result = anchor_result
        self.anchor_requests = []

    async def _anchor_investigate(self, request):
        self.anchor_requests.append(request)
        return self.anchor_result


def confirmed_anchor(direction, service):
    return InvestigationResult(
        status="confirmed",
        entity_id="cover.volet_terrasse_2",
        entity_name="Volet terrasse",
        event_type="state_change",
        event_time="2026-08-28T17:00:01+00:00",
        observed={"before": "closed", "after": direction, "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.gestion_volet",
            "name": "Gestion volet",
            "system_confirmed": True,
        },
        chain=[{"kind": "automation", "entity_id": "automation.gestion_volet", "proven": True}],
        evidence=[
            Evidence(
                kind="logbook",
                summary="service",
                strength="direct",
                raw={"context_domain": "cover", "context_service": service},
            )
        ],
        limits=[],
        meta={},
    )


def indeterminate_anchor(service):
    return InvestigationResult(
        status="indeterminate",
        entity_id="cover.volet_terrasse_2",
        entity_name="Volet terrasse",
        event_type="state_change",
        event_time="2026-08-28T17:00:01+00:00",
        observed={"before": "closed", "after": "opening", "attribute": None},
        cause={"type": "unknown", "entity_id": None, "name": None, "system_confirmed": False},
        chain=[],
        evidence=[
            Evidence(
                kind="logbook",
                summary="service",
                strength="direct",
                raw={"context_domain": "cover", "context_service": service},
            )
        ],
        limits=[],
        meta={},
    )


def terminal_result(after, event_time):
    before = "opening" if after == "open" else "closing"
    return InvestigationResult(
        status="indeterminate",
        entity_id="cover.volet_terrasse_2",
        entity_name="Volet terrasse",
        event_type="state_change",
        event_time=event_time,
        observed={"before": before, "after": after, "attribute": None, "description": "terminal"},
        cause={"type": "unknown", "entity_id": None, "name": None, "system_confirmed": False},
        chain=[],
        evidence=[],
        candidates=[],
        limits=[],
        meta={
            "window": {
                "start": "2026-08-28T16:55:00+00:00",
                "end": "2026-08-28T17:10:00+00:00",
            }
        },
    )


class TestDev33CoverEpisodes(unittest.IsolatedAsyncioTestCase):
    async def test_opening_block_is_anchored_at_first_opening_row(self):
        history = [
            {"state": "closed", "attributes": {"current_position": 0}, "last_updated": "2026-08-28T17:00:00+00:00"},
            {"state": "opening", "attributes": {"current_position": 0}, "last_updated": "2026-08-28T17:00:01+00:00"},
            {"state": "opening", "attributes": {"current_position": 35}, "last_updated": "2026-08-28T17:00:05+00:00"},
            {"state": "opening", "attributes": {"current_position": 80}, "last_updated": "2026-08-28T17:00:09+00:00"},
            {"state": "open", "attributes": {"current_position": 100}, "last_updated": "2026-08-28T17:00:12+00:00"},
        ]
        investigator = ProbeInvestigator(FakeHA(history), confirmed_anchor("opening", "open_cover"))
        request = InvestigationRequest(
            entity_id="cover.volet_terrasse_2",
            observed_time="2026-08-28T17:00:12+00:00",
            observed_value="open",
        )
        result = terminal_result("open", "2026-08-28T17:00:12+00:00")

        await investigator._apply_cover_episode(request, result)

        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.cause["entity_id"], "automation.gestion_volet")
        episode = result.meta["cover_episode"]
        self.assertEqual(episode["direction"], "opening")
        self.assertEqual(episode["motion_start_time"], "2026-08-28T17:00:01+00:00")
        self.assertEqual(episode["context_service"], "cover.open_cover")
        self.assertFalse(episode["context_service_proves_invoker"])
        self.assertTrue(episode["causal_anchor_used"])
        self.assertEqual(investigator.anchor_requests[0].observed_value, "opening")

    async def test_closing_block_remains_symmetric(self):
        history = [
            {"state": "open", "attributes": {"current_position": 100}, "last_updated": "2026-08-28T17:05:00+00:00"},
            {"state": "closing", "attributes": {"current_position": 100}, "last_updated": "2026-08-28T17:05:01+00:00"},
            {"state": "closing", "attributes": {"current_position": 60}, "last_updated": "2026-08-28T17:05:05+00:00"},
            {"state": "closing", "attributes": {"current_position": 20}, "last_updated": "2026-08-28T17:05:09+00:00"},
            {"state": "closed", "attributes": {"current_position": 0}, "last_updated": "2026-08-28T17:05:12+00:00"},
        ]
        investigator = ProbeInvestigator(FakeHA(history), confirmed_anchor("closing", "close_cover"))
        request = InvestigationRequest(
            entity_id="cover.volet_terrasse_2",
            observed_time="2026-08-28T17:05:12+00:00",
            observed_value="closed",
        )
        result = terminal_result("closed", "2026-08-28T17:05:12+00:00")

        await investigator._apply_cover_episode(request, result)

        self.assertEqual(result.status, "confirmed")
        episode = result.meta["cover_episode"]
        self.assertEqual(episode["direction"], "closing")
        self.assertEqual(episode["motion_start_time"], "2026-08-28T17:05:01+00:00")
        self.assertEqual(episode["context_service"], "cover.close_cover")
        self.assertTrue(episode["causal_anchor_used"])

    async def test_context_service_alone_never_upgrades_causal_certainty(self):
        history = [
            {"state": "closed", "attributes": {"current_position": 0}, "last_updated": "2026-08-28T17:00:00+00:00"},
            {"state": "opening", "attributes": {"current_position": 0}, "last_updated": "2026-08-28T17:00:01+00:00"},
            {"state": "opening", "attributes": {"current_position": 50}, "last_updated": "2026-08-28T17:00:06+00:00"},
            {"state": "open", "attributes": {"current_position": 100}, "last_updated": "2026-08-28T17:00:12+00:00"},
        ]
        investigator = ProbeInvestigator(FakeHA(history), indeterminate_anchor("open_cover"))
        request = InvestigationRequest(
            entity_id="cover.volet_terrasse_2",
            observed_time="2026-08-28T17:00:12+00:00",
            observed_value="open",
        )
        result = terminal_result("open", "2026-08-28T17:00:12+00:00")

        await investigator._apply_cover_episode(request, result)

        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.cause["type"], "unknown")
        episode = result.meta["cover_episode"]
        self.assertEqual(episode["context_service"], "cover.open_cover")
        self.assertFalse(episode["context_service_proves_invoker"])
        self.assertFalse(episode["causal_anchor_used"])

    async def test_non_contiguous_motion_is_not_borrowed(self):
        history = [
            {"state": "closed", "attributes": {}, "last_updated": "2026-08-28T17:00:00+00:00"},
            {"state": "opening", "attributes": {}, "last_updated": "2026-08-28T17:00:01+00:00"},
            {"state": "closed", "attributes": {}, "last_updated": "2026-08-28T17:00:06+00:00"},
            {"state": "open", "attributes": {}, "last_updated": "2026-08-28T17:00:12+00:00"},
        ]
        investigator = ProbeInvestigator(FakeHA(history), confirmed_anchor("opening", "open_cover"))
        request = InvestigationRequest(
            entity_id="cover.volet_terrasse_2",
            observed_time="2026-08-28T17:00:12+00:00",
            observed_value="open",
        )
        result = terminal_result("open", "2026-08-28T17:00:12+00:00")

        await investigator._apply_cover_episode(request, result)

        self.assertEqual(result.status, "indeterminate")
        self.assertNotIn("cover_episode", result.meta)
        self.assertEqual(investigator.anchor_requests, [])


if __name__ == "__main__":
    unittest.main()
