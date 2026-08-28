from __future__ import annotations

from pathlib import Path

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev36 as dev36
import memory_worker_dev34 as memory_base
from memory_worker_dev37 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.37"
CONSCIOUS_MEMORY_FILE = Path("/data") / "conscious_memory.sqlite3"
_CONTEXT_RETENTION_SECONDS = 12 * 60 * 60


def configure_dev37() -> None:
    """Keep dev.36 memory capture and polish only causal enrichment."""
    dev36.configure_dev36()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker

    # The lists remain strictly bounded by _MAX_TRIGGERS/_MAX_COMMANDS. Extending
    # their time horizon fixes valid delayed actions (2 min, 5 min, hours) without
    # reintroducing a queue or unbounded memory growth.
    memory_base._PENDING_SECONDS = float(_CONTEXT_RETENTION_SECONDS)

    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.36", "Mémoire consciente · dev.37"
    )


async def create_app() -> web.Application:
    configure_dev37()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, TargetedConsciousMemoryWorker):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
