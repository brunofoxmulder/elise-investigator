from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev47 as dev47
from causal_recorder_dev47 import LatestPrimaryStateRecorder
from memory_worker_dev48 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.48"
CONSCIOUS_MEMORY_FILE = dev47.CONSCIOUS_MEMORY_FILE


def configure_dev48() -> None:
    """Layer the bounded primary on/off retry on top of dev.47."""
    dev47.configure_dev47()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.RelevantCausalRecorder = LatestPrimaryStateRecorder
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.47", "Mémoire consciente · dev.48"
    )


async def create_app() -> web.Application:
    configure_dev48()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, TargetedConsciousMemoryWorker):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
