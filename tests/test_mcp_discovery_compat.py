import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from mcp_client_compat import CompatibleMCPReadOnlyClient


class TestCompatibleMCPDiscovery(unittest.TestCase):
    def test_accepts_existing_underscore_slug(self):
        slugs = CompatibleMCPReadOnlyClient._matching_slugs(
            [{"slug": "abc123_ha_mcp"}]
        )
        self.assertEqual(slugs, ["abc123_ha_mcp"])

    def test_accepts_hyphenated_slug(self):
        slugs = CompatibleMCPReadOnlyClient._matching_slugs(
            [{"slug": "abc123_ha-mcp"}]
        )
        self.assertEqual(slugs, ["abc123_ha-mcp"])

    def test_accepts_official_name_with_unexpected_slug_and_no_source_metadata(self):
        slugs = CompatibleMCPReadOnlyClient._matching_slugs(
            [
                {
                    "slug": "unexpected_store_identifier",
                    "name": "Home Assistant MCP Server",
                    "repository": "store-entry",
                }
            ]
        )
        self.assertEqual(slugs, ["unexpected_store_identifier"])

    def test_accepts_official_development_name(self):
        slugs = CompatibleMCPReadOnlyClient._matching_slugs(
            [
                {
                    "slug": "unexpected_dev_identifier",
                    "name": "Home Assistant MCP Server Development",
                }
            ]
        )
        self.assertEqual(slugs, ["unexpected_dev_identifier"])

    def test_rejects_unrelated_name(self):
        slugs = CompatibleMCPReadOnlyClient._matching_slugs(
            [{"slug": "other_tool", "name": "Another MCP Server"}]
        )
        self.assertEqual(slugs, [])

    def test_stable_is_prioritized_before_dev(self):
        slugs = CompatibleMCPReadOnlyClient._matching_slugs(
            [
                {"slug": "repo_ha_mcp_dev"},
                {"slug": "repo_ha_mcp"},
            ]
        )
        self.assertEqual(slugs, ["repo_ha_mcp", "repo_ha_mcp_dev"])


if __name__ == "__main__":
    unittest.main()
