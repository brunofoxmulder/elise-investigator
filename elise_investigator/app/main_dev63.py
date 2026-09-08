from __future__ import annotations

from typing import Any

from aiohttp import web

import main as base
import main_dev30 as dev30
import main_dev34 as dev34
from activity_reader_dev63 import ActivityTraceReader
from conversation import ConversationResolutionError
from ha_client import HomeAssistantError

VERSION = "0.2.0-dev.63.1"


def _effect(record) -> str:
    name = record.entity_name or record.entity_id
    domain = record.entity_id.split(".", 1)[0]
    kind = record.event_kind
    if domain == "light" and kind == "turned_on":
        return f"{name} s'est allumée"
    if domain == "light" and kind == "turned_off":
        return f"{name} s'est éteinte"
    if kind == "turned_on":
        return f"{name} s'est activé"
    if kind == "turned_off":
        return f"{name} s'est désactivé"
    if domain == "cover" and kind == "opening":
        return f"{name} a commencé à s'ouvrir"
    if domain == "cover" and kind == "closing":
        return f"{name} a commencé à se fermer"
    if domain == "cover" and kind == "opened":
        return f"{name} s'est ouvert"
    if domain == "cover" and kind == "closed":
        return f"{name} s'est fermé"
    return f"{name} est passé à {record.after_value}"


def _answer(record) -> tuple[str, bool]:
    effect = _effect(record)
    if record.origin_type == "user":
        return f"{effect} à la suite d'une commande utilisateur.", True
    if record.origin_type in {"automation", "script"}:
        if record.reason:
            return f"{effect} parce que {record.reason.rstrip('.')}.", True
        if record.source_name:
            return f"{effect} par {record.source_name}.", True
        if record.source_entity_id:
            return f"{effect} par {record.source_entity_id}.", True
    return "Je n'ai pas trouvé la cause.", False


async def _activity_payload(app: web.Application, req) -> dict[str, Any]:
    settings = app.get("causal_settings")
    hours = int(getattr(settings, "retention_hours", 12) or 12)
    reader: ActivityTraceReader = app["activity_reader_dev63"]
    record = await reader.investigate(req.entity_id, hours=hours)
    if record is None:
        return {"status":"confirmed","entity_id":req.entity_id,"answer_text":"Je n'ai pas trouvé la cause.","cause_found":False,"result_source":"ha_logbook_empty","read_only":True,"version":VERSION}
    try:
        state = await app["ha"].get_state(req.entity_id)
        attrs = state.get("attributes") if isinstance(state, dict) else None
        if isinstance(attrs, dict) and attrs.get("friendly_name"):
            record.entity_name = str(attrs["friendly_name"])
    except Exception:
        pass
    answer, found = _answer(record)
    return {"status":"confirmed","entity_id":record.entity_id,"answer_text":answer,"cause_found":found,"result_source":"ha_logbook_trace","event_time":record.event_time,"event_kind":record.event_kind,"after_value":record.after_value,"origin_type":record.origin_type,"source_entity_id":record.source_entity_id,"source_name":record.source_name,"reason":record.reason,"reason_code":record.reason_code,"journal":record.llm_payload(),"read_only":True,"version":VERSION}


async def activity_investigate(request: web.Request) -> web.Response:
    data: Any = None
    entity_id = ""
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("Corps JSON invalide")
        entity_id = str(data.get("entity_id") or "").strip()
        req = dev30._request_from_payload(data)
        payload = await _activity_payload(request.app, req)
        dev34._journal_io(request.app, "/api/v1/investigate", data, payload)
        return web.json_response(payload)
    except Exception as exc:
        payload = {"status":"confirmed","entity_id":entity_id,"answer_text":"Je n'ai pas trouvé la cause.","cause_found":False,"diagnostic_error":str(exc),"read_only":True,"version":VERSION}
        dev34._journal_io(request.app, "/api/v1/investigate", data, payload)
        return web.json_response(payload, status=200 if entity_id else 400)


async def activity_ask(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = None
    if not isinstance(data, dict) or not str(data.get("question") or "").strip():
        return web.json_response({"error":"question est obligatoire","version":VERSION}, status=400)
    try:
        req, interpretation = await base.build_investigation_request(str(data["question"]), ha=request.app["ha"])
        payload = await _activity_payload(request.app, req)
        payload["interpretation"] = interpretation
        dev34._journal_io(request.app, "/api/v1/ask", data, payload)
        return web.json_response(payload)
    except (ConversationResolutionError, ValueError, HomeAssistantError) as exc:
        payload = {"status":"confirmed","answer_text":"Je n'ai pas trouvé la cause.","cause_found":False,"diagnostic_error":str(exc),"read_only":True,"version":VERSION}
        dev34._journal_io(request.app, "/api/v1/ask", data, payload)
        return web.json_response(payload)


async def create_app() -> web.Application:
    dev34.VERSION = VERSION
    dev34.memory_ask = activity_ask
    dev34.stable_memory_investigate = activity_investigate
    app = await dev34.create_app()
    reader = ActivityTraceReader(app["ha"], app.get("investigator"))
    reader.set_mcp_client(app.get("mcp"))
    app["activity_reader_dev63"] = reader
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
