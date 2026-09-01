from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev48 as dev48
from causal_recorder_dev49 import LatestPrimaryStateRecorder
from memory_worker_dev49 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.49"
CONSCIOUS_MEMORY_FILE = dev48.CONSCIOUS_MEMORY_FILE


def configure_dev49() -> None:
    """Layer the two narrow dev.49 regression fixes on top of dev.48."""
    dev48.configure_dev48()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.RelevantCausalRecorder = LatestPrimaryStateRecorder
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.48", "Mémoire consciente · dev.49"
    )


async def create_app() -> web.Application:
    configure_dev49()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, TargetedConsciousMemoryWorker):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
