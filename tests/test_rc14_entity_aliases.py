import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'elise_investigator' / 'app'))
from conversation import ConversationResolutionError, resolve_entity, build_investigation_request
from ha_client import HAReadOnlyClient, HomeAssistantError
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.states = [
            {'entity_id': 'cover.volet_terrasse_2', 'attributes': {'friendly_name': 'Terrasse volet'}},
            {'entity_id': 'cover.volet_salon_2', 'attributes': {'friendly_name': 'Volet salon'}},
        ]

    def test_voice_alias_after_name_change(self):
        registry = [{'entity_id': 'cover.volet_terrasse_2', 'aliases': ['Volet terrasse']}]
        found = resolve_entity('Pourquoi le volet terrasse est fermé ?', self.states, registry)
        self.assertEqual(found['entity_id'], 'cover.volet_terrasse_2')

    def test_colliding_alias_never_guesses(self):
        registry = [{'entity_id': 'cover.volet_terrasse_2', 'aliases': ['Volet salon']}]
        with self.assertRaises(ConversationResolutionError):
            resolve_entity('Pourquoi le volet salon est fermé ?', self.states, registry)

    def test_duplicate_aliases_for_same_entity_are_not_ambiguous(self):
        registry = [{'entity_id': 'cover.volet_salon_2', 'aliases': ['Volet salon', 'Volet salon']}]
        self.assertEqual(resolve_entity('Pourquoi volet salon ?', self.states, registry)['entity_id'], 'cover.volet_salon_2')

    def test_unavailable_entity_not_added_from_registry(self):
        registry = [{'entity_id': 'cover.ancien', 'aliases': ['Volet fantôme']}]
        with self.assertRaises(ConversationResolutionError):
            resolve_entity('Pourquoi volet fantôme ?', self.states, registry)

    def test_exact_entity_id_takes_priority(self):
        registry = [{'entity_id': 'cover.volet_terrasse_2', 'aliases': ['Volet salon']}]
        found = resolve_entity('Pourquoi cover.volet_salon_2 est fermé ?', self.states, registry)
        self.assertEqual(found['entity_id'], 'cover.volet_salon_2')


class RegistryFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_websocket_batch_with_1233_entities(self):
        ids = [f'sensor.fixture_{i}' for i in range(1232)] + ['cover.volet_salon_2']
        seen = []
        async def websocket(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({'type': 'auth_required'})
            auth = await ws.receive_json()
            self.assertEqual(auth['type'], 'auth')
            await ws.send_json({'type': 'auth_ok'})
            command = await ws.receive_json()
            seen.append(command)
            result = {entity_id: {'entity_id': entity_id, 'aliases': [None]} for entity_id in ids}
            result['cover.volet_salon_2']['aliases'].append('Volet salon')
            await ws.send_json({'id': command['id'], 'type': 'result', 'success': True, 'result': result})
            await ws.close()
            return ws
        app = web.Application()
        app.router.add_get('/ws', websocket)
        async with TestServer(app) as server, ClientSession() as session:
            client = object.__new__(HAReadOnlyClient)
            client._session = session
            client._token = 'test-token'
            client.WS_URL = str(server.make_url('/ws')).replace('http:', 'ws:', 1)
            entries = await client.get_entity_registry_entries(ids)
        self.assertEqual(seen[0]['type'], 'config/entity_registry/get_entries')
        self.assertEqual(len(entries), 1233)
        states = [{'entity_id': 'cover.volet_salon_2', 'attributes': {'friendly_name': 'Salon volet'}}]
        self.assertEqual(resolve_entity('Pourquoi volet salon ?', states, entries)['entity_id'], 'cover.volet_salon_2')

    async def test_slow_registry_falls_back_with_timeout(self):
        class FakeHA:
            async def get_all_states(self):
                return [{'entity_id': 'cover.volet_salon_2', 'attributes': {'friendly_name': 'Volet salon'}}]
            async def get_entity_registry_entries(self, entity_ids):
                await asyncio.sleep(1)
                raise AssertionError('must be cancelled')
            async def get_config(self):
                return {'time_zone': 'Europe/Paris'}
        with patch('conversation._REGISTRY_TIMEOUT_SECONDS', 0.01), self.assertLogs('conversation', level='WARNING'):
            request, _ = await build_investigation_request('Pourquoi le volet salon est fermé ?', ha=FakeHA())
        self.assertEqual(request.entity_id, 'cover.volet_salon_2')

    async def test_extended_registry_wire_contract(self):
        client = object.__new__(HAReadOnlyClient)
        calls = []
        async def fake_ws(command):
            calls.append(command)
            return {'cover.volet_salon_2': {'entity_id': 'cover.volet_salon_2', 'aliases': [None, 'Volet salon']}, 'cover.unknown': None}
        client._ws = fake_ws
        result = await client.get_entity_registry_entries(['cover.volet_salon_2', 'cover.unknown'])
        self.assertEqual(calls, [{'type': 'config/entity_registry/get_entries', 'entity_ids': ['cover.volet_salon_2', 'cover.unknown']}])
        self.assertEqual(result[0]['aliases'], [None, 'Volet salon'])
        self.assertEqual(len(result), 1)

    async def test_non_dictionary_registry_response_is_failure(self):
        client = object.__new__(HAReadOnlyClient)
        async def fake_ws(command):
            return []
        client._ws = fake_ws
        with self.assertRaises(HomeAssistantError):
            await client.get_entity_registry_entries(['cover.volet_salon_2'])

    async def test_registry_failure_keeps_rc14_behavior(self):
        class FakeHA:
            async def get_all_states(self):
                return [{'entity_id': 'cover.volet_salon_2', 'attributes': {'friendly_name': 'Volet salon'}}]
            async def get_entity_registry_entries(self, entity_ids):
                raise RuntimeError('offline')
            async def get_config(self):
                return {'time_zone': 'Europe/Paris'}
        with self.assertLogs('conversation', level='WARNING'):
            request, _ = await build_investigation_request('Pourquoi le volet salon est fermé ?', ha=FakeHA())
        self.assertEqual(request.entity_id, 'cover.volet_salon_2')

    async def test_request_uses_extended_entries_for_aliases(self):
        class FakeHA:
            async def get_all_states(self):
                return [{'entity_id': 'cover.volet_salon_2', 'attributes': {'friendly_name': 'Salon store'}}]
            async def get_entity_registry_entries(self, entity_ids):
                self.ids = entity_ids
                return [{'entity_id': 'cover.volet_salon_2', 'aliases': [None, 'Volet salon']}]
            async def get_config(self):
                return {'time_zone': 'Europe/Paris'}
        ha = FakeHA()
        request, _ = await build_investigation_request('Pourquoi le volet salon est fermé ?', ha=ha)
        self.assertEqual(ha.ids, ['cover.volet_salon_2'])
        self.assertEqual(request.entity_id, 'cover.volet_salon_2')
