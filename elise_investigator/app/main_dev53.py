from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev45 as dev45
from memory_worker_dev45 import TargetedConsciousMemoryWorker as Dev45TargetedConsciousMemoryWorker
from memory_worker_dev46 import TargetedConsciousMemoryWorker

# Dev.53 is the operational rollback requested after dev.47-dev.52.
# It restores the COMPLETE dev.46 runtime contract, including the original
# persistent storage paths. No causal, cover, light, memory or MCP behavior is
# changed versus dev.46. Only the reported package/runtime version is advanced
# so Home Assistant can install it over newer failed candidates.
VERSION = "0.2.0-dev.53"
CONSCIOUS_MEMORY_FILE = dev45.CONSCIOUS_MEMORY_FILE


def configure_dev53() -> None:
    # Exact dev.46 configuration chain.
    dev45.configure_dev45()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.45", "Mémoire consciente · dev.53 (socle dev.46 restauré)"
    )


async def create_app() -> web.Application:
    configure_dev53()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, (TargetedConsciousMemoryWorker, Dev45TargetedConsciousMemoryWorker)):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
