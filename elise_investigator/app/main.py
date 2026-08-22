from __future__ import annotations

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from aiohttp import web, ClientSession, ClientTimeout

from ha_client import HAReadOnlyClient, HomeAssistantError
from investigator import Investigator
from models import InvestigationRequest
from ui import INDEX_HTML

VERSION = "0.1.0-beta.3"
DATA_DIR = Path("/data")
TOKEN_FILE = DATA_DIR / "api_token"
OPTIONS_FILE = DATA_DIR / "options.json"


def load_options() -> dict[str, Any]:
    defaults = {"log_level": "info", "default_window_minutes": 30, "max_reverse_candidates": 25}
    try:
        data = json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update(data)
    except Exception:
        pass
    return defaults


def load_or_create_api_token() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    except FileNotFoundError:
        pass
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return token


def is_ingress_request(request: web.Request) -> bool:
    if os.environ.get("ELISE_DEV_MODE") == "1":
        return True
    # Supervisor Ingress is expected to originate from 172.30.32.2.
    return request.remote == "172.30.32.2"


@web.middleware
async def access_guard(request: web.Request, handler):
    if request.path in {"/health", "/api/v1/health"}:
        return await handler(request)
    if is_ingress_request(request):
        return await handler(request)
    # Direct access is API-only and bearer protected.
    if request.path.startswith("/api/") or request.path == "/openapi.json":
        expected = request.app["api_token"]
        auth = request.headers.get("Authorization", "")
        if secrets.compare_digest(auth, f"Bearer {expected}"):
            return await handler(request)
        return web.json_response({"error": "unauthorized"}, status=401)
    return web.Response(text="Accès direct à l'interface refusé. Utilisez Home Assistant Ingress.", status=403)


def ai_tool_descriptor() -> dict[str, Any]:
    return {
        "name": "investigate_home_assistant_event",
        "description": (
            "Explique en lecture seule pourquoi une entité Home Assistant a changé. "
            "Utiliser entity_id; ajouter l'heure, la valeur ou l'attribut quand l'utilisateur les connaît. "
            "Le résultat sépare preuve système, candidats et déclaration utilisateur."
        ),
        "input_schema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {"type": "string"},
                "observed_time": {"type": "string"},
                "observed_value": {},
                "attribute": {"type": "string"},
                "user_declaration": {"type": "string"},
                "window_minutes": {"type": "integer", "minimum": 5, "maximum": 180},
            },
        },
        "endpoint": "/api/v1/investigate",
        "method": "POST",
        "read_only": True,
    }


def openapi_schema() -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Élise Investigator API", "version": VERSION, "description": "Read-only causal investigation for Home Assistant."},
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": {
                "InvestigationRequest": {
                    "type": "object",
                    "required": ["entity_id"],
                    "properties": {
                        "entity_id": {"type": "string", "example": "light.lampe_entree"},
                        "observed_time": {"type": "string", "description": "ISO-8601 or local datetime value"},
                        "observed_value": {"description": "Observed state or attribute value"},
                        "attribute": {"type": "string", "nullable": True, "example": "temperature"},
                        "user_declaration": {"type": "string", "nullable": True},
                        "window_minutes": {"type": "integer", "minimum": 5, "maximum": 180},
                    },
                }
            },
        },
        "paths": {
            "/api/v1/investigate": {
                "post": {
                    "summary": "Investigate why a Home Assistant entity changed",
                    "operationId": "investigate_entity",
                    "security": [{"bearerAuth": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/InvestigationRequest"}}}},
                    "responses": {"200": {"description": "Structured causal investigation"}, "400": {"description": "Invalid request"}, "503": {"description": "Home Assistant unavailable"}},
                }
            },
            "/api/v1/health": {"get": {"summary": "Health check", "responses": {"200": {"description": "Healthy"}}}},
        },
    }


async def index(request: web.Request) -> web.Response:
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def health(request: web.Request) -> web.Response:
    try:
        state = await request.app["ha"].get_config()
        return web.json_response({"ok": True, "version": VERSION, "home_assistant": state.get("version"), "read_only": True})
    except Exception as exc:
        return web.json_response({"ok": False, "version": VERSION, "error": str(exc), "read_only": True}, status=503)


async def connection(request: web.Request) -> web.Response:
    if not is_ingress_request(request):
        return web.json_response({"error": "available_through_ingress_only"}, status=403)
    return web.json_response({
        "api_token": request.app["api_token"],
        "endpoint": "/api/v1/investigate",
        "openapi": "/openapi.json",
        "port": 8099,
        "port_enabled_by_default": False,
    })


async def investigate(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Corps JSON invalide"}, status=400)
    if not isinstance(data, dict) or not data.get("entity_id"):
        return web.json_response({"error": "entity_id est obligatoire"}, status=400)
    try:
        req = InvestigationRequest(
            entity_id=str(data["entity_id"]),
            observed_time=data.get("observed_time"),
            observed_value=data.get("observed_value"),
            attribute=(str(data["attribute"]) if data.get("attribute") else None),
            user_declaration=(str(data["user_declaration"]) if data.get("user_declaration") else None),
            window_minutes=(int(data["window_minutes"]) if data.get("window_minutes") is not None else None),
        )
        result = await request.app["investigator"].investigate(req)
        return web.json_response(result.to_dict())
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except HomeAssistantError as exc:
        logging.getLogger(__name__).warning("Home Assistant read failed: %s", exc)
        return web.json_response({"error": str(exc)}, status=503)
    except Exception as exc:
        logging.getLogger(__name__).exception("Investigation failed")
        return web.json_response({"error": f"Erreur interne: {exc}"}, status=500)


async def ai_tool(request: web.Request) -> web.Response:
    return web.json_response(ai_tool_descriptor())


async def openapi(request: web.Request) -> web.Response:
    return web.json_response(openapi_schema())


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


async def create_app() -> web.Application:
    options = load_options()
    level = str(options.get("log_level", "info")).upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger(__name__).info("Starting Élise Investigator %s in strict read-only mode", VERSION)

    session = ClientSession(timeout=ClientTimeout(total=25))
    ha = HAReadOnlyClient(session)
    investigator_engine = Investigator(
        ha,
        default_window_minutes=int(options.get("default_window_minutes", 30)),
        max_reverse_candidates=int(options.get("max_reverse_candidates", 25)),
    )
    app = web.Application(middlewares=[access_guard], client_max_size=1024 * 1024)
    app["session"] = session
    app["ha"] = ha
    app["investigator"] = investigator_engine
    app["api_token"] = load_or_create_api_token()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/v1/health", health)
    app.router.add_get("/api/v1/connection", connection)
    app.router.add_get("/api/v1/ai-tool", ai_tool)
    app.router.add_post("/api/v1/investigate", investigate)
    app.router.add_get("/openapi.json", openapi)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
