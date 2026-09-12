from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Dev67PackagingTests(unittest.TestCase):
    def test_reuses_proven_dev62_packaging_contract(self):
        dockerfile = (ROOT / "elise_investigator" / "Dockerfile").read_text()
        launcher = (ROOT / "elise_investigator" / "run.sh").read_text()

        self.assertIn("COPY run.sh /run.sh", dockerfile)
        self.assertIn("RUN chmod 0755 /run.sh", dockerfile)
        self.assertIn('CMD ["/run.sh"]', dockerfile)
        supported = (
            "main_dev67.py", "main_dev68.py", "main_dev69.py", "main_dev70.py",
            "main_dev71.py", "main_dev72.py", "main_dev73.py", "main_v2_rc1.py",
            "main_v2_rc2.py", "main_v2_rc3.py", "main_v2_rc4.py", "main_v2_rc5.py",
        )
        self.assertTrue(any(name in launcher for name in supported))

        expected_versions = {
            "main_dev67.py": "0.2.0-dev.67",
            "main_dev68.py": "0.2.0-dev.68",
            "main_dev69.py": "0.2.0-dev.69",
            "main_dev70.py": "0.2.0-dev.70",
            "main_dev71.py": "0.2.0-dev.71",
            "main_dev72.py": "0.2.0-dev.72",
            "main_dev73.py": "0.2.0-dev.73",
            "main_v2_rc1.py": "0.3.0-rc.1",
            "main_v2_rc2.py": "0.3.0-rc.2",
            "main_v2_rc3.py": "0.3.0-rc.3",
            "main_v2_rc4.py": "0.3.0-rc.4",
            "main_v2_rc5.py": "0.3.0-rc.5.1",
        }
        selected = next(name for name in supported if name in launcher)
        entrypoint = (ROOT / "elise_investigator" / "app" / selected).read_text()
        self.assertIn(f'VERSION = "{expected_versions[selected]}"', entrypoint)

        self.assertNotIn("Dockerfile.dev66", dockerfile)
        self.assertNotIn("run_dev66.sh", launcher)
        self.assertNotIn("run_dev71.sh", launcher)
        self.assertNotIn("run_dev72.sh", launcher)
        self.assertNotIn("run_dev73.sh", launcher)


if __name__ == "__main__":
    unittest.main()
