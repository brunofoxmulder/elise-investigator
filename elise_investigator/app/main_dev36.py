from __future__ import annotations

from pathlib import Path

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
from memory_worker_dev36 import TargetedConsciousMemoryWorker

VERSION = "0.2.0-dev.36"
CONSCIOUS_MEMORY_FILE = Path("/data") / "conscious_memory.sqlite3"


def configure_dev36() -> None:
    """Keep one Investigator App and replace only the dev.35 memory worker."""
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker

    # Keep the existing interrogation IHM; update only its diagnostic wording.
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.34", "Mémoire consciente · dev.36"
    )
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "aucune enquête profonde n'est lancée dans le chemin conversationnel.",
        "la cause est enrichie au moment du changement par une lecture ciblée et le chemin conversationnel ne lance aucune enquête.",
    )
    dev34._MEMORY_SCRIPT = dev34._MEMORY_SCRIPT.replace(
        "Chemin normal : événements HA → mémoire locale → réponse · aucune file d’enrichissement · Home Assistant : ",
        "Chemin normal : changement HA → mémoire → enrichissement ciblé → réponse · aucune file d’enrichissement · Home Assistant : ",
    )


async def create_app() -> web.Application:
    configure_dev36()
    return await dev34.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
