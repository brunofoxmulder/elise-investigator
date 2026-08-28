from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

import main as base
import main_dev29 as dev29
import main_mcp
from causal_recorder import CausalRecord, CausalRecorder
from causal_response import answer_from_record
from causal_settings import CausalSettings
from conversation import ConversationResolutionError
from ha_client import HomeAssistantError
from human_explanation import build_human_causal_answer
from investigator import _history_time, _same_value, _state_value
from models import InvestigationRequest, InvestigationResult
from v02_investigator import V02Investigator

VERSION = "0.2.0-dev.30"


class EffectiveTransitionInvestigator(V02Investigator):
    """Prefer the latest real value transition over later same-value updates.

    Home Assistant can emit several history rows after a light changes state, for
    example ``off -> on`` followed by attribute refreshes that are still ``on``.
    A causal question must anchor on the effective transition, not on the last
    technical update carrying the same state.
    """

    def _choose_event(
        self,
        history: list[dict[str, Any]],
        *,
        observed_time,
        observed_value: Any,
        attribute: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if not history:
            return None, None

        indexed: list[tuple[int, dict[str, Any], Any]] = []
        for index, row in enumerate(history):
            when = _history_time(row, attribute=attribute)
            if when is not None:
                indexed.append((index, row, when))
        if not indexed:
            return (history[-2] if len(history) > 1 else None), history[-1]

        matching = [
            item
            for item in indexed
            if _same_value(_state_value(item[1], attribute), observed_value)
        ]
        base_pool = matching or indexed

        transitions: list[tuple[int, dict[str, Any], Any]] = []
        for item in base_pool:
            index, row, _ = item
            if index <= 0:
                continue
            previous = history[index - 1]
            if not _same_value(
                _state_value(previous, attribute),
                _state_value(row, attribute),
            ):
                transitions.append(item)

        # A proven transition wins over any later same-value refresh. If History
        # contains no transition in the window, keep the conservative legacy
        # fallback so boundary/current-state policies can still apply.
        pool = transitions or base_pool
        if observed_time:
            chosen = min(pool, key=lambda item: abs((item[2] - observed_time).total_seconds()))
        else:
            chosen = max(pool, key=lambda item: item[2])
        index = chosen[0]
        previous = history[index - 1] if index > 0 else None
        return previous, chosen[1]


def _request_from_payload(data: Any) -> InvestigationRequest:
    if not isinstance(data, dict) or not data.get("entity_id"):
        raise ValueError("entity_id est obligatoire")
    return InvestigationRequest(
        entity_id=str(data["entity_id"]),
        observed_time=(str(data["observed_time"]) if data.get("observed_time") else None),
        observed_value=data.get("observed_value"),
        attribute=(str(data["attribute"]) if data.get("attribute") else None),
        user_declaration=(str(data["user_declaration"]) if data.get("user_declaration") else None),
        window_minutes=(int(data["window_minutes"]) if data.get("window_minutes") is not None else None),
        detail_mode=(str(data.get("detail_mode") or "simple")),
    )


def _functional_answer(result: InvestigationResult) -> str:
    cause_type = str(result.cause.get("type") or "unknown")
    if cause_type in {"automation", "script"}:
        human = build_human_causal_answer(result)
        if human:
            return human
        label = result.entity_name or result.entity_id
        return f"La raison fonctionnelle précise du dernier changement de {label} ne peut pas être déterminée."
    return result.answer_text


def _record_payload(record: CausalRecord) -> dict[str, Any]:
    compact = record.llm_payload()
    payload: dict[str, Any] = {
        "status": record.confidence,
        "entity_id": record.entity_id,
        "entity_name": record.entity_name,
        "event_type": record.event_kind,
        "event_time": record.event_time,
        "answer_text": answer_from_record(record),
        "result_source": "causal_recorder",
        "read_only": True,
        "version": VERSION,
    }
    for key in ("reason", "source", "value", "attribute"):
        if key in compact:
            payload[key] = compact[key]
    return payload


def _result_payload(result: InvestigationResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": result.status,
        "entity_id": result.entity_id,
        "entity_name": result.entity_name,
        "event_type": result.event_type,
        "event_time": result.event_time,
        "answer_text": _functional_answer(result),
        "result_source": "deep_investigation_fallback",
        "read_only": True,
        "version": VERSION,
    }
    explanation = result.meta.get("explanation") if isinstance(result.meta, dict) else None
    human_cause = explanation.get("human_cause") if isinstance(explanation, dict) else None
    if isinstance(human_cause, dict) and human_cause.get("proven") is True:
        reason = str(human_cause.get("text") or "").strip()
        if reason:
            payload["reason"] = reason
    if result.cause.get("type") == "user":
        payload["source"] = "utilisateur"
    if result.observed.get("after") is not None:
        payload["value"] = result.observed.get("after")
    if result.observed.get("attribute"):
        payload["attribute"] = result.observed.get("attribute")
    return payload


async def _why_for_request(app: web.Application, req: InvestigationRequest) -> dict[str, Any]:
    recorder: CausalRecorder = app["causal_recorder"]
    record = recorder.find_best(
        req.entity_id,
        observed_time=req.observed_time,
        observed_value=req.observed_value,
        attribute=req.attribute,
    )
    if record is not None:
        return _record_payload(record)

    settings: CausalSettings = app["causal_settings"]
    if not settings.deep_fallback:
        return {
            "status": "indeterminate",
            "entity_id": req.entity_id,
            "answer_text": "Aucun événement enregistré ne permet d'expliquer cet état récent.",
            "result_source": "causal_recorder_empty",
            "read_only": True,
            "version": VERSION,
        }

    result = await app["causal_investigator"].investigate(req)
    return _result_payload(result)


async def structured_why(request: web.Request) -> web.Response:
    """Structured journal-first endpoint used by Élise Why / Assist."""
    try:
        data = await request.json()
        req = _request_from_payload(data)
        return web.json_response(await _why_for_request(request.app, req))
    except ValueError as exc:
        return web.json_response({"error": str(exc), "read_only": True, "version": VERSION}, status=400)
    except HomeAssistantError as exc:
        logging.getLogger(__name__).warning("Home Assistant causal read failed: %s", exc)
        return web.json_response({"error": str(exc), "read_only": True, "version": VERSION}, status=503)
    except Exception as exc:
        logging.getLogger(__name__).exception("Structured causal request failed")
        return web.json_response({"error": f"Erreur interne: {exc}", "read_only": True}, status=500)


async def recorder_first_ask(request: web.Request) -> web.Response:
    """Natural-language compatibility endpoint sharing the same journal-first core."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Corps JSON invalide"}, status=400)
    if not isinstance(data, dict) or not str(data.get("question") or "").strip():
        return web.json_response({"error": "question est obligatoire"}, status=400)

    try:
        req, interpretation = await base.build_investigation_request(
            str(data["question"]),
            ha=request.app["ha"],
        )
        payload = await _why_for_request(request.app, req)
        payload["interpretation"] = interpretation
        return web.json_response(payload)
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


async def manual_investigate(request: web.Request) -> web.Response:
    """Keep the manual deep-search UI, but use the human causal presentation layer."""
    try:
        data = await request.json()
        req = _request_from_payload(data)
        result = await request.app["causal_investigator"].investigate(req)
        result.answer_text = _functional_answer(result)
        return web.json_response(result.to_dict())
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except HomeAssistantError as exc:
        logging.getLogger(__name__).warning("Home Assistant manual read failed: %s", exc)
        return web.json_response({"error": str(exc)}, status=503)
    except Exception as exc:
        logging.getLogger(__name__).exception("Manual investigation failed")
        return web.json_response({"error": f"Erreur interne: {exc}"}, status=500)


def _patch_manual_ui(html: str) -> str:
    old = "statusEl.textContent='Cause '+d.status;"
    new = (
        "const statusLabels={confirmed:'confirmée',probable:'probable',indeterminate:'indéterminée'};"
        "statusEl.textContent='Cause '+(statusLabels[d.status]||d.status);"
    )
    return html.replace(old, new, 1)


def _patch_dev30_card() -> None:
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace("Journal causal · dev.29", "Journal causal · dev.30")
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(
        "<strong>Nouveau en dev.29 :</strong> Investigator mémorise localement les changements significatifs des objets Home Assistant et enrichit leur cause en arrière-plan. Les questions « Pourquoi ? » consultent d'abord ce journal, sans écrire dans Home Assistant.",
        "<strong>Nouveau en dev.30 :</strong> Assist / Élise Why utilisent désormais directement le journal causal prioritaire. La recherche manuelle reste une enquête approfondie séparée, toujours en lecture seule.",
    )
    dev29._CAUSAL_CARD = dev29._CAUSAL_CARD.replace(
        "<strong>Ce que dev.29 change dans l'usage :</strong>",
        "<strong>Ce que dev.30 garantit dans l'usage :</strong>",
    )


async def create_app() -> web.Application:
    # Reuse the validated dev.29 journal/runtime and only replace the routing and
    # event-selection policy required by the terrain finding of 28/08/2026.
    dev29.VERSION = VERSION
    dev29.V02Investigator = EffectiveTransitionInvestigator
    dev29.recorder_first_ask = recorder_first_ask
    base.investigate = manual_investigate
    _patch_dev30_card()
    main_mcp.BASE_INDEX_HTML = _patch_manual_ui(main_mcp.BASE_INDEX_HTML)

    app = await dev29.create_app()
    base.add_ingress_post(app, "/api/v1/why", structured_why)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
