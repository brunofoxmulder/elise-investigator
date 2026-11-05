"""Check RC15 against a disposable Home Assistant started by CI, never production."""

import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "elise_investigator" / "app"))
from conversation import ConversationResolutionError, build_investigation_request, resolve_entity
from ha_client import HAReadOnlyClient, HomeAssistantError


BASE = "http://127.0.0.1:18123"
CLIENT_ID = BASE + "/"
PASSWORD = "local-fixture-not-a-real-account"


async def expect_json(response):
    if response.status >= 400:
        raise AssertionError(f"Fixture HA returned HTTP {response.status}: {(await response.text())[:500]}")
    return await response.json()


async def main():
    async with ClientSession(timeout=ClientTimeout(total=30)) as session:
        for _ in range(120):
            try:
                async with session.get(BASE + "/api/onboarding") as response:
                    if response.status == 200:
                        break
            except (ClientError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(2)
        else:
            raise AssertionError("Disposable Home Assistant did not become ready")

        async with session.post(BASE + "/api/onboarding/users", json={
            "client_id": CLIENT_ID, "name": "Fixture", "username": "fixture",
            "password": PASSWORD, "language": "en",
        }) as response:
            code = (await expect_json(response))["auth_code"]
        async with session.post(BASE + "/auth/token", data={
            "grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID,
        }) as response:
            token = (await expect_json(response))["access_token"]

        client = object.__new__(HAReadOnlyClient)
        client._session = session
        client._token = token
        client._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        client.REST_BASE = BASE + "/api"
        client.WS_URL = "ws://127.0.0.1:18123/api/websocket"
        for _ in range(60):
            entries = await client.list_entity_registry()
            entry = next((x for x in entries if x.get("unique_id") == "rc15_fixture_001"), None)
            if entry:
                try:
                    await client.get_state(entry["entity_id"])
                    break
                except HomeAssistantError:
                    pass
            await asyncio.sleep(1)
        else:
            raise AssertionError("Disposable fixture entity did not load")
        entity_id = entry["entity_id"]

        # This update is deliberately limited to the disposable localhost container.
        async def set_fixture_alias(target):
            async with session.ws_connect(client.WS_URL) as ws:
                assert (await ws.receive_json())["type"] == "auth_required"
                await ws.send_json({"type": "auth", "access_token": token})
                assert (await ws.receive_json())["type"] == "auth_ok"
                await ws.send_json({"id": 1, "type": "config/entity_registry/update",
                                    "entity_id": target, "aliases": ["Volet salon"]})
                result = await ws.receive_json()
                assert result.get("success"), result

        await set_fixture_alias(entity_id)

        states = await client.get_all_states()
        question = "Pourquoi volet salon ?"
        try:
            resolve_entity(question, states)
        except ConversationResolutionError:
            pass
        else:
            raise AssertionError("Fixture must not already match before checking the alias")
        samples = []
        for _ in range(5):
            started = time.monotonic()
            request, _ = await build_investigation_request(question, ha=client)
            samples.append((time.monotonic() - started) * 1000)
            assert request.entity_id == entity_id, (request.entity_id, entity_id)
        for _ in range(30):
            registry = await client.list_entity_registry()
            other = next((x for x in registry if x.get("unique_id") == "rc15_fixture_002"), None)
            if other:
                try:
                    await client.get_state(other["entity_id"])
                    break
                except HomeAssistantError:
                    pass
            await asyncio.sleep(1)
        else:
            raise AssertionError("Second disposable fixture entity did not load")
        await set_fixture_alias(other["entity_id"])
        try:
            await build_investigation_request(question, ha=client)
        except ConversationResolutionError as exc:
            assert {x["entity_id"] for x in exc.candidates} == {entity_id, other["entity_id"]}
        else:
            raise AssertionError("Duplicate alias must be reported as ambiguous")
        print(f"Disposable HA {os.environ['HA_TEST_VERSION']}: alias resolved to fixture entity; "
              f"ambiguous alias refused; median full request {statistics.median(samples):.1f} ms (n=5)")


if __name__ == "__main__":
    asyncio.run(main())
