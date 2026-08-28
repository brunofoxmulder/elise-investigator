from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web

import main as base
import main_mcp
from causal_enricher import CausalEnricher
from causal_recorder import CausalRecorder
from causal_response import answer_from_record
from causal_settings import CausalSettings, CausalSettingsStore
from causal_worker import CausalRecorderWorker
from conversation import ConversationResolutionError
from ha_client import HomeAssistantError
from ha_event_stream import HAStateChangeStream
from mcp_client_inprocess import InProcessMCPReadOnlyClient
from v02_investigator import V02Investigator

VERSION = "0.2.0-dev.29"
DATA_DIR = Path("/data")
JOURNAL_FILE = DATA_DIR / "causal_journal.sqlite3"
SETTINGS_FILE = DATA_DIR / "causal_settings.json"


_CAUSAL_CARD = r'''
<div id="causal_console" class="card">
  <p class="section-title">Journal causal · dev.29</p>
  <p class="section-sub">Écoute locale des changements Home Assistant. Les événements sont stockés dans Investigator puis enrichis en arrière-plan, sans aucune écriture dans Home Assistant.</p>
  <p id="causal_status" class="small">Chargement du journal…</p>
  <div class="grid">
    <div>
      <label for="causal_retention">Durée du journal (heures)</label>
      <input id="causal_retention" type="number" min="1" max="72" step="1" value="12">
    </div>
    <div>
      <label for="causal_fallback">Enquête approfondie de secours</label>
      <label style="font-weight:500;margin-top:10px"><input id="causal_fallback" type="checkbox" style="width:auto;margin-right:8px">Si aucun événement n'est enregistré</label>
    </div>
  </div>
  <button id="causal_save" type="button">Enregistrer les réglages</button>
  <p id="causal_save_note" class="small"></p>
</div>
'''

_CAUSAL_SCRIPT = r'''
const causalStatus=document.getElementById('causal_status'),causalRetention=document.getElementById('causal_retention'),causalFallback=document.getElementById('causal_fallback'),causalSave=document.getElementById('causal_save'),causalSaveNote=document.getElementById('causal_save_note');
async function loadCausalStatus(){
 try{
  const r=await fetch(api('api/v1/causal/status'));const d=await r.json();if(!r.ok)throw new Error(d.error||'Journal indisponible');
  causalRetention.value=d.settings?.retention_hours??12;causalFallback.checked=d.settings?.deep_fallback!==false;
  const w=d.worker||{};causalStatus.textContent=(w.running?'Journal actif':'Journal arrêté')+' · '+(d.record_count||0)+' événement(s) conservé(s) · file '+(w.queue_depth||0)+'/'+(w.queue_capacity||0)+' · enrichis '+(w.records_enriched||0)+(w.enrichment_failures?' · échecs '+w.enrichment_failures:'');
 }catch(err){causalStatus.textContent='Journal causal indisponible : '+err.message;}
}
causalSave.addEventListener('click',async()=>{
 causalSave.disabled=true;causalSaveNote.textContent='Enregistrement…';
 try{
  const body={retention_hours:Number(causalRetention.value),deep_fallback:!!causalFallback.checked};
  const r=await fetch(api('api/v1/causal/settings'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.error||'Réglage impossible');
  causalSaveNote.textContent='Réglages enregistrés localement dans Investigator.';await loadCausalStatus();
 }catch(err){causalSaveNote.textContent='Erreur : '+err.message;}
 finally{causalSave.disabled=false;}
});
loadCausalStatus();setInterval(loadCausalStatus,15000);
'''


def _install_ui_extension() -> None:
    if "id=\"causal_console\"" not in main_mcp._MCP_CARD:
        main_mcp._MCP_CARD += "\n" + _CAUSAL_CARD
    if "loadCausalStatus" not in main_mcp._MCP_SCRIPT:
        main_mcp._MCP_SCRIPT = main_mcp._MCP_SCRIPT.replace("0.2.0-dev.28", VERSION) + "\n" + _CAUSAL_SCRIPT


