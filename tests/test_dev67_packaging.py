from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Dev67PackagingTests(unittest.TestCase):
    def test_reuses_proven_dev62_packaging_contract(self):
        dockerfile = (ROOT / "elise_investigator" / "Dockerfile").read_text()
        launcher = (ROOT / "elise_investigator" / "run.sh").read_text()
        entrypoint = (ROOT / "elise_investigator" / "app" / "main_dev67.py").read_text()

        self.assertIn("COPY run.sh /run.sh", dockerfile)
        self.assertIn("RUN chmod 0755 /run.sh", dockerfile)
        self.assertIn('CMD ["/run.sh"]', dockerfile)
        self.assertIn("#!/usr/bin/with-contenv bashio", launcher)
        self.assertIn("exec python3 main_dev67.py", launcher)
        self.assertIn('VERSION = "0.2.0-dev.67"', entrypoint)
        self.assertNotIn("Dockerfile.dev66", dockerfile)
        self.assertNotIn("run_dev66.sh", launcher)


if __name__ == "__main__":
    unittest.main()
