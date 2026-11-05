"""Validate a proposed test manifest without changing Home Assistant."""

from pathlib import Path

from awesomeversion import AwesomeVersion
import yaml

ROOT = Path(__file__).resolve().parent
reference = yaml.safe_load((ROOT / "rc14_reference_manifest.yaml").read_text())
candidate = yaml.safe_load((ROOT / "proposed_rc15_manifest.yaml").read_text())

assert reference["version"] == "0.3.0-rc.14"
assert reference["image"] == "ghcr.io/brunofoxmulder/elise-investigator-v2-rc14-private"
assert candidate["version"] == "0.3.0-rc.15"
assert candidate["image"] == "ghcr.io/brunofoxmulder/elise-investigator-rc15-test"
assert AwesomeVersion(candidate["version"]) > AwesomeVersion(reference["version"])
for key in {"version", "image", "description"}:
    reference.pop(key)
    candidate.pop(key)
assert candidate == reference, "Application configuration or permissions unexpectedly changed"
print("Manifest: exact OCI tag, upgrade ordering, settings and permissions verified")
