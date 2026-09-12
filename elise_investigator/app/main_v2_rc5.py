from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2

VERSION = "0.3.0-rc.5"


async def create_app() -> web.Application:
    """Candidate terrain V2 RC5.

    RC5 est strictement dérivée de RC4. Le moteur causal V2 et les chemins
    terrain validés restent inchangés ; seule la réponse utilisateur ajoute
    l'âge relatif de l'événement observé à partir de event_time.
    """
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
