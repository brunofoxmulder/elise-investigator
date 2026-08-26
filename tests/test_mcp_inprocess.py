import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from mcp_client import MCPReadOnlyError
from mcp_client_inprocess import InProcessMCPReadOnlyClient


class TestInProcessMCPConnection(unittest.TestCase):
    def test_accepts_direct_private_lan_url(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            "http://192.168.1.20:9584/private_abcdefghijk"
        )
        self.assertEqual(connection.host, "192.168.1.20")
        self.assertEqual(connection.port, 9584)
        self.assertTrue(connection.read_only)
        self.assertNotIn("[SECRET]", connection.url)

    def test_accepts_local_webhook_url(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            "http://10.0.0.5:8123/api/webhook/mcp_abcdefghijk"
        )
        self.assertEqual(connection.host, "10.0.0.5")
        self.assertEqual(connection.port, 8123)

    def test_rejects_missing_url(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url("")

    def test_rejects_cloud_https_url(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url(
                "https://example.ui.nabu.casa/api/webhook/mcp_abcdefghijk"
            )

    def test_rejects_public_ip(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url(
                "http://8.8.8.8:9584/private_abcdefghijk"
            )

    def test_rejects_loopback_of_investigator_container(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url(
                "http://127.0.0.1:9584/private_abcdefghijk"
            )

    def test_rejects_unrecognized_path(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url(
                "http://192.168.1.20:9584/settings"
            )


if __name__ == "__main__":
    unittest.main()
