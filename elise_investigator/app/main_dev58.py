from __future__ import annotations

from typing import Any

from aiohttp import web

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev55 as dev55
from causal_recorder import CausalRecorder
from memory_response_dev34 import answer_from_memory, cause_found
from memory_selection_dev58 import find_best_functional
from memory_worker_dev57 import TargetedConsciousMemoryWorker
from models import InvestigationRequest

VERSION = "0.2.0-dev.58"
CONSCIOUS_MEMORY_FILE = dev55.CONSCIOUS_MEMORY_FILE


def _memory_payload_dev58(app: web.Application, req: InvestigationRequest) -> dict[str, Any]:
    recorder: CausalRecorder = app["causal_recorder"]
    record = find_best_functional(
        recorder,
        req.entity_id,
        observed_time=req.observed_time,
        observed_value=req.observed_value,
        attribute=req.attribute,
    )
    if record is None:
        return {
            "status": "confirmed",
            "entity_id": req.entity_id,
            "answer_text": "Je n'ai pas trouvé la cause.",
            "cause_found": False,
            "result_source": "conscious_memory_empty",
            "read_only": True,
            "version": VERSION,
        }

    return {
        "status": "confirmed",
        "entity_id": record.entity_id,
        "answer_text": answer_from_memory(record),
        "cause_found": cause_found(record),
        "result_source": "conscious_memory",
        "event_time": record.event_time,
        "event_kind": record.event_kind,
        "before_value": record.before_value,
        "after_value": record.after_value,
        "attribute": record.attribute,
        "origin_type": record.origin_type,
        "reason": record.reason,
        "journal": {
            **record.llm_payload(),
            "before": record.before_value,
            "after": record.after_value,
        },
        "read_only": True,
        "version": VERSION,
    }


def configure_dev58() -> None:
    """Keep dev.57 Activity causality and fix plain light-state event selection."""
    dev55.configure_dev55()
    dev34.VERSION = VERSION
    dev29.JOURNAL_FILE = CONSCIOUS_MEMORY_FILE
    dev34.ConsciousMemoryWorker = TargetedConsciousMemoryWorker
    dev34._memory_payload = _memory_payload_dev58
    dev34._MEMORY_CARD = dev34._MEMORY_CARD.replace(
        "Mémoire consciente · dev.55", "Mémoire consciente · dev.58"
    )


async def create_app() -> web.Application:
    configure_dev58()
    app = await dev34.create_app()
    worker = app.get("causal_worker")
    mcp_client = app.get("mcp")
    if isinstance(worker, TargetedConsciousMemoryWorker):
        worker.targeted.set_mcp_client(mcp_client)
    return app


if __name__ == "__main__":
    # No behavior change: this commit only retriggers CI so the new publisher can
    # build the exact green dev.58 commit through workflow_run.
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
