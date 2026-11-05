import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'elise_investigator/app'))
import main_v2_rc15_ha202611 as candidate


class CandidatePackagingTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_reuses_rc13_lifecycle_with_new_version(self):
        expected = object()
        with patch.object(candidate.rc13, 'create_app', new=AsyncMock(return_value=expected)) as create:
            self.assertIs(await candidate.create_app(), expected)
            create.assert_awaited_once_with(version='0.3.0-rc.15')

    def test_separate_packaging_and_existing_launcher_unchanged(self):
        launcher = (ROOT / 'elise_investigator/run_rc15_ha202611.sh').read_text()
        dockerfile = (ROOT / 'elise_investigator/Dockerfile.rc15_ha202611').read_text()
        current = (ROOT / 'elise_investigator/run.sh').read_text()
        self.assertIn('exec python3 main_v2_rc15_ha202611.py', launcher)
        self.assertIn('COPY run_rc15_ha202611.sh /run.sh', dockerfile)
        self.assertEqual(current, '#!/usr/bin/with-contenv bashio\nset -e\ncd /app\nexec python3 main_v2_rc14.py\n')
