from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev50 import TargetedMemoryEnricher


RAW_ASPIRATOR_TRACE = {
    "config": {
        "action": [
            {"action": "switch.turn_on", "target": {"entity_id": "switch.prise_aspirateur"}},
            {"delay": "00:02:00"},
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "numeric_state",
                                "entity_id": "sensor.prise_aspirateur_power",
                                "above": 1,
                            }
                        ],
                        "sequence": [
                            {
                                "wait_for_trigger": [
                                    {
                                        "trigger": "numeric_state",
                                        "entity_id": "sensor.prise_aspirateur_power",
                                        "below": 1,
                                        "for": {"minutes": 2},
                                    }
                                ],
                                "timeout": "06:00:00",
                                "continue_on_timeout": True,
                            },
                            {
                                # Deliberately device-style: the runtime node below has no
                                # canonical entity_id in params, matching the field failure.
                                "domain": "switch",
                                "type": "turn_off",
                                "device_id": "aspirator-device",
                            },
                            {
                                "action": "notify.mobile_app_sm_s918b",
                                "data": {"message": "L'aspirateur est chargé"},
                            },
                        ],
                    }
                ]
            },
        ]
    },
    "trace": {
        "action/0": [
            {
                "timestamp": "2026-09-01T20:00:12.221072+00:00",
                "result": {
                    "params": {
                        "domain": "switch",
                        "service": "turn_on",
                        "target": {"entity_id": ["switch.prise_aspirateur"]},
                    }
                },
            }
        ],
        "action/1": [
            {
                "timestamp": "2026-09-01T20:00:12.250000+00:00",
                "result": {"delay": 120.0, "done": True},
            }
        ],
        "action/2": [
            {
                "timestamp": "2026-09-01T20:02:12.260000+00:00",
                "result": {"choice": 0},
            }
        ],
        "action/2/choose/0/sequence/0": [
            {
                "timestamp": "2026-09-01T20:08:09.120000+00:00",
                "changed_variables": {
                    "wait": {
                        "completed": True,
                        "trigger": {
                            "platform": "numeric_state",
                            "entity_id": "sensor.prise_aspirateur_power",
                            "below": 1,
                            "for": {"seconds": 120},
                            "idx": 0,
                        },
                    }
                },
            }
        ],
        "action/2/choose/0/sequence/1": [
            {
                "timestamp": "2026-09-01T20:08:09.172086+00:00",
                "result": {"device_action": True},
            }
        ],
        "action/2/choose/0/sequence/2": [
            {
                "timestamp": "2026-09-01T20:08:09.300000+00:00",
                "result": {"done": True},
            }
        ],
    },
}


class TestDev50RawAspiratorTrace(unittest.IsolatedAsyncioTestCase):
    async def test_raw_nested_trace_recovers_wait_reason_without_extractor_mock(self):
        record = CausalRecord(
            record_id=1,
            entity_id="switch.prise_aspirateur",
            entity_name="Prise aspirateur",
            event_time="2026-09-01T20:08:09.223136+00:00",
            event_kind="turned_off",
            before_value="on",
            after_value="off",
            origin_type="automation",
            source_entity_id="automation.charge_aspirateur",
            source_name="Charge aspirateur",
            confidence="confirmed",
        )
        enricher = object.__new__(TargetedMemoryEnricher)
        enricher._label_cause = AsyncMock()

        text, run_id, compact = await enricher._reason_from_detail(
            record,
            "automation.charge_aspirateur",
            "Charge aspirateur",
            "automation",
            RAW_ASPIRATOR_TRACE,
            "7d24dc728d151c6352adc359228f6934",
        )

        self.assertIsNotNone(text)
        self.assertIn("puissance", text.lower())
        self.assertIn("1", text)
        self.assertEqual(run_id, "7d24dc728d151c6352adc359228f6934")
        self.assertIsNotNone(compact)
        self.assertEqual(compact.get("origin"), "wait_for_trigger")
        self.assertEqual(compact.get("detail", {}).get("below"), 1)
        self.assertEqual(compact.get("detail", {}).get("for"), {"minutes": 2})

    async def test_cover_is_still_excluded_from_dev50_fallback(self):
        record = CausalRecord(
            record_id=2,
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-09-01T20:08:09.223136+00:00",
            event_kind="closed",
            before_value="closing",
            after_value="closed",
            origin_type="automation",
            source_entity_id="automation.volet",
            source_name="Volet",
            confidence="confirmed",
        )
        self.assertFalse(
            TargetedMemoryEnricher._context_link_proven(
                record, "automation.volet", "automation"
            )
        )


if __name__ == "__main__":
    unittest.main()
