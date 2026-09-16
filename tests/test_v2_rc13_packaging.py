from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "elise_investigator/app"))
import main_v2_rc13 as candidate
from activity_reader_rc13 import ActivityTraceReaderRC13
from causal_recorder import CausalRecorder
from proof_capture_rc13 import ObservedMemoryStream


class PackagingTests(unittest.IsolatedAsyncioTestCase):
    def test_candidate_preserves_proven_generic_packaging(self):
        self.assertEqual((ROOT / "elise_investigator/run.sh").read_text(),
                         "#!/usr/bin/with-contenv bashio\nset -e\ncd /app\nexec python3 main_v2_rc13.py\n")
        dockerfile = (ROOT / "elise_investigator/Dockerfile").read_text()
        self.assertIn("COPY run.sh /run.sh", dockerfile)
        self.assertIn("RUN chmod 0755 /run.sh", dockerfile)
        self.assertIn('CMD ["/run.sh"]', dockerfile)
        self.assertFalse((ROOT / "elise_investigator/Dockerfile.rc13").exists())
        self.assertFalse((ROOT / "elise_investigator/run_rc13.sh").exists())
        self.assertIn('version: "0.3.0-rc.13"', (ROOT / "elise_investigator/config.yaml").read_text())
        self.assertEqual(candidate.VERSION, "0.3.0-rc.13")

    def test_workflow_tests_before_building_separate_candidate(self):
        workflow = (ROOT / ".github/workflows/publish-v2-rc13-image.yml").read_text()
        self.assertIn("refs/heads/candidate-v2-rc13-proof-retention", workflow)
        self.assertIn("elise-investigator-v2-rc13-private:0.3.0-rc.13", workflow)
        self.assertIn("file: ./elise_investigator/Dockerfile\n", workflow)
        self.assertLess(workflow.index("unittest discover"), workflow.index("push: true"))

    async def test_bootstrap_uses_existing_stream_database_and_shutdown_order(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CausalRecorder(Path(directory) / "memory.sqlite3")
            stream = object()
            app = web.Application()
            app["causal_recorder"] = recorder
            app["causal_worker"] = SimpleNamespace(stream=stream)
            app["activity_reader_dev63"] = ActivityTraceReaderRC13(object())
            with patch.object(candidate.impl, "create_app", AsyncMock(return_value=app)), \
                 patch.object(candidate.impl, "VERSION"), \
                 patch.object(candidate.impl, "ActivityTraceReader"), \
                 patch.object(candidate.impl, "_answer"):
                actual = await candidate.create_app()
            self.assertIs(actual, app)
            self.assertIsInstance(app["causal_worker"].stream, ObservedMemoryStream)
            self.assertIs(app["causal_worker"].stream.stream, stream)
            self.assertIs(app["activity_reader_dev63"].archive.db, recorder._db)
            app.freeze()
            await app.startup()
            self.assertTrue(app["proof_capture_rc13"].status()["running"])
            await app.shutdown()
            self.assertFalse(app["proof_capture_rc13"].status()["running"])
            recorder.close()
