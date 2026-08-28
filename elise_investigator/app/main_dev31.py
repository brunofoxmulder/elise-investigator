from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

import main as base
import main_dev29 as dev29
import main_dev30 as dev30
import main_mcp
from causal_recorder import CausalRecord, CausalRecorder
from conversation import ConversationResolutionError
from ha_client import HomeAssistantError
from models import InvestigationRequest

VERSION = "0.2.0-dev.31"


def _fast_record_payload(record: CausalRecord) -> dict[str, Any]:
    """Return the compact Assist payload without implementation leakage."""
    payload = dev30._record_payload(record)
    payload["version"] = VERSION
    if record.origin_type in {"automation", "script"} and not record.reason:
        label = record.entity_name or record.entity_id
        payload["answer_text"] = (
            f"La raison fonctionnelle précise du dernier changement de {label} "
            "ne peut pas être déterminée."
        )
    return payload


def _journal_only_for_request(app: web.Application, req: InvestigationRequest) -> dict[str, Any]:
    """Resolve from the causal journal only; never block Assist on deep research."""
    recorder: CausalRecorder = app["causal_recorder"]
    record = recorder.find_best(
        req.entity_id,
        observed_time=req.observed_time,
        observed_value=req.observed_value,
        attribute=req.attribute,
    )
    if record is not None:
        return _fast_record_payload(record)

    return {
        "status": "indeterminate",
        "entity_id": req.entity_id,
        "answer_text": "Aucun événement enregistré ne permet encore d'établir la cause.",
        "result_source": "causal_recorder_empty",
        "read_only": True,
        "version": VERSION,
    }


async def stable_investigate(request: web.Request) -> web.Response:
    """Stable Élise Why endpoint: journal-first, bounded and non-blocking."""
    try:
        data = await request.json()
        req = dev30._request_from_payload(data)
        return web.json_response(_journal_only_for_request(request.app, req))
    except ValueError as exc:
        return web.json_response(
            {"error": str(exc), "read_only": True, "version": VERSION}, status=400
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Stable journal lookup failed")
        return web.json_response(
            {"error": f"Erreur interne: {exc}", "read_only": True, "version": VERSION},
            status=500,
        )


async def journal_first_ask(request: web.Request) -> web.Response:
    """Natural-language compatibility endpoint using the same fast journal policy."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Corps JSON invalide"}, status=400)
    if not isinstance(data, dict) or not str(data.get("question") or "").strip():
        return web.json_response({"error": "question est obligatoire"}, status=400)

    try:
        req, interpretation = await base.build_investigation_request(
            str(data["question"]), ha=request.app["ha"]
        )
        payload = _journal_only_for_request(request.app, req)
        payload["interpretation"] = interpretation
        return web.json_response(payload)
    except ConversationResolutionError as exc:
        status = 409 if exc.candidates else 400
        return web.json_response(
            {
                "error": str(exc),
                "candidates": exc.candidates,
                "read_only": True,
                "version": VERSION,
            },
            status=status,
        )
    except ValueError as exc:
        return web.json_response(
            {"error": str(exc), "read_only": True, "version": VERSION}, status=400
        )
    except HomeAssistantError as exc:
        logging.getLogger(__name__).warning("Home Assistant conversational read failed: %s", exc)
        return web.json_response(
            {"error": str(exc), "read_only": True, "version": VERSION}, status=503
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Journal-first conversation failed")
        return web.json_response(
            {"error": f"Erreur interne: {exc}", "read_only": True, "version": VERSION},
            status=500,
        )


def _patch_manual_ui_route(html: str) -> str:
    """Keep the local manual investigation on the dedicated deep endpoint."""
    patched = dev30._patch_manual_ui(html)
    return patched.replace(
        "api('api/v1/investigate')",
        "api('api/v1/investigate/deep')",
        1,
    )


def _patch_dev31_card() -> None:
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(
        "Journal causal · dev.29", "Journal causal · dev.31"
    )
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(
        "<strong>Nouveau en dev.29 :</strong> Investigator mémorise localement les changements significatifs des objets Home Assistant et enrichit leur cause en arrière-plan. Les questions « Pourquoi ? » consultent d'abord ce journal, sans écrire dans Home Assistant.",
        "<strong>Nouveau en dev.31 :</strong> la porte historique <code>/api/v1/investigate</code> reste stable pour Élise Why et consulte uniquement le journal causal préparé en arrière-plan. Elle ne lance plus d'enquête profonde synchrone, afin de ne pas ralentir Assist.",
    )
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(
        "<li><strong>Si le journal ne suffit pas :</strong> l'enquête approfondie peut être lancée en secours selon le réglage ci-dessous.</li>",
        "<li><strong>Assist :</strong> si le journal ne suffit pas, la réponse reste immédiatement indéterminée ; l'enquête approfondie n'est jamais lancée dans le dialogue.</li>",
    )
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(
        "<li><strong>Inchangé :</strong> l'investigation manuelle et la Recherche MCP locale restent disponibles séparément avec leurs garde-fous actuels.</li>",
        "<li><strong>Investigation manuelle :</strong> elle utilise une porte profonde séparée et conserve les preuves structurées complètes. La Recherche MCP locale reste inchangée.</li>",
    )


async def create_app() -> web.Application:
    # Dev.31 deliberately leaves Élise Why untouched. Its historical endpoint
    # /api/v1/investigate becomes the stable, fast contract and the manual UI is
    # moved behind /api/v1/investigate/deep.
    dev29.VERSION = VERSION
    dev30.VERSION = VERSION
    main_mcp.VERSION = VERSION
    dev29.V02Investigator = dev30.EffectiveTransitionInvestigator
    dev29.recorder_first_ask = journal_first_ask
    base.investigate = stable_investigate

    _patch_dev31_card()
    main_mcp.BASE_INDEX_HTML = _patch_manual_ui_route(main_mcp.BASE_INDEX_HTML)

    app = await dev29.create_app()
    base.add_ingress_post(app, "/api/v1/investigate/deep", dev30.manual_investigate)
    # Compatibility alias for future clients; Élise Why dev.18 remains on
    # /api/v1/investigate and does not need any update.
    base.add_ingress_post(app, "/api/v1/why", stable_investigate)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
