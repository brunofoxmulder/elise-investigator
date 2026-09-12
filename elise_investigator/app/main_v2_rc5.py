from __future__ import annotations

from aiohttp import web

import main_dev63 as impl
from activity_reader_v2 import ActivityTraceReaderV2
from causal_response import answer_from_record

VERSION = "0.3.0-rc.5"


def _answer_with_event_age(record) -> tuple[str, bool]:
    """RC5 presentation-only wrapper for the live Activity response path.

    main_dev63 owns the HTTP path used by the add-on and has its own historical
    _answer renderer. RC5 must therefore replace that renderer explicitly so
    every record carrying event_time gets the same relative event age already
    covered by causal_response tests. No causal evidence or resolver state is
    changed here.
    """
    answer = answer_from_record(record)
    found = bool(
        record.origin_type in {"user", "alexa"}
        or (record.origin_type in {"automation", "script"} and record.reason)
    )
    return answer, found


async def create_app() -> web.Application:
    """Candidate terrain V2 RC5.

    RC5 est strictement dérivée de RC4. Le moteur causal V2 et les chemins
    terrain validés restent inchangés ; seule la réponse utilisateur ajoute
    l'âge relatif de l'événement observé à partir de event_time.
    """
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderV2
    impl._answer = _answer_with_event_age
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
