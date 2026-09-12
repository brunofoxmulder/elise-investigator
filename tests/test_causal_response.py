import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_response import answer_from_record


NOW = datetime(2026, 9, 12, 19, 0, 0, tzinfo=timezone.utc)


class TestCausalResponse(unittest.TestCase):
    def test_functional_reason_comes_before_technical_provenance(self):
        item = CausalRecord(
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-09-12T18:58:00+00:00",
            event_kind="positioned",
            after_value=40,
            attribute="current_position",
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon",
            source_name="Gestion volet salon avec soleil et saison",
            reason="la position du soleil et la luminosité imposaient cette position",
            confidence="confirmed",
        )
        answer = answer_from_record(item, now=NOW)
        self.assertIn("positionné à 40 % il y a 2 min", answer)
        self.assertIn("parce que la position du soleil", answer)
        self.assertNotIn("Gestion volet", answer)
        self.assertNotIn("automation.", answer)

    def test_event_age_is_independent_from_causal_delay(self):
        item = CausalRecord(
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-09-12T18:58:00+00:00",
            event_kind="closed",
            after_value="closed",
            origin_type="automation",
            reason="le soleil s'est couché il y a 45 minutes",
            confidence="confirmed",
        )
        answer = answer_from_record(item, now=NOW)
        self.assertEqual(
            answer,
            "Volet salon s'est fermé il y a 2 min parce que le soleil s'est couché il y a 45 minutes.",
        )

    def test_event_age_formats_hours_and_minutes(self):
        item = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-09-12T17:48:00+00:00",
            event_kind="turned_off",
            after_value="off",
            origin_type="user",
            confidence="confirmed",
        )
        self.assertIn("il y a 1 h 12 min", answer_from_record(item, now=NOW))

    def test_event_age_formats_sub_minute(self):
        item = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-09-12T18:59:40+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="user",
            confidence="confirmed",
        )
        self.assertIn("il y a moins d'une minute", answer_from_record(item, now=NOW))

    def test_automation_without_functional_reason_does_not_expose_name(self):
        item = CausalRecord(
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-09-12T18:58:00+00:00",
            event_kind="positioned",
            after_value=40,
            origin_type="automation",
            source_name="Secret implementation name",
            confidence="confirmed",
        )
        answer = answer_from_record(item, now=NOW)
        self.assertIn("raison fonctionnelle", answer)
        self.assertIn("il y a 2 min", answer)
        self.assertNotIn("Secret implementation name", answer)

    def test_user_and_alexa_are_explicit_only_when_stored(self):
        user = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-09-12T18:58:00+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="user",
            confidence="confirmed",
        )
        self.assertIn("commande utilisateur", answer_from_record(user, now=NOW))
        self.assertIn("il y a 2 min", answer_from_record(user, now=NOW))
        alexa = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-09-12T18:58:00+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="alexa",
            confidence="confirmed",
        )
        self.assertIn("commande Alexa", answer_from_record(alexa, now=NOW))
        self.assertIn("il y a 2 min", answer_from_record(alexa, now=NOW))

    def test_unknown_never_guesses(self):
        item = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-09-12T18:58:00+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="unknown",
            confidence="indeterminate",
        )
        answer = answer_from_record(item, now=NOW)
        self.assertIn("cause n'est pas établie", answer)
        self.assertIn("il y a 2 min", answer)


if __name__ == "__main__":
    unittest.main()
