from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2

VERSION = "0.2.0-arch-v2"


async def create_app() -> web.Application:
    """Run the normal Investigator API with the V2 reader for architecture tests only.

    This module is intentionally not referenced by run.sh, Docker packaging or the HAOS
    add-on manifest. Promotion to an installable candidate requires a separate decision.
    """
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
