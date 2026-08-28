import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_settings import CausalSettings, CausalSettingsStore


class TestCausalSettings(unittest.TestCase):
    def test_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = CausalSettingsStore(path)
            self.assertEqual(store.load(), CausalSettings(retention_hours=12, deep_fallback=True))
            store.save(CausalSettings(retention_hours=24, deep_fallback=False))
            self.assertEqual(store.load(), CausalSettings(retention_hours=24, deep_fallback=False))

    def test_corrupt_or_invalid_file_falls_back_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"retention_hours": 999, "deep_fallback": "yes"}', encoding="utf-8")
            settings = CausalSettingsStore(path).load()
            self.assertEqual(settings.retention_hours, 12)
            self.assertTrue(settings.deep_fallback)


if __name__ == "__main__":
    unittest.main()
