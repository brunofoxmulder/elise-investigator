from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2

VERSION = "0.3.0-rc.4"


async def create_app() -> web.Application:
    """Candidate terrain V2 RC4.

    RC4 conserve l'architecture V2/RC3 et ajoute uniquement l'enrichissement
    cover-only des décisions calculées dans les variables runtime de la trace HA.
    Aucun chemin non-cover n'est modifié.
    """
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
