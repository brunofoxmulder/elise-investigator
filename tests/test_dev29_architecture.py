import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


class TestDev29Architecture(unittest.TestCase):
    def test_candidate_launcher_uses_dev29_wrapper(self):
        run_sh = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        self.assertIn("main_dev29.py", run_sh)
        self.assertNotIn("main_mcp_inprocess.py", run_sh)

    def test_manual_investigate_endpoint_is_not_replaced(self):
        source = (APP / "main_dev29.py").read_text(encoding="utf-8")
        self.assertIn("base.ask = recorder_first_ask", source)
        self.assertNotIn("base.investigate =", source)
        self.assertIn("manual /investigate endpoint remains untouched", source)

    def test_settings_ui_contains_both_validated_controls(self):
        source = (APP / "main_dev29.py").read_text(encoding="utf-8")
        self.assertIn("causal_retention", source)
        self.assertIn('min="1" max="72"', source)
        self.assertIn("causal_fallback", source)
        self.assertIn("Enquête approfondie de secours", source)

    def test_dev29_home_assistant_stream_has_no_mutating_command(self):
        source = (APP / "ha_event_stream.py").read_text(encoding="utf-8")
        self.assertIn('"type": "subscribe_events"', source)
        forbidden = (
            '"type": "call_service"',
            '"type": "config/entity_registry/update"',
            '"type": "config/device_registry/update"',
            '"type": "automation/config"',
            '"type": "script/config"',
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_causal_modules_never_call_supervisor_write_endpoints(self):
        names = (
            "causal_enricher.py",
            "causal_events.py",
            "causal_recorder.py",
            "causal_response.py",
            "causal_settings.py",
            "causal_worker.py",
            "ha_event_stream.py",
            "main_dev29.py",
            "runtime_decision.py",
        )
        combined = "\n".join((APP / name).read_text(encoding="utf-8") for name in names)
        self.assertNotIn("supervisor/core/api/services", combined)
        self.assertNotIn("session.post", combined)
        self.assertNotIn("session.put", combined)
        self.assertNotIn("session.delete", combined)


if __name__ == "__main__":
    unittest.main()
