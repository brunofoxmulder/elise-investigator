from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientTimeout, web

from homeassistant.components import cloud, persistent_notification, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CLOUDHOOK_URL,
    CONF_INVESTIGATOR_SLUG,
    CONF_INVESTIGATOR_TOKEN,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EXPECTED_SKILL_ID,
    INVESTIGATOR_ASK_PATH,
    INVESTIGATOR_PORT,
    MAX_QUESTION_LENGTH,
    NOTIFICATION_ID,
    REQUEST_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def _investigator_url(slug: str) -> str:
    """Build the internal Supervisor-network URL for Investigator."""
    hostname = slug.replace("_", "-")
    return f"http://{hostname}:{INVESTIGATOR_PORT}{INVESTIGATOR_ASK_PATH}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Maison Élise Bridge."""
    webhook_id = str(entry.data[CONF_WEBHOOK_ID])

    if not cloud.async_active_subscription(hass):
        raise ConfigEntryNotReady(
            "Maison Élise Bridge requires an active Home Assistant Cloud subscription"
        )

    try:
        cloudhook_url = await cloud.async_get_or_create_cloudhook(hass, webhook_id)
    except (cloud.CloudNotAvailable, cloud.CloudNotConnected) as err:
        raise ConfigEntryNotReady("Home Assistant Cloud is not ready") from err

    if entry.data.get(CONF_CLOUDHOOK_URL) != cloudhook_url:
        data = dict(entry.data)
        data[CONF_CLOUDHOOK_URL] = cloudhook_url
        hass.config_entries.async_update_entry(entry, data=data)

    async def handle_webhook(
        hass: HomeAssistant, received_webhook_id: str, request: web.Request
    ) -> web.Response:
        """Relay one read-only causal question to Élise Investigator."""
        if received_webhook_id != webhook_id:
            return web.json_response(
                {"ok": False, "error": "invalid_webhook"}, status=403
            )

        try:
            payload = await request.json()
        except Exception:
            return web.json_response(
                {"ok": False, "error": "invalid_json"}, status=400
            )

        if not isinstance(payload, dict):
            return web.json_response(
                {"ok": False, "error": "invalid_json"}, status=400
            )

        if payload.get("skill_id") != EXPECTED_SKILL_ID:
            return web.json_response(
                {"ok": False, "error": "invalid_skill"}, status=403
            )

        question = str(payload.get("question") or "").strip()
        if not question:
            return web.json_response(
                {"ok": False, "error": "question_required"}, status=400
            )
        if len(question) > MAX_QUESTION_LENGTH:
            return web.json_response(
                {"ok": False, "error": "question_too_long"}, status=400
            )

        session = async_get_clientsession(hass)
        try:
            async with session.post(
                _investigator_url(str(entry.data[CONF_INVESTIGATOR_SLUG])),
                headers={
                    "Authorization": f"Bearer {entry.data[CONF_INVESTIGATOR_TOKEN]}"
                },
                json={"question": question},
                timeout=ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as response:
                if response.status in (401, 403):
                    return web.json_response(
                        {"ok": False, "error": "investigator_auth"}, status=502
                    )
                if response.status != 200:
                    return web.json_response(
                        {"ok": False, "error": "investigator_unavailable"},
                        status=502,
                    )
                try:
                    result: Any = await response.json(content_type=None)
                except Exception:
                    return web.json_response(
                        {"ok": False, "error": "invalid_investigator_response"},
                        status=502,
                    )
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "investigator_timeout"}, status=504
            )
        except ClientError:
            return web.json_response(
                {"ok": False, "error": "investigator_unavailable"}, status=502
            )

        if not isinstance(result, dict):
            return web.json_response(
                {"ok": False, "error": "invalid_investigator_response"}, status=502
            )

        answer_text = str(result.get("answer_text") or "").strip()
        if not answer_text:
            return web.json_response(
                {"ok": False, "error": "answer_missing"}, status=502
            )

        return web.json_response(
            {
                "ok": True,
                "answer_text": answer_text,
                "status": result.get("status"),
                "read_only": True,
            }
        )

    try:
        webhook.async_register(
            hass,
            DOMAIN,
            "Maison Élise",
            webhook_id,
            handle_webhook,
            allowed_methods=("POST",),
        )
    except ValueError as err:
        raise ConfigEntryNotReady(
            "Maison Élise webhook is already registered"
        ) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_WEBHOOK_ID: webhook_id,
        CONF_CLOUDHOOK_URL: cloudhook_url,
    }

    persistent_notification.async_create(
        hass,
        (
            "La passerelle vocale Maison Élise est prête.\n\n"
            "Copie cette URL dans le code Alexa-hosted quand Élise te le demandera :\n\n"
            f"`{cloudhook_url}`\n\n"
            "Cette URL est un secret : ne la publie pas."
        ),
        title="Maison Élise Bridge",
        notification_id=NOTIFICATION_ID,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Maison Élise Bridge without changing its cloudhook URL."""
    webhook_id = str(entry.data[CONF_WEBHOOK_ID])
    webhook.async_unregister(hass, webhook_id)

    entries = hass.data.get(DOMAIN)
    if isinstance(entries, dict):
        entries.pop(entry.entry_id, None)
        if not entries:
            hass.data.pop(DOMAIN, None)

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the cloudhook only when the integration is removed permanently."""
    webhook_id = str(entry.data[CONF_WEBHOOK_ID])
    try:
        await cloud.async_delete_cloudhook(hass, webhook_id)
    except (cloud.CloudNotAvailable, cloud.CloudNotConnected):
        _LOGGER.debug(
            "Cloudhook deletion deferred because Home Assistant Cloud is unavailable"
        )
