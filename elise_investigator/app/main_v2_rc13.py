from __future__ import annotations

import logging

from aiohttp import web

import main as base
import main_dev63 as impl
from activity_reader_rc13 import ActivityTraceReaderRC13
from main_v2_rc11 import _answer_with_event_age
from proof_archive_rc13 import ProofArchive
from proof_capture_rc13 import ObservedMemoryStream, ProofCapture

VERSION = "0.3.0-rc.13"


async def _start_capture(app):
    await app["proof_capture_rc13"].start()


async def _stop_capture(app):
    await app["proof_capture_rc13"].stop()


async def _proof_status(request):
    app = request.app
    capture = app.get("proof_capture_rc13")
    return web.json_response({"version": VERSION, "available": capture is not None,
        "capture": capture.status() if capture else None,
        "retention_hours": app["causal_recorder"].retention_hours,
        "archive_failures": app["activity_reader_dev63"].archive_failures,
        "read_only_home_assistant": True})


async def create_app() -> web.Application:
    impl.VERSION = VERSION
    impl.ActivityTraceReader = ActivityTraceReaderRC13
    impl._answer = _answer_with_event_age
    app = await impl.create_app()
    reader = app["activity_reader_dev63"]
    try:
        archive = ProofArchive(app["causal_recorder"])
    except Exception as exc:
        logging.getLogger(__name__).warning("Proof archive unavailable (%s)", type(exc).__name__)
    else:
        reader.archive = archive
        capture = ProofCapture(reader, archive)
        app["proof_capture_rc13"] = capture
        worker = app["causal_worker"]
        worker.stream = ObservedMemoryStream(worker.stream, capture)
        app.on_startup.append(_start_capture)
        app.on_shutdown.append(_stop_capture)
    base.add_ingress_get(app, "/api/v1/proofs/status", _proof_status)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
