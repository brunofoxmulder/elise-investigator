import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'elise_investigator' / 'app'))
from conversation import ConversationResolutionError, resolve_entity, build_investigation_request


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
    async def test_registry_failure_keeps_rc14_behavior(self):
        class FakeHA:
            async def get_all_states(self):
                return [{'entity_id': 'cover.volet_salon_2', 'attributes': {'friendly_name': 'Volet salon'}}]
            async def list_entity_registry(self):
                raise RuntimeError('offline')
            async def get_config(self):
                return {'time_zone': 'Europe/Paris'}
        with self.assertLogs('conversation', level='WARNING'):
            request, _ = await build_investigation_request('Pourquoi le volet salon est fermé ?', ha=FakeHA())
        self.assertEqual(request.entity_id, 'cover.volet_salon_2')
