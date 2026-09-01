from __future__ import annotations

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev49 as dev49
from causal_recorder_dev49 import LatestPrimaryStateRecorder
from memory_worker_dev50 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.50"
CONSCIOUS_MEMORY_FILE = dev49.CONSCIOUS_MEMORY_FILE


def configure_dev50() -> None:
    """Layer the narrow nested-trace cause recovery on top of dev.49."""
    dev49.configure_dev49()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.RelevantCausalRecorder = LatestPrimaryStateRecorder
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.49", "Mémoire consciente · dev.50"
    )


async def create_app() -> web.Application:
    configure_dev50()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, TargetedConsciousMemoryWorker):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
