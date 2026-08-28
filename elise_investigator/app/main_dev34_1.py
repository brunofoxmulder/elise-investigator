from __future__ import annotations

from pathlib import Path

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34

VERSION = "0.2.0-dev.34.1"
CONSCIOUS_MEMORY_FILE = Path("/data") / "conscious_memory.sqlite3"


def configure_storage_isolation() -> None:
    """Keep dev.34 memory separate from the historical dev.29-dev.33 journal."""
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE


async def create_app() -> web.Application:
    configure_storage_isolation()
    return await dev34.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
