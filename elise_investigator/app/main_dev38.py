from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev37 as dev37
from memory_worker_dev37 import TargetedConsciousMemoryWorker as Dev37TargetedConsciousMemoryWorker
from memory_worker_dev38 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.38"
CONSCIOUS_MEMORY_FILE = dev37.CONSCIOUS_MEMORY_FILE


def configure_dev38() -> None:
    """Keep dev.37 behavior and replace only the cover terminal enricher."""
    dev37.configure_dev37()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.37", "Mémoire consciente · dev.38"
    )


async def create_app() -> web.Application:
    configure_dev38()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, (TargetedConsciousMemoryWorker, Dev37TargetedConsciousMemoryWorker)):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
