from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2

VERSION = "0.3.0-rc.1"


async def create_app() -> web.Application:
    """Candidate terrain du moteur causal V2.

    Aucun changement de logique causale n'est introduit ici : ce wrapper branche
    uniquement l'API Investigator existante sur ActivityTraceReaderV2.
    """
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
