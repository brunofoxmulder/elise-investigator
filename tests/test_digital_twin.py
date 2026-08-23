import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from digital_twin import DigitalTwinHA
from investigator import Investigator
from models import InvestigationRequest


class DigitalTwinInvestigatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_temperature_threshold_drives_cover_to_80_percent(self):
        target = "cover.test_volet"
        automation = "automation.test_temperature_volet"
        automation_id = "auto-temp-cover"
        event_time = "2026-08-23T13:31:05+00:00"

        twin = DigitalTwinHA(
            states=[
                {
                    "entity_id": target,
                    "state": "open",
                    "attributes": {"friendly_name": "Volet test", "current_position": 80},
                    "last_changed": "2026-08-23T13:30:00+00:00",
                    "last_updated": event_time,
                },
                {
                    "entity_id": "sensor.test_temperature_exterieure",
                    "state": "25.6",
                    "attributes": {"friendly_name": "Température extérieure test", "unit_of_measurement": "°C"},
                    "last_changed": "2026-08-23T13:31:00+00:00",
                    "last_updated": "2026-08-23T13:31:00+00:00",
                },
                {
                    "entity_id": automation,
                    "state": "on",
                    "attributes": {"friendly_name": "Gestion thermique volet test", "id": automation_id},
                    "last_changed": "2026-08-23T10:00:00+00:00",
                    "last_updated": "2026-08-23T13:31:01+00:00",
                },
            ],
            histories={
                target: [
                    {
                        "state": "open",
                        "attributes": {"friendly_name": "Volet test", "current_position": 100},
                        "last_changed": "2026-08-23T13:20:00+00:00",
                        "last_updated": "2026-08-23T13:20:00+00:00",
                    },
                    {
                        "state": "open",
                        "attributes": {"friendly_name": "Volet test", "current_position": 80},
                        "last_changed": "2026-08-23T13:20:00+00:00",
                        "last_updated": event_time,
                    },
                ]
            },
            logbooks={
                target: [
                    {
                        "entity_id": target,
                        "when": event_time,
                        "message": "position changed to 80",
                        "context_entity_id": automation,
                        "context_entity_id_name": "Gestion thermique volet test",
                    }
                ]
            },
            trace_summaries={
                ("automation", automation_id): [
                    {
                        "run_id": "run-1",
                        "timestamp": {"start": "2026-08-23T13:31:01+00:00"},
                    }
                ]
            },
            trace_details={
                ("automation", automation_id, "run-1"): {
                    "trigger": {
                        "platform": "numeric_state",
                        "entity_id": "sensor.test_temperature_exterieure",
                        "above": 25,
                        "from_state": {"state": "24.8"},
                        "to_state": {"state": "25.6"},
                    },
                    "action": {
                        "domain": "cover",
                        "service": "set_cover_position",
                        "target": {"entity_id": target},
                        "service_data": {"position": 80},
                    },
                }
            },
        )

        investigator = Investigator(twin)
        result = await investigator.investigate(
            InvestigationRequest(
                entity_id=target,
                observed_time="2026-08-23T15:31:05+02:00",
                observed_value=80,
                attribute="current_position",
            )
        )

        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.event_type, "attribute_change")
        self.assertEqual(result.observed["before"], 100)
        self.assertEqual(result.observed["after"], 80)
        self.assertEqual(result.cause["type"], "automation")
        self.assertEqual(result.cause["entity_id"], automation)
        self.assertTrue(result.cause["system_confirmed"])
        self.assertEqual(result.cause["trigger_source"]["above"], 25)
        self.assertEqual(result.cause["trigger_source"]["to_state"]["state"], "25.6")
        self.assertEqual(result.cause["commands"][0]["service"], "cover.set_cover_position")
        self.assertEqual(result.cause["commands"][0]["data"]["position"], 80)
        self.assertEqual([step["kind"] for step in result.chain], ["trigger", "automation", "command"])

        # The behavioral twin is intentionally incapable of mutating Home Assistant.
        self.assertFalse(hasattr(twin, "call_service"))


if __name__ == "__main__":
    unittest.main()
