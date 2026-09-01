from __future__ import annotations

from pathlib import Path

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev45 as dev45
import main_dev46 as dev46
from memory_worker_dev45 import TargetedConsciousMemoryWorker as Dev45TargetedConsciousMemoryWorker
from memory_worker_dev46 import TargetedConsciousMemoryWorker

# Dev.52 is a clean rebuild from the exact dev.46 code line.
# The causal engine is not modified. The only functional difference is storage
# isolation: records written by dev.47-dev.51 cannot be reused by this runtime.
VERSION = "0.2.0-dev.52"
CONSCIOUS_MEMORY_FILE = Path("/data") / "conscious_memory_dev52.sqlite3"
REQUEST_JOURNAL_FILE = Path("/data") / "investigator_requests_dev52.sqlite3"


def configure_dev52() -> None:
    # Restore the complete dev.46 configuration first, then change only runtime
    # identity and storage paths. This keeps covers, brightness episodes and
    # causal enrichment exactly on the dev.46 implementation.
    dev46.configure_dev46()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.REQUEST_JOURNAL_FILE = REQUEST_JOURNAL_FILE
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.46",
        "Mémoire consciente · dev.52 (socle dev.46 propre)",
    )


async def create_app() -> web.Application:
    configure_dev52()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, (TargetedConsciousMemoryWorker, Dev45TargetedConsciousMemoryWorker)):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
