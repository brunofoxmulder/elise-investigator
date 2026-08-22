import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
sys.path.insert(0, str(APP))

from conversation import ConversationResolutionError, parse_observed_time, parse_observed_value, resolve_entity


STATES = [
    {
        "entity_id": "light.lampe_salle_de_bain",
        "state": "on",
        "attributes": {"friendly_name": "Lampe salle de bain"},
    },
    {
        "entity_id": "cover.volet_terrasse_2",
        "state": "closed",
        "attributes": {"friendly_name": "volet terrasse"},
    },
    {
        "entity_id": "climate.salon",
        "state": "cool",
        "attributes": {"friendly_name": "Salon"},
    },
    {
        "entity_id": "sensor.salon_temperature",
        "state": "21",
        "attributes": {"friendly_name": "Salon température"},
    },
]


class ConversationTests(unittest.TestCase):
    def test_natural_bathroom_light_question_resolves_entity(self):
        row = resolve_entity(
            "Élise, pourquoi la lampe de la salle de bain vient de s'allumer ?",
            STATES,
        )
        self.assertEqual(row["entity_id"], "light.lampe_salle_de_bain")
        self.assertEqual(parse_observed_value("elle vient de s'allumer"), "on")

    def test_terrace_cover_question_parses_closed(self):
        row = resolve_entity("Pourquoi le volet terrasse s'est fermé ?", STATES)
        self.assertEqual(row["entity_id"], "cover.volet_terrasse_2")
        self.assertEqual(parse_observed_value("Pourquoi le volet terrasse s'est fermé ?"), "closed")

    def test_exact_short_friendly_name_beats_longer_names(self):
        row = resolve_entity("Pourquoi Salon vient de passer en cool ?", STATES)
        self.assertEqual(row["entity_id"], "climate.salon")
        self.assertEqual(parse_observed_value("Pourquoi Salon vient de passer en cool ?"), "cool")

    def test_approximate_clock_time_is_interpreted_today(self):
        tz = ZoneInfo("Europe/Paris")
        now = datetime(2026, 8, 22, 23, 15, tzinfo=tz)
        parsed = parse_observed_time("Pourquoi le volet terrasse s'est fermé vers 22h05 ?", tz, now=now)
        self.assertEqual(parsed, "2026-08-22T22:05:00+02:00")

    def test_hour_without_minutes_is_supported(self):
        tz = ZoneInfo("Europe/Paris")
        now = datetime(2026, 8, 22, 23, 15, tzinfo=tz)
        parsed = parse_observed_time("hier vers 18h", tz, now=now)
        self.assertEqual(parsed, "2026-08-21T18:00:00+02:00")

    def test_explicit_day_month_is_preserved(self):
        tz = ZoneInfo("Europe/Paris")
        now = datetime(2026, 8, 22, 23, 15, tzinfo=tz)
        parsed = parse_observed_time("le 22/08 vers 20h05", tz, now=now)
        self.assertEqual(parsed, "2026-08-22T20:05:00+02:00")

    def test_clock_time_after_midnight_can_mean_previous_evening(self):
        tz = ZoneInfo("Europe/Paris")
        now = datetime(2026, 8, 23, 0, 30, tzinfo=tz)
        parsed = parse_observed_time("Pourquoi la lampe s'est allumée vers 23h15 ?", tz, now=now)
        self.assertEqual(parsed, "2026-08-22T23:15:00+02:00")

    def test_relative_minutes(self):
        tz = ZoneInfo("Europe/Paris")
        now = datetime(2026, 8, 22, 23, 15, tzinfo=tz)
        parsed = parse_observed_time("il y a 10 minutes", tz, now=now)
        self.assertEqual(parsed, "2026-08-22T23:05:00+02:00")

    def test_unknown_entity_is_not_guessed(self):
        with self.assertRaises(ConversationResolutionError):
            resolve_entity("Pourquoi la lampe du grenier vient de s'allumer ?", STATES)


if __name__ == "__main__":
    unittest.main()
