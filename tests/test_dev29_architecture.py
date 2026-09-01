import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


class TestDev29Architecture(unittest.TestCase):
    def test_candidate_launcher_uses_current_wrapper(self):
        run_sh = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        self.assertIn("main_dev50.py", run_sh)
        self.assertNotIn("main_mcp_inprocess.py", run_sh)

    def test_manual_investigate_endpoint_is_not_replaced_in_dev29_base(self):
        source = (APP / "main_dev29.py").read_text(encoding="utf-8")
        self.assertIn("base.ask = recorder_first_ask", source)
        self.assertNotIn("base.investigate =", source)
        self.assertIn("manual /investigate endpoint remains untouched", source)

    def test_journal_uses_separate_dev16_engine_without_replacing_manual_engine_in_dev29(self):
        source = (APP / "main_dev29.py").read_text(encoding="utf-8")
        self.assertIn("V02Investigator", source)
        self.assertIn('app["causal_investigator"]', source)
        self.assertIn('app["investigator"]', source)
        self.assertNotIn('app["investigator"] = causal_investigator', source)

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
            "causal_recorder_dev33.py",
            "causal_recorder_dev47.py",
            "causal_recorder_dev49.py",
            "causal_response.py",
            "causal_settings.py",
            "causal_worker.py",
            "cover_position_investigator.py",
            "cover_episode_investigator.py",
            "ha_event_stream.py",
            "ha_memory_stream_dev34.py",
            "main_dev29.py",
            "main_dev30.py",
            "main_dev31.py",
            "main_dev32.py",
            "main_dev33.py",
            "main_dev34.py",
            "main_dev34_1.py",
            "main_dev36.py",
            "main_dev37.py",
            "main_dev38.py",
            "main_dev39.py",
            "main_dev43.py",
            "main_dev44.py",
            "main_dev45.py",
            "main_dev46.py",
            "main_dev47.py",
            "main_dev48.py",
            "main_dev49.py",
            "main_dev50.py",
            "memory_response_dev34.py",
            "memory_worker_dev34.py",
            "memory_worker_dev36.py",
            "memory_worker_dev37.py",
            "memory_worker_dev38.py",
            "memory_worker_dev39.py",
            "memory_worker_dev43.py",
            "memory_worker_dev44.py",
            "memory_worker_dev45.py",
            "memory_worker_dev46.py",
            "memory_worker_dev48.py",
            "memory_worker_dev49.py",
            "memory_worker_dev50.py",
            "mcp_targeted_trace_dev36.py",
            "request_journal_dev34.py",
            "runtime_decision.py",
            "targeted_memory_enricher_dev36.py",
            "targeted_memory_enricher_dev37.py",
            "targeted_memory_enricher_dev38.py",
            "targeted_memory_enricher_dev39.py",
            "targeted_memory_enricher_dev43.py",
            "targeted_memory_enricher_dev44.py",
            "targeted_memory_enricher_dev45.py",
            "targeted_memory_enricher_dev48.py",
            "targeted_memory_enricher_dev49.py",
            "targeted_memory_enricher_dev50.py",
            "context_linked_effect_cause_dev50.py",
            "combined_trigger_condition_factors.py",
            "v02_investigator.py",
        )
        combined = "\n".join((APP / name).read_text(encoding="utf-8") for name in names)
        self.assertNotIn("supervisor/core/api/services", combined)
        self.assertNotIn("session.post", combined)
        self.assertNotIn("session.put", combined)
        self.assertNotIn("session.delete", combined)

    def test_candidate_build_does_not_promote_test_manifest(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-dev29-image.yml").read_text(encoding="utf-8")
        self.assertIn("elise-investigator-dev29-private:0.2.0-dev.29", workflow)
        self.assertNotIn("elise_investigator_02_test/config.yaml", workflow)
        self.assertNotIn("dist-dev29", workflow)


if __name__ == "__main__":
    unittest.main()
