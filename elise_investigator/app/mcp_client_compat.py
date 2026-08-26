from __future__ import annotations

import re
from typing import Any

from mcp_client import MCPReadOnlyClient


class CompatibleMCPReadOnlyClient(MCPReadOnlyClient):
    """Terrain-compatible HA-MCP discovery for Supervisor app metadata.

    The base client already enforces the read-only MCP contract. This subclass
    only broadens app discovery so a store-prefixed or hyphenated installed slug
    can still be recognized from the official HA-MCP metadata returned by
    Supervisor.
    """

    OFFICIAL_NAME = "home assistant mcp server"
    OFFICIAL_SOURCE = "homeassistant-ai/ha-mcp"

    @staticmethod
    def _norm(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @classmethod
    def _is_official_metadata(cls, addon: dict[str, Any]) -> bool:
        name = cls._norm(addon.get("name"))
        source_text = " ".join(
            str(addon.get(key) or "").lower()
            for key in ("url", "repository")
        )
        return name == cls.OFFICIAL_NAME and cls.OFFICIAL_SOURCE in source_text

    @classmethod
    def _matching_slugs(cls, addons: list[dict[str, Any]]) -> list[str]:
        stable: list[str] = []
        dev: list[str] = []

        for addon in addons:
            slug = str(addon.get("slug") or "").strip()
            if not slug:
                continue

            slug_normalized = slug.lower().replace("-", "_")
            slug_match = (
                slug_normalized == "ha_mcp"
                or slug_normalized.endswith("_ha_mcp")
                or slug_normalized == "ha_mcp_dev"
                or slug_normalized.endswith("_ha_mcp_dev")
            )
            metadata_match = cls._is_official_metadata(addon)

            if not slug_match and not metadata_match:
                continue

            is_dev = (
                slug_normalized == "ha_mcp_dev"
                or slug_normalized.endswith("_ha_mcp_dev")
                or "development" in cls._norm(addon.get("name"))
            )
            target = dev if is_dev else stable
            if slug not in target:
                target.append(slug)

        return stable + dev
