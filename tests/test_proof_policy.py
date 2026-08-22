import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
sys.path.insert(0, str(APP))

from models import Evidence, InvestigationRequest, InvestigationResult
from proof_policy import enforce_result_policy, executed_trace_actions


class ProofPolicyTests(unittest.TestCase):
    def test_config_reference_is_not_execution_proof(self):
        detail = {
            "config": {
                "action": {
                    "domain": "cover",
                    "service": "close_cover",
                    "target": {"entity_id": "cover.volet_salon_2"},
                }
            },
            "trace": {},
        }
        self.assertEqual(executed_trace_actions(detail, "cover.volet_salon_2"), [])

    def test_executed_trace_action_is_detected(self):
        detail = {
            "config": {},
            "trace": {
                "action/0": [
                    {
                        "result": {
                            "params": {
                                "domain": "cover",
                                "service": "close_cover",
                                "target": {"entity_id": "cover.volet_salon_2"},
                            }
                        }
                    }
                ]
            },
        }
        actions = executed_trace_actions(detail, "cover.volet_salon_2")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["service"], "cover.close_cover")

    def test_multiple_traced_sources_are_not_a_confirmed_unique_cause(self):
        result = InvestigationResult(
            status="confirmed",
            entity_id="cover.volet_salon_2",
            entity_name="volet salon",
            event_type="state_change",
            event_time="2026-08-22T19:36:19+00:00",
            observed={"before": "closing", "after": "closed", "description": "volet salon est passée de closing à closed."},
            cause={
                "type": "multiple",
                "entity_id": None,
                "name": "Plusieurs exécutions prouvées",
                "system_confirmed": True,
                "exclusive": False,
                "sources": ["automation.a", "automation.b"],
            },
            evidence=[
                Evidence(kind="trace", summary="Trace proche", source="automation.a", strength="direct"),
                Evidence(kind="trace", summary="Trace proche", source="automation.b", strength="direct"),
            ],
            limits=["Plusieurs causes peuvent être vraies simultanément ; l'exclusivité n'est pas démontrée."],
            meta={"rules": {}},
        )

        enforce_result_policy(result)

        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.cause["type"], "multiple_candidates")
        self.assertFalse(result.cause["system_confirmed"])
        self.assertTrue(all(item.strength == "supporting" for item in result.evidence))
        self.assertTrue(result.meta["rules"]["multiple_traces_do_not_prove_unique_cause"])

    def test_history_boundary_state_is_not_treated_as_none_to_state_event(self):
        result = InvestigationResult(
            status="indeterminate",
            entity_id="light.lampe_tele",
            entity_name="lampe télé",
            event_type="state_change",
            event_time="2026-08-22T20:20:18.258506+00:00",
            observed={
                "before": None,
                "after": "on",
                "attribute": None,
                "description": "lampe télé est passée de None à on.",
            },
            cause={"type": "unknown", "entity_id": None, "name": None, "system_confirmed": False},
            chain=[],
            evidence=[
                Evidence(
                    kind="history",
                    summary="Événement enregistré par le Recorder: None → on",
                    timestamp="2026-08-22T20:20:18.258506+00:00",
                    strength="direct",
                    raw={"previous": None, "event": {"state": "on"}},
                )
            ],
            candidates=[{"entity_id": "automation.example"}],
            limits=["La recherche inverse trouve des candidats, mais aucune exécution précise n'est prouvée."],
            meta={
                "window": {
                    "start": "2026-08-22T20:20:18.258506+00:00",
                    "end": "2026-08-22T20:50:18.258506+00:00",
                },
                "rules": {},
            },
        )
        request = InvestigationRequest(entity_id="light.lampe_tele")

        enforce_result_policy(result, request=request)

        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.event_type, "window_boundary_state")
        self.assertIsNone(result.event_time)
        self.assertEqual(result.cause["type"], "unknown")
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.evidence[0].strength, "supporting")
        self.assertIn("début de la période", result.observed["description"])
        self.assertTrue(result.meta["rules"]["window_boundary_is_not_event"])

    def test_explicit_observed_time_prevents_boundary_downgrade(self):
        result = InvestigationResult(
            status="indeterminate",
            entity_id="light.lampe_tele",
            entity_name="lampe télé",
            event_type="state_change",
            event_time="2026-08-22T20:20:18.258506+00:00",
            observed={"before": None, "after": "on", "description": "lampe télé est passée de None à on."},
            cause={"type": "unknown", "entity_id": None, "name": None, "system_confirmed": False},
            evidence=[
                Evidence(
                    kind="history",
                    summary="Événement enregistré par le Recorder: None → on",
                    strength="direct",
                    raw={"previous": None, "event": {"state": "on"}},
                )
            ],
            meta={
                "window": {
                    "start": "2026-08-22T20:20:18.258506+00:00",
                    "end": "2026-08-22T20:50:18.258506+00:00",
                },
                "rules": {},
            },
        )
        request = InvestigationRequest(
            entity_id="light.lampe_tele",
            observed_time="2026-08-22T20:50:18.258506+00:00",
        )

        enforce_result_policy(result, request=request)

        self.assertEqual(result.event_type, "state_change")
        self.assertEqual(result.event_time, "2026-08-22T20:20:18.258506+00:00")


if __name__ == "__main__":
    unittest.main()