async def recorder_first_ask(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Corps JSON invalide"}, status=400)
    if not isinstance(data, dict) or not str(data.get("question") or "").strip():
        return web.json_response({"error": "question est obligatoire"}, status=400)

    try:
        investigation_request, interpretation = await base.build_investigation_request(
            str(data["question"]),
            ha=request.app["ha"],
        )
        recorder: CausalRecorder = request.app["causal_recorder"]
        record = recorder.find_best(
            investigation_request.entity_id,
            observed_time=investigation_request.observed_time,
            observed_value=investigation_request.observed_value,
            attribute=investigation_request.attribute,
        )
        if record is not None:
            return web.json_response(
                {
                    "status": record.confidence,
                    "answer_text": answer_from_record(record),
                    "interpretation": interpretation,
                    "source": "causal_recorder",
                    "journal": record.llm_payload(),
                    "read_only": True,
                    "version": VERSION,
                }
            )

        settings: CausalSettings = request.app["causal_settings"]
        if not settings.deep_fallback:
            label = interpretation.get("entity_name") or investigation_request.entity_id
            return web.json_response(
                {
                    "status": "indeterminate",
                    "answer_text": (
                        f"Aucun changement récent de {label} n'est encore enregistré dans le journal causal. "
                        "L'enquête approfondie de secours est désactivée."
                    ),
                    "interpretation": interpretation,
                    "source": "causal_recorder_empty",
                    "journal": None,
                    "read_only": True,
                    "version": VERSION,
                }
            )

        result = await request.app["investigator"].investigate(investigation_request)
        return web.json_response(
            {
                "status": result.status,
                "answer_text": result.answer_text,
                "interpretation": interpretation,
                "source": "deep_investigation_fallback",
                "investigation": result.to_dict(),
                "read_only": True,
                "version": VERSION,
            }
        )
    except ConversationResolutionError as exc:
        status = 409 if exc.candidates else 400
        return web.json_response(
            {"error": str(exc), "candidates": exc.candidates, "read_only": True, "version": VERSION},
            status=status,
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc), "read_only": True, "version": VERSION}, status=400)
    except HomeAssistantError as exc:
        logging.getLogger(__name__).warning("Home Assistant conversational read failed: %s", exc)
        return web.json_response({"error": str(exc), "read_only": True, "version": VERSION}, status=503)
    except Exception as exc:
        logging.getLogger(__name__).exception("Recorder-first conversation failed")
        return web.json_response({"error": f"Erreur interne: {exc}", "read_only": True}, status=500)


async def causal_status(request: web.Request) -> web.Response:
    recorder: CausalRecorder = request.app["causal_recorder"]
    worker: CausalRecorderWorker = request.app["causal_worker"]
    settings: CausalSettings = request.app["causal_settings"]
    return web.json_response(
        {
            "version": VERSION,
            "settings": settings.to_dict(),
            "record_count": recorder.count(),
            "worker": worker.status(),
            "read_only_home_assistant": True,
        }
    )


async def causal_settings(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Corps JSON invalide"}, status=400)
    if not isinstance(data, dict):
        return web.json_response({"error": "Corps JSON invalide"}, status=400)
    try:
        settings = CausalSettings.from_dict(data)
        # Invalid explicit values are rejected rather than silently normalized.
        raw_retention = int(data.get("retention_hours", settings.retention_hours))
        if not 1 <= raw_retention <= 72:
            raise ValueError("retention_hours doit être compris entre 1 et 72")
        if "deep_fallback" in data and not isinstance(data["deep_fallback"], bool):
            raise ValueError("deep_fallback doit être un booléen")
        settings.retention_hours = raw_retention
        store: CausalSettingsStore = request.app["causal_settings_store"]
        settings = store.save(settings)
        request.app["causal_settings"] = settings
        request.app["causal_recorder"].set_retention_hours(settings.retention_hours)
        return web.json_response({"settings": settings.to_dict(), "read_only_home_assistant": True})
    except (TypeError, ValueError) as exc:
        return web.json_response({"error": str(exc), "read_only_home_assistant": True}, status=400)


async def _start_causal(app: web.Application) -> None:
    await app["causal_worker"].start()


async def _stop_causal(app: web.Application) -> None:
    await app["causal_worker"].stop()


async def _close_causal(app: web.Application) -> None:
    app["causal_recorder"].close()


async def create_app() -> web.Application:
    _install_ui_extension()
    main_mcp.VERSION = VERSION
    main_mcp.MCPReadOnlyClient = InProcessMCPReadOnlyClient

    # The route is registered by base.create_app; swap only its handler before
    # construction so the manual /investigate endpoint remains untouched.
    base.ask = recorder_first_ask
    app = await main_mcp.create_app()

    settings_store = CausalSettingsStore(SETTINGS_FILE)
    settings = settings_store.load()
    recorder = CausalRecorder(JOURNAL_FILE, retention_hours=settings.retention_hours)

    # Keep the terrain-proven dev.28 manual engine untouched. The journal uses a
    # separate dev.16-derived deterministic engine so long traces, action-local
    # waits/branches and cover movement episodes are available during enrichment.
    options = base.load_options()
    causal_investigator = V02Investigator(
        app["ha"],
        default_window_minutes=int(options.get("default_window_minutes", 30)),
        max_reverse_candidates=int(options.get("max_reverse_candidates", 25)),
    )
    enricher = CausalEnricher(causal_investigator, app["ha"])
    worker = CausalRecorderWorker(
        HAStateChangeStream(app["session"]),
        recorder,
        enricher,
    )

    app["causal_settings_store"] = settings_store
    app["causal_settings"] = settings
    app["causal_recorder"] = recorder
    app["causal_investigator"] = causal_investigator
    app["causal_worker"] = worker

    base.add_ingress_get(app, "/api/v1/causal/status", causal_status)
    base.add_ingress_post(app, "/api/v1/causal/settings", causal_settings)
    app.on_startup.append(_start_causal)
    app.on_shutdown.append(_stop_causal)
    app.on_cleanup.append(_close_causal)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
