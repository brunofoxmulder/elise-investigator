from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev46 as dev46
from memory_worker_dev54 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.54"
CONSCIOUS_MEMORY_FILE = dev46.CONSCIOUS_MEMORY_FILE


def configure_dev54() -> None:
    """Keep the complete dev.46 engine and replace only its memory worker."""
    dev46.configure_dev46()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.46", "Mémoire consciente · dev.54"
    )


async def create_app() -> web.Application:
    configure_dev54()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, TargetedConsciousMemoryWorker):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
