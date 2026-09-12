from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2
from causal_response import answer_from_record

VERSION = "0.3.0-rc.6"


def _answer_with_event_age(record) -> tuple[str, bool]:
    """RC6 presentation-only wrapper for the live Activity response path.

    RC6 is the RC5.1 implementation repackaged under a clean candidate version.
    The causal engine remains unchanged. The live response path uses the common
    causal_response renderer so records carrying event_time include relative age.
    """
    answer = answer_from_record(record)
    found = bool(
        record.origin_type in {"user", "alexa"}
        or (record.origin_type in {"automation", "script"} and record.reason)
    )
    return answer, found


async def create_app() -> web.Application:
    """Candidate terrain V2 RC6, functionally identical to corrected RC5.1."""
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    impl._answer = _answer_with_event_age
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
