from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web

import main as base
import main_dev29 as dev29
import main_dev30 as dev30
import main_mcp
from causal_recorder import CausalRecord, CausalRecorder
from causal_recorder_dev33 import RelevantCausalRecorder
from causal_settings import CausalSettings, CausalSettingsStore
from conversation import ConversationResolutionError
from cover_episode_investigator import CoverEpisodeInvestigator
from ha_client import HomeAssistantError
from ha_memory_stream_dev34 import HAMemoryEventStream
from memory_response_dev34 import answer_from_memory, cause_found
from memory_worker_dev34 import ConsciousMemoryWorker
from models import InvestigationRequest
from request_journal_dev34 import RequestJournal

VERSION = "0.2.0-dev.34"
REQUEST_JOURNAL_FILE = Path("/data") / "investigator_requests.sqlite3"
_LOGGER = logging.getLogger(__name__)

_MEMORY_CARD = r'''
<div id="causal_console" class="card">
  <p class="section-title">Mémoire consciente · dev.34</p>
  <p class="section-sub">Investigator mémorise localement ce qui s'est réellement passé sur les objets utiles. Une question retrouve directement le dernier changement pertinent ; aucune enquête profonde n'est lancée dans le chemin conversationnel.</p>

  <p id="causal_status" class="small">Chargement de la mémoire…</p>
  <p id="causal_mode" class="small"></p>

  <label for="causal_retention">Durée de mémoire</label>
  <input id="causal_retention" type="number" min="1" max="72" step="1" value="12">
  <p class="picker-help">De 1 à 72 heures · 12 heures par défaut.</p>
  <button id="causal_save" type="button">Enregistrer la durée</button>
  <p id="causal_save_note" class="small"></p>

  <details style="margin-top:16px">
    <summary>Journal des demandes — entrée / sortie</summary>
    <p class="small">Diagnostic uniquement : ce qui arrive à Investigator et ce qu'il renvoie. Ce journal local suit la même durée de conservation que la mémoire.</p>
    <button id="io_refresh" type="button" class="diag-copy">Actualiser</button>
    <pre id="io_log">Chargement…</pre>
  </details>
</div>
'''

_MEMORY_SCRIPT = r'''
const causalStatus=document.getElementById('causal_status'),causalMode=document.getElementById('causal_mode'),causalRetention=document.getElementById('causal_retention'),causalSave=document.getElementById('causal_save'),causalSaveNote=document.getElementById('causal_save_note');
const ioRefresh=document.getElementById('io_refresh'),ioLog=document.getElementById('io_log');
async function loadCausalStatus(){
 try{
  const r=await fetch(api('api/v1/causal/status'));const d=await r.json();if(!r.ok)throw new Error(d.error||'Mémoire indisponible');
  causalRetention.value=d.settings?.retention_hours??12;
  const w=d.worker||{};
  causalStatus.textContent=(w.running?'Mémoire active':'Mémoire arrêtée')+' · '+(d.record_count||0)+' souvenir(s) conservé(s) · '+(w.records_written||0)+' changement(s) utile(s) capturé(s) depuis le démarrage';
  causalMode.textContent='Chemin normal : événements HA → mémoire locale → réponse · aucune file d’enrichissement · Home Assistant : '+(d.read_only_home_assistant===true?'lecture seule':'état de sécurité non confirmé');
 }catch(err){causalStatus.textContent='Mémoire indisponible : '+err.message;causalMode.textContent='';}
}
async function loadIoLog(){
 try{
  const r=await fetch(api('api/v1/io-log?limit=20'));const d=await r.json();if(!r.ok)throw new Error(d.error||'Journal indisponible');
  const rows=Array.isArray(d.entries)?d.entries:[];
  ioLog.textContent=rows.length?rows.map(x=>'['+x.time+'] '+x.route+'\nENTRÉE '+JSON.stringify(x.request,null,2)+'\nSORTIE '+JSON.stringify(x.response,null,2)).join('\n\n'):'Aucune demande enregistrée.';
 }catch(err){ioLog.textContent='Journal indisponible : '+err.message;}
}
causalSave.addEventListener('click',async()=>{
 causalSave.disabled=true;causalSaveNote.textContent='Enregistrement…';
 try{
  const body={retention_hours:Number(causalRetention.value)};
  const r=await fetch(api('api/v1/causal/settings'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.error||'Réglage impossible');
  causalSaveNote.textContent='Durée enregistrée localement.';await loadCausalStatus();
 }catch(err){causalSaveNote.textContent='Erreur : '+err.message;}
 finally{causalSave.disabled=false;}
});
ioRefresh.addEventListener('click',loadIoLog);
loadCausalStatus();loadIoLog();setInterval(loadCausalStatus,15000);
'''


