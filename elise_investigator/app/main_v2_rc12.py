from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_rc12 import ActivityTraceReaderRC12
from main_v2_rc11 import _answer_with_event_age

VERSION = "0.3.0-rc.12"


async def create_app() -> web.Application:
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderRC12
    impl._answer = _answer_with_event_age
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
