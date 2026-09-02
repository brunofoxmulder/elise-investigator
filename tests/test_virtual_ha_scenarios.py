import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
VIRTUAL = TESTS / "virtual_ha"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(VIRTUAL))

from scenarios import LAMP, brightness_transition_scenario, cover_episode_scenario


class VirtualHAScenarioEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_brightness_timeline_can_be_observed_at_multiple_instants(self):
        scenario = brightness_transition_scenario()

        first = scenario.at("2026-09-02T17:59:15+00:00")
        middle = scenario.at("2026-09-02T18:01:31+00:00")
        late = scenario.at("2026-09-02T18:02:30+00:00")

        self.assertEqual((await first.get_state(LAMP))["attributes"]["brightness"], 0)
        self.assertEqual((await middle.get_state(LAMP))["attributes"]["brightness"], 16)
        self.assertEqual((await late.get_state(LAMP))["attributes"]["brightness"], 17)

        first_logbook = await first.get_logbook(LAMP)
        late_logbook = await late.get_logbook(LAMP)
        self.assertEqual(first_logbook[-1]["context_entity_id"], "automation.ambiance_du_soir_test")
        self.assertNotIn("context_entity_id", late_logbook[-1])
        self.assertEqual(late_logbook[-1]["context_id"], "ctx-transition-1")

        # The same causal episode can therefore be queried before and after
        # context-poor intermediate brightness samples.
        self.assertEqual(len(await first.get_history(LAMP)), 2)
        self.assertEqual(len(await late.get_history(LAMP)), 4)

    async def test_virtual_scenarios_remain_strictly_read_only(self):
        twin = brightness_transition_scenario().at("2026-09-02T18:02:30+00:00")
        self.assertFalse(hasattr(twin, "call_service"))

    async def test_cover_episode_is_kept_as_a_separate_regression_scenario(self):
        twin = cover_episode_scenario().at("2026-09-02T16:00:20+00:00")
        state = await twin.get_state("cover.volet_test")
        history = await twin.get_history("cover.volet_test")

        self.assertEqual(state["state"], "closed")
        self.assertEqual(state["attributes"]["current_position"], 0)
        self.assertEqual([item["state"] for item in history], ["open", "closing", "closed"])
        self.assertFalse(hasattr(twin, "call_service"))


if __name__ == "__main__":
    unittest.main()
