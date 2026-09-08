from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Dev66PackagingTests(unittest.TestCase):
    def test_dedicated_launcher_and_dockerfile(self):
        launcher = (ROOT / "elise_investigator" / "run_dev66.sh").read_text()
        dockerfile = (ROOT / "elise_investigator" / "Dockerfile.dev66").read_text()
        entrypoint = (ROOT / "elise_investigator" / "app" / "main_dev66.py").read_text()
        self.assertIn("exec python3 main_dev66.py", launcher)
        self.assertIn("RUN chmod 0755 /run_dev66.sh", dockerfile)
        self.assertIn('CMD ["/usr/bin/with-contenv", "bashio", "/run_dev66.sh"]', dockerfile)
        self.assertIn('VERSION = "0.2.0-dev.66"', entrypoint)

if __name__ == "__main__":
    unittest.main()
