import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from causal_events import changes_from_state_event


def event(entity_id, old_state, new_state, *, old_attrs=None, new_attrs=None, context=None):
    return {
        "event_type": "state_changed",
        "time_fired": "2026-08-28T10:38:53+00:00",
        "data": {
            "entity_id": entity_id,
            "old_state": {
                "state": old_state,
                "attributes": old_attrs or {},
                "context": context or {},
            },
            "new_state": {
                "state": new_state,
                "attributes": new_attrs or {},
                "context": context or {},
            },
        },
    }


class TestCausalEvents(unittest.TestCase):
    def test_light_off_is_normalized_for_any_entity_id(self):
        changes = changes_from_state_event(
            event(
                "light.entree",
                "on",
                "off",
                old_attrs={"friendly_name": "Lampe entrée"},
                new_attrs={"friendly_name": "Lampe entrée"},
                context={"id": "ctx", "parent_id": "parent", "user_id": None},
            )
        )
        self.assertEqual(len(changes), 1)
        change = changes[0]
        self.assertEqual(change.event_kind, "turned_off")
        self.assertEqual(change.before_value, "on")
        self.assertEqual(change.after_value, "off")
        self.assertEqual(change.entity_name, "Lampe entrée")
        self.assertEqual(change.context_id, "ctx")
        self.assertEqual(change.parent_id, "parent")

    def test_cover_position_is_recorded_even_when_primary_state_does_not_change(self):
        changes = changes_from_state_event(
            event(
                "cover.volet_salon_2",
                "open",
                "open",
                old_attrs={"friendly_name": "Volet salon", "current_position": 70},
                new_attrs={"friendly_name": "Volet salon", "current_position": 40},
            )
        )
        self.assertEqual(len(changes), 1)
        change = changes[0]
        self.assertEqual(change.attribute, "current_position")
        self.assertEqual(change.event_kind, "positioned")
        self.assertEqual(change.before_value, 70)
        self.assertEqual(change.after_value, 40)

    def test_cover_state_and_position_can_be_emitted_together(self):
        changes = changes_from_state_event(
            event(
                "cover.volet_test",
                "open",
                "closing",
                old_attrs={"current_position": 100},
                new_attrs={"current_position": 95},
            )
        )
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0].event_kind, "closing")
        self.assertEqual(changes[1].event_kind, "positioned")

    def test_irrelevant_attribute_only_update_is_ignored(self):
        changes = changes_from_state_event(
            event(
                "sensor.temperature_test",
                "20.0",
                "20.0",
                old_attrs={"friendly_name": "Temp", "unit_of_measurement": "°C", "foo": 1},
                new_attrs={"friendly_name": "Temp", "unit_of_measurement": "°C", "foo": 2},
            )
        )
        self.assertEqual(changes, [])

    def test_sensor_primary_change_is_kept(self):
        changes = changes_from_state_event(
            event(
                "sensor.temperature_test",
                "20.0",
                "20.4",
                old_attrs={"friendly_name": "Temp"},
                new_attrs={"friendly_name": "Temp"},
            )
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].event_kind, "state_changed")
        self.assertEqual(changes[0].after_value, "20.4")

    def test_entity_creation_or_removal_is_not_presented_as_causal_change(self):
        created = {
            "event_type": "state_changed",
            "data": {
                "entity_id": "light.new",
                "old_state": None,
                "new_state": {"state": "off", "attributes": {}},
            },
        }
        self.assertEqual(changes_from_state_event(created), [])


if __name__ == "__main__":
    unittest.main()
