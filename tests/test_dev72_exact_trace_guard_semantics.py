from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev72 import TargetedMemoryEnricher


class _HA:
    async def get_state(self, entity_id):
        names = {
            "binary_sensor.mouvement_sdb": "Mouvement salle de bain",
            "switch.prise_de_comptage_prise_1": "prise_de_comptage_prise_1",
            "input_boolean.mode_cinema": "Mode Cinéma",
            "binary_sensor.heures_creuses": "Heures creuses",
            "sensor.battery": "Batterie",
        }
        attrs = {"friendly_name": names.get(entity_id, entity_id)}
        if entity_id == "sensor.battery":
            attrs["unit_of_measurement"] = "%"
        return {"entity_id": entity_id, "state": "on", "attributes": attrs}


class _TraceInvestigator:
    pass


def _record(entity_id: str) -> CausalRecord:
    return CausalRecord(
        entity_id=entity_id,
        event_time="2026-09-10T21:18:23+00:00",
        event_kind="turned_on",
        after_value="on",
        origin_type="automation",
        source_entity_id="automation.test",
        source_name="Test",
        confidence="confirmed",
    )


class Dev72ExactTraceGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_motion_trigger_does_not_promote_pure_state_guards(self):
        detail = {
            "config": {
                "conditions": [
                    {"condition": "state", "entity_id": "switch.prise_de_comptage_prise_1", "state": "on"},
                    {"condition": "state", "entity_id": "input_boolean.mode_cinema", "state": "off"},
                ],
                "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.hotte"}}],
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {
                    "platform": "state",
                    "entity_id": "binary_sensor.mouvement_sdb",
                    "from_state": {"state": "off"},
                    "to_state": {"state": "on"},
                }}}],
                "condition/0": [{"result": {"result": True, "state": "on"}}],
                "condition/1": [{"result": {"result": True, "state": "off"}}],
                "action/0": [{"result": {"params": {
                    "domain": "light", "service": "turn_on", "target": {"entity_id": ["light.hotte"]}
                }}}],
            },
        }
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        reason, _, cause = await helper._reason_from_detail(
            _record("light.hotte"), "automation.test", "Test", "automation", detail, "run-motion"
        )
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "automation_trigger")
        self.assertNotIn("prise_de_comptage", str(reason))
        self.assertNotIn("Mode Cinéma", str(reason))

    async def test_numeric_threshold_joint_cause_remains_supported(self):
        detail = {
            "config": {
                "conditions": [{"condition": "numeric_state", "entity_id": "sensor.battery", "below": 40}],
                "actions": [{"action": "switch.turn_on", "target": {"entity_id": "switch.telephone"}}],
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {
                    "platform": "state", "entity_id": "binary_sensor.heures_creuses",
                    "from_state": {"state": "off"}, "to_state": {"state": "on"},
                }}}],
                "condition/0": [{"result": {"result": True, "state": "32"}}],
                "action/0": [{"result": {"params": {
                    "domain": "switch", "service": "turn_on", "target": {"entity_id": ["switch.telephone"]}
                }}}],
            },
        }
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        reason, _, cause = await helper._reason_from_detail(
            _record("switch.telephone"), "automation.test", "Test", "automation", detail, "run-joint"
        )
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "trigger_plus_conditions")
        self.assertIn("Heures creuses", reason)
        self.assertIn("Batterie", reason)


if __name__ == "__main__":
    unittest.main()
