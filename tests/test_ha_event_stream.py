import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ha_client import HomeAssistantError
from ha_event_stream import HAStateChangeStream


class FakeWebSocket:
    def __init__(self, *, ack_success=True, events=None):
        self.sent = []
        self._json = [
            {"type": "auth_required"},
            {"type": "auth_ok"},
            {
                "id": 1,
                "type": "result",
                "success": ack_success,
                "error": None if ack_success else {"message": "denied"},
            },
        ]
        self._messages = [
            SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(item))
            for item in (events or [])
        ]

    async def receive_json(self, timeout=None):
        return self._json.pop(0)

    async def send_json(self, payload):
        self.sent.append(payload)

    def __aiter__(self):
        self._iter = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeContext:
    def __init__(self, ws):
        self.ws = ws

    async def __aenter__(self):
        return self.ws

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, ws):
        self.ws = ws
        self.calls = []

    def ws_connect(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeContext(self.ws)


class TestHAStateChangeStream(unittest.IsolatedAsyncioTestCase):
    async def test_only_subscribe_events_state_changed_is_sent_after_auth(self):
        event = {
            "id": 1,
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {"entity_id": "light.entree"},
            },
        }
        ws = FakeWebSocket(events=[event])
        session = FakeSession(ws)
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            stream = HAStateChangeStream(session)
            received = [item async for item in stream.events()]

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["event_type"], "state_changed")
        self.assertEqual(
            ws.sent,
            [
                {"type": "auth", "access_token": "test-token"},
                {"id": 1, "type": "subscribe_events", "event_type": "state_changed"},
            ],
        )
        command_types = {item.get("type") for item in ws.sent[1:]}
        self.assertEqual(command_types, {"subscribe_events"})

    async def test_non_state_changed_payloads_are_ignored(self):
        wrong = {
            "id": 1,
            "type": "event",
            "event": {"event_type": "call_service", "data": {}},
        }
        ws = FakeWebSocket(events=[wrong])
        session = FakeSession(ws)
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            stream = HAStateChangeStream(session)
            received = [item async for item in stream.events()]
        self.assertEqual(received, [])

    async def test_subscription_refusal_fails_closed(self):
        ws = FakeWebSocket(ack_success=False)
        session = FakeSession(ws)
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            stream = HAStateChangeStream(session)
            with self.assertRaises(HomeAssistantError):
                _ = [item async for item in stream.events()]


if __name__ == "__main__":
    unittest.main()
