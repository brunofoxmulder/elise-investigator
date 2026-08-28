import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_response import answer_from_record


class TestCausalResponse(unittest.TestCase):
    def test_functional_reason_comes_before_technical_provenance(self):
        item = CausalRecord(
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-08-28T10:00:00+00:00",
            event_kind="positioned",
            after_value=40,
            attribute="current_position",
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon",
            source_name="Gestion volet salon avec soleil et saison",
            reason="la position du soleil et la luminosité imposaient cette position",
            confidence="confirmed",
        )
        answer = answer_from_record(item)
        self.assertIn("positionné à 40 %", answer)
        self.assertIn("parce que la position du soleil", answer)
        self.assertNotIn("Gestion volet", answer)
        self.assertNotIn("automation.", answer)

    def test_automation_without_functional_reason_does_not_expose_name(self):
        item = CausalRecord(
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_time="2026-08-28T10:00:00+00:00",
            event_kind="positioned",
            after_value=40,
            origin_type="automation",
            source_name="Secret implementation name",
            confidence="confirmed",
        )
        answer = answer_from_record(item)
        self.assertIn("raison fonctionnelle", answer)
        self.assertNotIn("Secret implementation name", answer)

    def test_user_and_alexa_are_explicit_only_when_stored(self):
        user = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-08-28T10:00:00+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="user",
            confidence="confirmed",
        )
        self.assertIn("commande utilisateur", answer_from_record(user))
        alexa = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-08-28T10:00:00+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="alexa",
            confidence="confirmed",
        )
        self.assertIn("commande Alexa", answer_from_record(alexa))

    def test_unknown_never_guesses(self):
        item = CausalRecord(
            entity_id="light.salon",
            entity_name="Lampe salon",
            event_time="2026-08-28T10:00:00+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="unknown",
            confidence="indeterminate",
        )
        self.assertIn("cause n'est pas établie", answer_from_record(item))


if __name__ == "__main__":
    unittest.main()
