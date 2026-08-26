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

    def test_accepts_local_webhook_url(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            "http://10.0.0.5:8123/api/webhook/mcp_abcdefghijk"
        )
        self.assertEqual(connection.host, "10.0.0.5")
        self.assertEqual(connection.port, 8123)

    def test_accepts_unknown_secret_path_shape_for_handshake_validation(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            "http://192.168.1.20:9584/opaque-secret-format-v2"
        )
        self.assertEqual(connection.port, 9584)
        self.assertIn("opaque-secret-format-v2", connection.url)

    def test_accepts_custom_webhook_id_without_mcp_prefix(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            "http://192.168.1.20:8123/api/webhook/custom-secret-value"
        )
        self.assertEqual(connection.port, 8123)

    def test_normalizes_line_break_and_tab_from_clipboard(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            "http://192.168.1.20:8123/api/webhook/\nmcp_abcde\tfghijk"
        )
        self.assertEqual(
            connection.url,
            "http://192.168.1.20:8123/api/webhook/mcp_abcdefghijk",
        )

    def test_normalizes_nbsp_and_zero_width_format_chars(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            "http://192.168.1.20:9584/private_abcd\u00a0efgh\u200bijk"
        )
        self.assertEqual(
            connection.url,
            "http://192.168.1.20:9584/private_abcdefghijk",
        )

    def test_normalization_does_not_change_secret_characters(self):
        connection = InProcessMCPReadOnlyClient._connection_from_url(
            " http://192.168.1.20:9584/private_aB9_-xyz "
        )
        self.assertTrue(connection.url.endswith("/private_aB9_-xyz"))

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

    def test_rejects_root_path(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url(
                "http://192.168.1.20:9584/"
            )

    def test_rejects_unapproved_local_port(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url(
                "http://192.168.1.20:9999/opaque-secret"
            )

    def test_rejects_query_or_fragment(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._connection_from_url(
                "http://192.168.1.20:9584/opaque-secret?x=1"
            )


if __name__ == "__main__":
    unittest.main()
