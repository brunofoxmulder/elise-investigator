from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev72 import ActivityTraceReader as Dev72ActivityTraceReader
from activity_reader_dev73 import ActivityTraceReader, _is_raw_provider_trigger_text
from causal_recorder import CausalRecord


class _HA:
    pass


def _record(reason: str, reason_code: str) -> CausalRecord:
    return CausalRecord(
        entity_id="light.hue_tento_color_panel_1",
        event_time="2026-09-10T21:14:41+00:00",
        event_kind="turned_on",
        after_value="on",
        origin_type="automation",
        source_entity_id="automation.allumer_salle_de_bain_selon_l_heure_et_la_presence",
        source_name="Allumer salle de bain selon l'heure et la présence",
        reason=reason,
        reason_code=reason_code,
        trigger={},
        confidence="confirmed",
    )


class Dev73NativeReasonFirewallTests(unittest.IsolatedAsyncioTestCase):
    def test_detector_matches_provider_trigger_phrase_independently_of_reason_code(self):
        self.assertTrue(_is_raw_provider_trigger_text("triggered by state of binary_sensor.salle_de_bain_mouvement"))
        self.assertTrue(_is_raw_provider_trigger_text("  Triggered by numeric state of sensor.battery"))
        self.assertFalse(_is_raw_provider_trigger_text("un mouvement a été détecté"))
        self.assertFalse(_is_raw_provider_trigger_text("le délai de 10 minutes s'est écoulé"))

    async def test_dev72_terrain_native_message_is_suppressed_at_terminal_reader_boundary(self):
        record = _record(
            "triggered by state of binary_sensor.salle_de_bain_mouvement",
            "ha_2026_9_activity_native",
        )
        reader = ActivityTraceReader(_HA())
        with patch.object(
            Dev72ActivityTraceReader,
            "_record_from_entries",
            new=AsyncMock(return_value=record),
        ):
            result = await reader._record_from_entries(
                record.entity_id,
                [],
                end_time=None,
                hours=12,
                allow_upstream=True,
            )

        self.assertIs(result, record)
        self.assertIsNone(result.reason)
        self.assertIsNone(result.reason_code)
        self.assertEqual(
            result.trigger.get("suppressed_native_reason"),
            "triggered by state of binary_sensor.salle_de_bain_mouvement",
        )
        self.assertEqual(
            result.trigger.get("suppressed_native_reason_code"),
            "ha_2026_9_activity_native",
        )

    async def test_source_hint_path_is_suppressed_by_same_terminal_rule(self):
        record = _record(
            "triggered by state of binary_sensor.salle_de_bain_mouvement",
            "ha_2026_9_activity_source_hint",
        )
        reader = ActivityTraceReader(_HA())
        with patch.object(
            Dev72ActivityTraceReader,
            "_record_from_entries",
            new=AsyncMock(return_value=record),
        ):
            result = await reader._record_from_entries(
                record.entity_id,
                [],
                end_time=None,
                hours=12,
                allow_upstream=True,
            )
        self.assertIsNone(result.reason)
        self.assertIsNone(result.reason_code)

    async def test_proven_exact_trace_reason_is_never_touched(self):
        record = _record("un mouvement a été détecté", "ha_logbook+exact_trace")
        reader = ActivityTraceReader(_HA())
        with patch.object(
            Dev72ActivityTraceReader,
            "_record_from_entries",
            new=AsyncMock(return_value=record),
        ):
            result = await reader._record_from_entries(
                record.entity_id,
                [],
                end_time=None,
                hours=12,
                allow_upstream=True,
            )
        self.assertEqual(result.reason, "un mouvement a été détecté")
        self.assertEqual(result.reason_code, "ha_logbook+exact_trace")

    def test_dev54_fallback_remains_intact(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
