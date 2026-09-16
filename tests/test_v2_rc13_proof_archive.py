"""Synthetic exact-event proofs: never connects to Home Assistant."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "elise_investigator/app"))
from causal_recorder import CausalRecord, CausalRecorder
from proof_archive_rc13 import POLICY, PROOF_KEY, ProofArchive

NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


def record():
    fact = {"entity_id": "cover.test", "state": "open", "when": (NOW - timedelta(hours=1)).isoformat(),
            "context_id": "effect-one"}
    carrier = {**fact, "when": (NOW - timedelta(hours=1, seconds=15)).isoformat(),
               "state": "opening", "context_id": "command-one"}
    proof = {"policy": POLICY, "run_id": "run-one", "source": "automation.test",
             "execution_time": carrier["when"],
             "command": {"path": "action/4", "service": "set_cover_position", "data": {"position": 100}},
             "cause": {"origin": "automation_trigger", "detail": {"platform": "time_pattern"}}}
    return CausalRecord(entity_id="cover.test", event_time=fact["when"], event_kind="opened", after_value="open",
        origin_type="automation", source_entity_id="automation.test", confidence="confirmed",
        reason="le calcul a demandé 100 %", reason_code="ha_logbook+exact_trace", trace_run_id="run-one",
        trigger={"ha_activity_fact": fact, "ha_activity_attribution": carrier, PROOF_KEY: proof})


def unresolved(item):
    item = deepcopy(item)
    item.reason = item.reason_code = item.trace_run_id = None
    item.trigger.pop(PROOF_KEY, None)
    return item


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "memory.sqlite3"
        self.recorder = CausalRecorder(self.path)
        self.now = NOW
        self.archive = ProofArchive(self.recorder, clock=lambda: self.now)

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def test_reopen_database_retains_exact_cause_and_structured_proof(self):
        original = record()
        self.assertTrue(self.archive.save(original))
        self.recorder.close()
        self.recorder = CausalRecorder(self.path)
        self.archive = ProofArchive(self.recorder, clock=lambda: self.now)
        candidate = unresolved(original)
        self.assertTrue(self.archive.restore(candidate))
        self.assertEqual(candidate.reason, original.reason)
        self.assertEqual(candidate.trigger[PROOF_KEY], original.trigger[PROOF_KEY])
        self.assertEqual(candidate.reason_code, "ha_logbook+retained_exact_trace")

    def test_new_event_same_entity_same_final_position_never_reuses_old_cause(self):
        original = record(); self.archive.save(original)
        candidate = unresolved(original)
        candidate.event_time = (NOW - timedelta(minutes=10)).isoformat()
        candidate.trigger["ha_activity_fact"]["when"] = candidate.event_time
        self.assertFalse(self.archive.restore(candidate))
        self.assertIsNone(candidate.reason)

    def test_identity_guards_each_source_effect_context_and_attribute(self):
        original = record(); self.archive.save(original)
        changes = [lambda r: setattr(r, "entity_id", "cover.other"),
                   lambda r: setattr(r, "source_entity_id", "automation.other"),
                   lambda r: setattr(r, "after_value", "closed"),
                   lambda r: setattr(r, "attribute", "current_position"),
                   lambda r: r.trigger["ha_activity_fact"].update(context_id="new-context"),
                   lambda r: r.trigger["ha_activity_attribution"].update(context_id="new-command"),
                   lambda r: r.trigger.pop("ha_activity_fact")]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                candidate = unresolved(original); change(candidate)
                self.assertFalse(self.archive.restore(candidate))

    def test_expiry_uses_event_time_and_does_not_slide_on_queries(self):
        original = record(); self.archive.save(original)
        self.now = NOW + timedelta(hours=10)
        self.assertTrue(self.archive.restore(unresolved(original)))
        self.now += timedelta(hours=2)
        self.assertFalse(self.archive.restore(unresolved(original)))
        self.assertFalse(self.archive.save(original))
        self.archive.prune()
        self.assertEqual(self.archive.db.execute("SELECT count(*) FROM exact_proofs_rc13").fetchone()[0], 0)

    def test_current_retention_setting_applies_without_restarting(self):
        original = record(); self.archive.save(original)
        self.recorder.retention_hours = 1
        self.now += timedelta(seconds=1)
        self.assertFalse(self.archive.restore(unresolved(original)))

    def test_identical_saves_are_idempotent_and_missing_reason_cannot_overwrite(self):
        original = record()
        self.assertTrue(self.archive.save(original)); self.assertTrue(self.archive.save(original))
        self.assertFalse(self.archive.save(unresolved(original)))
        self.assertEqual(self.archive.db.execute("SELECT count(*) FROM exact_proofs_rc13").fetchone()[0], 1)
        self.assertTrue(self.archive.restore(unresolved(original)))

    def test_conflicting_proofs_for_same_event_disable_reuse(self):
        original = record(); self.archive.save(original)
        other = deepcopy(original); other.reason = "une autre raison"; other.trigger[PROOF_KEY]["cause"]["origin"] = "delay"
        self.assertFalse(self.archive.save(other))
        self.assertFalse(self.archive.restore(unresolved(original)))

    def test_current_reason_is_never_replaced(self):
        original = record(); self.archive.save(original)
        candidate = deepcopy(original); candidate.reason = "preuve fraîche"
        self.assertFalse(self.archive.restore(candidate))
        self.assertEqual(candidate.reason, "preuve fraîche")

    def test_unknown_probable_provider_text_or_missing_trace_is_never_saved(self):
        for field, value in [("confidence", "probable"), ("reason_code", "ha_2026_9_activity_native"),
                             ("trace_run_id", None), ("origin_type", "unknown")]:
            with self.subTest(field=field):
                item = record(); setattr(item, field, value)
                self.assertFalse(self.archive.save(item))

    def test_corrupted_payload_is_not_returned(self):
        original = record(); self.archive.save(original)
        self.archive.db.execute("UPDATE exact_proofs_rc13 SET payload='{}'")
        self.assertFalse(self.archive.restore(unresolved(original)))

    def test_proof_size_and_archive_count_are_bounded(self):
        original = record(); original.trigger[PROOF_KEY]["cause"]["oversized"] = "x" * 40000
        self.assertFalse(self.archive.save(original))
        self.archive.MAX_ROWS = 2
        for minute in range(3):
            item = record(); item.event_time = (NOW - timedelta(minutes=minute)).isoformat()
            item.trigger["ha_activity_fact"]["when"] = item.event_time
            self.assertTrue(self.archive.save(item))
        self.assertEqual(self.archive.db.execute("SELECT count(*) FROM exact_proofs_rc13").fetchone()[0], 2)

    def test_display_name_changes_do_not_change_event_identity(self):
        original = record(); self.archive.save(original)
        candidate = unresolved(original); candidate.entity_name = "New name"
        candidate.trigger["ha_activity_fact"]["name"] = "New name"
        self.assertTrue(self.archive.restore(candidate))

    def test_timezone_equivalence_keeps_same_event(self):
        original = record(); self.archive.save(original)
        candidate = unresolved(original)
        candidate.event_time = "2026-09-16T13:00:00+02:00"
        candidate.trigger["ha_activity_fact"]["when"] = candidate.event_time
        self.assertTrue(self.archive.restore(candidate))

    def test_stale_trace_from_same_source_is_not_saved(self):
        item = record()
        item.trigger[PROOF_KEY]["execution_time"] = (NOW - timedelta(hours=2)).isoformat()
        self.assertFalse(self.archive.save(item))

    def test_contradictory_trace_context_is_not_saved(self):
        item = record(); item.trigger[PROOF_KEY]["trace_context"] = {"id": "another-run"}
        self.assertFalse(self.archive.save(item))

    def test_matching_trace_parent_context_is_accepted(self):
        item = record(); item.trigger[PROOF_KEY]["trace_context"] = {"id": "child", "parent_id": "command-one"}
        self.assertTrue(self.archive.save(item))
