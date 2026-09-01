from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev45 as dev45
from memory_worker_dev45 import TargetedConsciousMemoryWorker as Dev45TargetedConsciousMemoryWorker
from memory_worker_dev46 import TargetedConsciousMemoryWorker

# Dev.51 is deliberately a version-only repackaging of the last terrain-valid
# causal engine: dev.46. No causal, cover, light, memory or enrichment logic is
# changed here. The higher version number only allows Home Assistant to install
# this rollback cleanly over dev.50.
VERSION = "0.2.0-dev.51"
CONSCIOUS_MEMORY_FILE = dev45.CONSCIOUS_MEMORY_FILE


def configure_dev51() -> None:
    dev45.configure_dev45()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.45", "Mémoire consciente · dev.51 (moteur dev.46)"
    )


async def create_app() -> web.Application:
    configure_dev51()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, (TargetedConsciousMemoryWorker, Dev45TargetedConsciousMemoryWorker)):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
