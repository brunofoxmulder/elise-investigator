from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2

VERSION = "0.3.0-rc.2"


async def create_app() -> web.Application:
    """Candidate terrain V2 RC2.

    Le wrapper conserve l'API Investigator existante et branche ActivityTraceReaderV2.
    Les changements fonctionnels RC2 restent limités au traitement des covers préparé
    sur fix-v2-cover-episodes.
    """
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