def _patch_ui(html: str) -> str:
    patched = html.replace(
        '<p class="section-title">Investigation</p>',
        '<p class="section-title">Interroger la mémoire</p>',
        1,
    )
    patched = patched.replace(
        "Choisis l'objet. Les autres champs sont facultatifs et servent seulement à préciser l'événement.",
        "Choisis l'objet. Investigator retrouve le dernier changement pertinent mémorisé ; les autres champs restent facultatifs.",
        1,
    )
    patched = patched.replace(">Enquêter</button>", ">Interroger</button>", 1)
    patched = patched.replace("btn.textContent='Investigation…'", "btn.textContent='Recherche…'", 1)
    patched = patched.replace(
        "statusEl.textContent='Cause '+d.status;statusEl.className='status '+d.status;",
        "statusEl.textContent='RÉSULTAT';statusEl.className='status confirmed';",
        1,
    )
    return patched


def _memory_payload(app: web.Application, req: InvestigationRequest) -> dict[str, Any]:
    recorder: CausalRecorder = app["causal_recorder"]
    record = recorder.find_best(
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


def _fallback(entity_id: str, *, diagnostic_error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "confirmed",
        "entity_id": entity_id,
        "answer_text": "Je n'ai pas trouvé la cause.",
        "cause_found": False,
        "result_source": "conscious_memory_fallback",
        "read_only": True,
        "version": VERSION,
    }
    if diagnostic_error:
        payload["diagnostic_error"] = diagnostic_error
    return payload


def _journal_io(app: web.Application, route: str, incoming: Any, outgoing: Any) -> None:
    journal = app.get("request_journal")
    if isinstance(journal, RequestJournal):
        try:
            journal.append(route, incoming, outgoing)
        except Exception as exc:
            _LOGGER.warning("Request journal write failed: %s", exc)
    _LOGGER.info("Investigator %s input=%s output=%s", route, incoming, outgoing)


async def stable_memory_investigate(request: web.Request) -> web.Response:
    """Stable Why endpoint: always return the dev.34 memory contract when possible."""
    data: Any = None
    entity_id = ""
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("Corps JSON invalide")
        entity_id = str(data.get("entity_id") or "").strip()
        req = dev30._request_from_payload(data)
        payload = _memory_payload(request.app, req)
        _journal_io(request.app, "/api/v1/investigate", data, payload)
        return web.json_response(payload)
    except Exception as exc:
        if entity_id:
            payload = _fallback(entity_id, diagnostic_error=str(exc))
            _journal_io(request.app, "/api/v1/investigate", data, payload)
            return web.json_response(payload)
        payload = {
            "error": str(exc),
            "answer_text": "Je n'ai pas trouvé la cause.",
            "read_only": True,
            "version": VERSION,
        }
        _journal_io(request.app, "/api/v1/investigate", data, payload)
        return web.json_response(payload, status=400)


async def memory_ask(request: web.Request) -> web.Response:
    """Natural-language compatibility endpoint backed by the same memory."""
    try:
        data = await request.json()
    except Exception:
        data = None
    if not isinstance(data, dict) or not str(data.get("question") or "").strip():
        payload = {
            "error": "question est obligatoire",
            "answer_text": "Je n'ai pas trouvé la cause.",
            "read_only": True,
            "version": VERSION,
        }
        _journal_io(request.app, "/api/v1/ask", data, payload)
        return web.json_response(payload, status=400)

    try:
        req, interpretation = await base.build_investigation_request(
            str(data["question"]), ha=request.app["ha"]
        )
        payload = _memory_payload(request.app, req)
        payload["interpretation"] = interpretation
        _journal_io(request.app, "/api/v1/ask", data, payload)
        return web.json_response(payload)
    except (ConversationResolutionError, ValueError, HomeAssistantError) as exc:
        payload = {
            "status": "confirmed",
            "answer_text": "Je n'ai pas trouvé la cause.",
            "cause_found": False,
            "diagnostic_error": str(exc),
            "read_only": True,
            "version": VERSION,
        }
        _journal_io(request.app, "/api/v1/ask", data, payload)
        return web.json_response(payload)
    except Exception as exc:
        _LOGGER.exception("Conscious-memory conversation failed")
        payload = {
            "status": "confirmed",
            "answer_text": "Je n'ai pas trouvé la cause.",
            "cause_found": False,
            "diagnostic_error": str(exc),
            "read_only": True,
            "version": VERSION,
        }
        _journal_io(request.app, "/api/v1/ask", data, payload)
        return web.json_response(payload)


async def memory_status(request: web.Request) -> web.Response:
    recorder: CausalRecorder = request.app["causal_recorder"]
    worker: ConsciousMemoryWorker = request.app["causal_worker"]
    settings: CausalSettings = request.app["causal_settings"]
    return web.json_response(
        {
            "version": VERSION,
            "settings": {"retention_hours": settings.retention_hours},
            "record_count": recorder.count(),
            "worker": worker.status(),
            "read_only_home_assistant": True,
        }
    )


async def memory_settings(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("Corps JSON invalide")
        raw_retention = int(data.get("retention_hours", 12))
        if not 1 <= raw_retention <= 72:
            raise ValueError("retention_hours doit être compris entre 1 et 72")
        settings = CausalSettings(retention_hours=raw_retention, deep_fallback=False)
        store: CausalSettingsStore = request.app["causal_settings_store"]
        settings = store.save(settings)
        request.app["causal_settings"] = settings
        request.app["causal_recorder"].set_retention_hours(raw_retention)
        journal = request.app.get("request_journal")
        if isinstance(journal, RequestJournal):
            journal.set_retention_hours(raw_retention)
        return web.json_response(
            {"settings": {"retention_hours": raw_retention}, "read_only_home_assistant": True}
        )
    except (TypeError, ValueError) as exc:
        return web.json_response({"error": str(exc), "read_only_home_assistant": True}, status=400)


async def io_log(request: web.Request) -> web.Response:
    try:
        limit = int(request.query.get("limit", "20"))
    except ValueError:
        limit = 20
    journal: RequestJournal = request.app["request_journal"]
    return web.json_response(
        {"version": VERSION, "entries": journal.recent(limit=limit), "read_only": True}
    )


async def _close_request_journal(app: web.Application) -> None:
    journal = app.get("request_journal")
    if isinstance(journal, RequestJournal):
        journal.close()


async def create_app() -> web.Application:
    # Dev.34 keeps the proven dev.33 deep engine available only on its explicit
    # diagnostic endpoint, but replaces the normal recorder/enrichment pipeline
    # with an event-memory path that performs no reverse investigation.
    dev29.VERSION = VERSION
    dev30.VERSION = VERSION
    main_mcp.VERSION = VERSION
    dev29.CausalRecorder = RelevantCausalRecorder
    dev29.CausalRecorderWorker = ConsciousMemoryWorker
    dev29.HAStateChangeStream = HAMemoryEventStream
    dev29.V02Investigator = CoverEpisodeInvestigator
    dev29.recorder_first_ask = memory_ask
    dev29.causal_status = memory_status
    dev29.causal_settings = memory_settings
    base.ask = memory_ask
    base.investigate = stable_memory_investigate

    dev29._CAUSAL_CARD = _MEMORY_CARD
    dev29._CAUSAL_SCRIPT = _MEMORY_SCRIPT
    main_mcp.BASE_INDEX_HTML = _patch_ui(main_mcp.BASE_INDEX_HTML)

    app = await dev29.create_app()

    settings: CausalSettings = app["causal_settings"]
    request_journal = RequestJournal(
        REQUEST_JOURNAL_FILE, retention_hours=settings.retention_hours
    )
    app["request_journal"] = request_journal

    # Deep/manual investigation remains available for development diagnostics,
    # but neither Assist nor the normal IHM invokes it in dev.34.
    base.add_ingress_post(app, "/api/v1/investigate/deep", dev30.manual_investigate)
    base.add_ingress_post(app, "/api/v1/why", stable_memory_investigate)
    base.add_ingress_get(app, "/api/v1/io-log", io_log)
    app.on_cleanup.append(_close_request_journal)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
