from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev38 as dev38
from memory_worker_dev38 import TargetedConsciousMemoryWorker as Dev38TargetedConsciousMemoryWorker
from memory_worker_dev39 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.39"
CONSCIOUS_MEMORY_FILE = dev38.CONSCIOUS_MEMORY_FILE


def configure_dev39() -> None:
    """Keep dev.38 behavior and recover only proven cover episode start causes."""
    dev38.configure_dev38()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.38", "Mémoire consciente · dev.39"
    )


async def create_app() -> web.Application:
    configure_dev39()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, (TargetedConsciousMemoryWorker, Dev38TargetedConsciousMemoryWorker)):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
