from __future__ import annotations

from scenario_engine import VirtualHAScenario


LAMP = "light.hue_tento_color_panel_1_3"
AUTOMATION = "automation.ambiance_du_soir_test"
AUTOMATION_ID = "ambiance-soir-test"


def brightness_transition_scenario() -> VirtualHAScenario:
    """Synthetic/anonymised replay of the 2026-09-02 field symptom.

    The important causal shape is preserved:
      1. an automation starts a brightness transition with confirmed context;
      2. later brightness samples belong to the same physical transition but
         carry no fresh causal context;
      3. Investigator must be evaluated at several instants, not only once.

    Values/timestamps are test data. No live Home Assistant connection exists.
    """

    return VirtualHAScenario(
        initial_states=[
            {
                "entity_id": LAMP,
                "state": "on",
                "attributes": {
                    "friendly_name": "Lampe salon test",
                    "brightness": 158,
                },
                "last_changed": "2026-09-02T17:50:00+00:00",
                "last_updated": "2026-09-02T17:50:00+00:00",
            },
            {
                "entity_id": AUTOMATION,
                "state": "on",
                "attributes": {
                    "friendly_name": "Ambiance du soir test",
                    "id": AUTOMATION_ID,
                },
                "last_changed": "2026-09-02T06:00:00+00:00",
                "last_updated": "2026-09-02T17:59:13+00:00",
            },
        ],
        events=[
            {
                "time": "2026-09-02T17:59:14.253639+00:00",
                "entity_id": LAMP,
                "attributes": {"brightness": 0},
                "message": "brightness changed to 0",
                "context_entity_id": AUTOMATION,
                "context_entity_id_name": "Ambiance du soir test",
                "context_id": "ctx-transition-1",
            },
            {
                "time": "2026-09-02T18:01:30+00:00",
                "entity_id": LAMP,
                "attributes": {"brightness": 16},
                "message": "brightness changed to 16",
                "context_id": "ctx-transition-1",
                "logbook": True,
            },
            {
                "time": "2026-09-02T18:02:29.126368+00:00",
                "entity_id": LAMP,
                "attributes": {"brightness": 17},
                "message": "brightness changed to 17",
                "context_id": "ctx-transition-1",
                "logbook": True,
            },
        ],
        automation_configs={
            AUTOMATION_ID: {
                "id": AUTOMATION_ID,
                "alias": "Ambiance du soir test",
                "trigger": [
                    {
                        "platform": "sun",
                        "event": "sunset",
                        "offset": "-00:30:00",
                    }
                ],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": LAMP},
                        "data": {"transition": 1800},
                    }
                ],
            }
        },
        trace_summaries={
            ("automation", AUTOMATION_ID): [
                {
                    "run_id": "run-transition-1",
                    "timestamp": {"start": "2026-09-02T17:59:14+00:00"},
                }
            ]
        },
        trace_details={
            ("automation", AUTOMATION_ID, "run-transition-1"): {
                "trigger": {
                    "platform": "sun",
                    "event": "sunset",
                    "offset": "-00:30:00",
                },
                "action": {
                    "domain": "light",
                    "service": "turn_on",
                    "target": {"entity_id": LAMP},
                    "service_data": {"transition": 1800},
                },
            }
        },
    )


def cover_episode_scenario() -> VirtualHAScenario:
    """Minimal non-regression cover episode kept beside light scenarios."""

    cover = "cover.volet_test"
    automation = "automation.volet_test"
    automation_id = "volet-test"
    return VirtualHAScenario(
        initial_states=[
            {
                "entity_id": cover,
                "state": "open",
                "attributes": {"friendly_name": "Volet test", "current_position": 100},
                "last_changed": "2026-09-02T15:00:00+00:00",
                "last_updated": "2026-09-02T15:00:00+00:00",
            },
            {
                "entity_id": automation,
                "state": "on",
                "attributes": {"friendly_name": "Volet test auto", "id": automation_id},
                "last_changed": "2026-09-02T06:00:00+00:00",
                "last_updated": "2026-09-02T16:00:00+00:00",
            },
        ],
        events=[
            {
                "time": "2026-09-02T16:00:01+00:00",
                "entity_id": cover,
                "state": "closing",
                "attributes": {"current_position": 100},
                "message": "closing",
                "context_entity_id": automation,
                "context_entity_id_name": "Volet test auto",
                "context_id": "ctx-cover-1",
            },
            {
                "time": "2026-09-02T16:00:15+00:00",
                "entity_id": cover,
                "state": "closed",
                "attributes": {"current_position": 0},
                "message": "closed",
                "context_id": "ctx-cover-1",
            },
        ],
        automation_configs={
            automation_id: {
                "id": automation_id,
                "alias": "Volet test auto",
                "trigger": [{"platform": "time", "at": "18:00:00"}],
                "action": [
                    {"service": "cover.close_cover", "target": {"entity_id": cover}}
                ],
            }
        },
        trace_summaries={
            ("automation", automation_id): [
                {"run_id": "run-cover-1", "timestamp": {"start": "2026-09-02T16:00:00+00:00"}}
            ]
        },
        trace_details={
            ("automation", automation_id, "run-cover-1"): {
                "trigger": {"platform": "time", "at": "18:00:00"},
                "action": {
                    "domain": "cover",
                    "service": "close_cover",
                    "target": {"entity_id": cover},
                    "service_data": {},
                },
            }
        },
    )
