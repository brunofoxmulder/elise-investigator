"""Release bootstrap: preserve capture and report RC14 consistently."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "elise_investigator/app"))

import main_v2_rc14 as candidate
from activity_reader_rc13 import ActivityTraceReaderRC13
from causal_recorder import CausalRecorder
from proof_capture_rc13 import ObservedMemoryStream


class RC14PackagingTests(unittest.IsolatedAsyncioTestCase):
    def test_current_release_packaging_is_consistent(self):
        self.assertEqual(candidate.VERSION, "0.3.0-rc.14")
        self.assertEqual(candidate.rc13.VERSION, "0.3.0-rc.13")
        self.assertEqual((ROOT / "elise_investigator/run.sh").read_text(),
                         "#!/usr/bin/with-contenv bashio\nset -e\ncd /app\nexec python3 main_v2_rc14.py\n")
        self.assertIn('version: "0.3.0-rc.14"',
                      (ROOT / "elise_investigator/config.yaml").read_text())
        self.assertFalse((ROOT / "elise_investigator/Dockerfile.rc14").exists())
        self.assertFalse((ROOT / "elise_investigator/run_rc14.sh").exists())

    def test_candidate_workflow_tests_before_publish_and_verifies_image(self):
        workflow = (ROOT / ".github/workflows/publish-v2-rc14-image.yml").read_text()
        self.assertIn("refs/heads/candidate-v2-rc14-native-assist-origin", workflow)
        self.assertIn("elise-investigator-v2-rc14-private:0.3.0-rc.14", workflow)
        self.assertIn("file: ./elise_investigator/Dockerfile\n", workflow)
        self.assertLess(workflow.index("unittest discover"), workflow.index("push: true"))
        self.assertIn("steps.publish.outputs.digest", workflow)
        self.assertIn("--entrypoint python3", workflow)

    async def test_bootstrap_reports_rc14_and_preserves_capture_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CausalRecorder(Path(directory) / "memory.sqlite3")
            stream = object()
            app = web.Application()
            app["causal_recorder"] = recorder
            app["causal_worker"] = SimpleNamespace(stream=stream)
            app["activity_reader_dev63"] = ActivityTraceReaderRC13(object())
            with patch.object(candidate.rc13.impl, "create_app", AsyncMock(return_value=app)), \
                 patch.object(candidate.rc13.impl, "VERSION"), \
                 patch.object(candidate.rc13.impl, "ActivityTraceReader"), \
                 patch.object(candidate.rc13.impl, "_answer"):
                actual = await candidate.create_app()
                self.assertEqual(candidate.rc13.impl.VERSION, candidate.VERSION)
                self.assertIs(candidate.rc13.impl.ActivityTraceReader, ActivityTraceReaderRC13)
            self.assertIs(actual, app)
            self.assertEqual(candidate.rc13.VERSION, "0.3.0-rc.13")
            self.assertIsInstance(app["causal_worker"].stream, ObservedMemoryStream)
            self.assertIs(app["causal_worker"].stream.stream, stream)
            self.assertIs(app["activity_reader_dev63"].archive.db, recorder._db)
            response = await candidate.rc13._proof_status(SimpleNamespace(app=app))
            status = json.loads(response.text)
            self.assertEqual(status["version"], candidate.VERSION)
            self.assertTrue(status["available"])
            self.assertTrue(status["read_only_home_assistant"])
            app.freeze()
            await app.startup()
            self.assertTrue(app["proof_capture_rc13"].status()["running"])
            await app.shutdown()
            self.assertFalse(app["proof_capture_rc13"].status()["running"])
            recorder.close()
