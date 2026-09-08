from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Dev64PackagingTests(unittest.TestCase):
    def test_dedicated_launcher_and_dockerfile(self):
        launcher = (ROOT / "elise_investigator" / "run_dev64.sh").read_text()
        dockerfile = (ROOT / "elise_investigator" / "Dockerfile.dev64").read_text()
        entrypoint = (ROOT / "elise_investigator" / "app" / "main_dev64.py").read_text()

        self.assertIn("exec python3 main_dev64.py", launcher)
        self.assertIn('CMD ["/usr/bin/with-contenv", "bashio", "/run_dev64.sh"]', dockerfile)
        self.assertIn('VERSION = "0.2.0-dev.64"', entrypoint)
        self.assertNotIn("run_dev63.sh", dockerfile)


if __name__ == "__main__":
    unittest.main()
