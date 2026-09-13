from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2
from causal_response import answer_from_record

VERSION = "0.3.0-rc.7"


def _answer_with_event_age(record) -> tuple[str, bool]:
    """RC7 keeps the validated RC6 presentation path unchanged."""
    answer = answer_from_record(record)
    found = bool(
        record.origin_type in {"user", "alexa"}
        or (record.origin_type in {"automation", "script"} and record.reason)
    )
    return answer, found


async def create_app() -> web.Application:
    """RC7: generic trace-selection hardening, no resolver semantic change."""
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    impl._answer = _answer_with_event_age
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
