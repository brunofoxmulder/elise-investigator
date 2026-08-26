import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import main_mcp
from mcp_trace_explorer import MAX_CANDIDATES, TRACE_LIST_LIMIT


class TestDev28MCPUI(unittest.TestCase):
    def test_version_text_button_and_independent_picker_are_dev28(self):
        self.assertEqual(main_mcp.VERSION, "0.2.0-dev.28")
        self.assertIn('id="mcp_entity_search"', main_mcp._MCP_CARD)
        self.assertIn('id="mcp_entity"', main_mcp._MCP_CARD)
        self.assertIn("Sélecteur MCP autonome", main_mcp._MCP_CARD)
        self.assertIn('id="mcp_copy_text"', main_mcp._MCP_CARD)
        self.assertIn('>Texte</button>', main_mcp._MCP_CARD)
        self.assertIn("Rien n'est envoyé automatiquement", main_mcp._MCP_CARD)

    def test_mcp_picker_uses_existing_read_only_entity_catalog(self):
        script = main_mcp._MCP_SCRIPT
        self.assertIn("async function loadMcpEntities()", script)
        self.assertIn("fetch(api('api/v1/entities'))", script)
        self.assertIn("function findMcpMatches", script)
        self.assertIn("function mcpSetSelected", script)
        self.assertIn("mcpEntitySearch.addEventListener('input'", script)

    def test_mcp_search_no_longer_depends_on_investigator_picker(self):
        script = main_mcp._MCP_SCRIPT
        start = script.index("mcpGo.addEventListener")
        end = script.index("loadMcpEntities().catch", start)
        handler = script[start:end]

        self.assertIn("mcpEntityEl.value", handler)
        self.assertIn("entity_id:mcpEntityEl.value", handler)
        self.assertNotIn("entityEl.value", handler)
        self.assertNotIn("loadEntities()", handler)
        self.assertNotIn("resolveTypedValue()", handler)
        self.assertNotIn("renderError(", handler)

    def test_export_is_compact_and_does_not_copy_raw_mcp_payload(self):
        script = main_mcp._MCP_SCRIPT
        start = script.index("function buildMcpShareText")
        end = script.index("async function loadMcpStatus")
        builder = script[start:end]

        for expected in (
            "ÉLISE INVESTIGATOR — RÉSUMÉ MCP",
            "Entity ID:",
            "Question:",
            "Réponse:",
            "Historique utile:",
            "Candidats:",
            "Traces:",
            "Piste détaillée:",
            "Détail compact:",
            "Lecture seule:",
            "IA:",
            "Verdict causal Investigator: inchangé",
            "Sélection temporelle = preuve causale: non",
        ):
            self.assertIn(expected, builder)

        self.assertNotIn("JSON.stringify(d", builder)
        self.assertNotIn("d.mcp", builder)
        self.assertNotIn("endpoint", builder.lower())

    def test_text_button_is_clipboard_only(self):
        script = main_mcp._MCP_SCRIPT
        start = script.index("mcpCopyText.addEventListener")
        end = script.index("mcpGo.addEventListener")
        handler = script[start:end]

        self.assertIn("copyText(buildMcpShareText(lastMcpResult))", handler)
        self.assertNotIn("fetch(", handler)
        self.assertNotIn("XMLHttpRequest", handler)
        self.assertNotIn("sendBeacon", handler)

    def test_dev26_trace_bounds_are_unchanged(self):
        self.assertEqual(MAX_CANDIDATES, 6)
        self.assertEqual(TRACE_LIST_LIMIT, 3)
        self.assertIn("detail_limit", Path(APP_DIR / "mcp_trace_explorer.py").read_text())
        self.assertIn('"detail_limit": 1', Path(APP_DIR / "mcp_trace_explorer.py").read_text())

    def test_generated_browser_script_has_valid_javascript_syntax(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(main_mcp._MCP_SCRIPT)
            path = handle.name
        try:
            completed = subprocess.run(
                [node, "--check", path],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
