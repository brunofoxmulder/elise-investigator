from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev55 as dev55
from memory_worker_dev56 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.56"
CONSCIOUS_MEMORY_FILE = dev55.CONSCIOUS_MEMORY_FILE


def configure_dev56() -> None:
    """Layer native Logbook causality on top of validated dev.55 behaviour."""
    dev55.configure_dev55()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.55", "Mémoire consciente · dev.56"
    )


async def create_app() -> web.Application:
    configure_dev56()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, TargetedConsciousMemoryWorker):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
