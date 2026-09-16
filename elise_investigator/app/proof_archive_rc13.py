"""Bounded, exact-event proof archive in Investigator's existing SQLite file.

The HA Logbook still selects the event. This archive cannot select an older event,
infer a cause, or extend a proof's lifetime when somebody asks the same question.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from activity_reader_dev60 import _context_ids, _dt

PROOF_KEY = "retained_proof_rc13"
POLICY = "rc12-exact-trace-v1"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def event_identity(record):
    """Stable HA facts only: no friendly names, current values, or nearest-time match."""
    trigger = record.trigger or {}
    fact = trigger.get("ha_activity_fact")
    carrier = trigger.get("ha_activity_attribution")
    if not isinstance(fact, dict) or not isinstance(carrier, dict):
        return None
    when = _dt(fact.get("when"))
    carrier_time = _dt(carrier.get("when"))
    if (when is None or carrier_time is None or when != record.normalized_time()
            or fact.get("entity_id") != record.entity_id
            or fact.get("state") != record.after_value
            or record.origin_type not in {"automation", "script"}
            or not record.source_entity_id):
        return None
    return {
        "policy": POLICY, "entity_id": record.entity_id,
        "event_time": when.isoformat(), "event_kind": record.event_kind,
        "attribute": record.attribute, "after": record.after_value,
        "origin": record.origin_type, "source": record.source_entity_id,
        "fact_contexts": sorted(_context_ids(fact)),
        "carrier_time": carrier_time.isoformat(), "carrier_state": carrier.get("state"),
        "carrier_contexts": sorted(_context_ids(carrier)),
    }


class ProofArchive:
    MAX_ROWS = 2048
    MAX_BYTES = 32768

    def __init__(self, recorder, *, clock=None):
        self.recorder = recorder
        # Reuse the existing connection/lifecycle; never open or mount HA's database.
        self.db = recorder._db
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.db.execute("""CREATE TABLE IF NOT EXISTS exact_proofs_rc13 (
            event_key TEXT PRIMARY KEY, event_time TEXT NOT NULL,
            payload TEXT NOT NULL, digest TEXT NOT NULL, conflict INTEGER NOT NULL DEFAULT 0
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_proofs_rc13_time ON exact_proofs_rc13(event_time)")
        self.db.commit()
        self.prune()

    def prune(self):
        cutoff = self.clock() - timedelta(hours=self.recorder.retention_hours)
        with self.db:
            self.db.execute("DELETE FROM exact_proofs_rc13 WHERE event_time < ?", (cutoff.isoformat(),))
            self.db.execute("""DELETE FROM exact_proofs_rc13 WHERE event_key IN
                (SELECT event_key FROM exact_proofs_rc13 ORDER BY event_time DESC, event_key
                 LIMIT -1 OFFSET ?)""", (self.MAX_ROWS,))

    def _key(self, record):
        identity = event_identity(record)
        if identity is None:
            return None, None
        now = self.clock()
        if not now - timedelta(hours=self.recorder.retention_hours) <= record.normalized_time() <= now:
            return None, None
        return hashlib.sha256(_json(identity).encode()).hexdigest(), identity

    def save(self, record):
        key, identity = self._key(record)
        proof = (record.trigger or {}).get(PROOF_KEY)
        if (not key or record.confidence != "confirmed" or not record.reason
                or record.reason_code != "ha_logbook+exact_trace"
                or not record.trace_run_id or not isinstance(proof, dict)
                or proof.get("policy") != POLICY
                or proof.get("run_id") != record.trace_run_id
                or proof.get("source") != record.source_entity_id
                or not proof.get("command") or not proof.get("cause")):
            return False
        executed = _dt(proof.get("execution_time"))
        observed = _dt(identity["carrier_time"])
        # The source and exact target/effect are already established by RC12.
        # Also require the actual executed action to belong to this movement,
        # rather than retaining a nearest but stale run from the same automation.
        if executed is None or not 0 <= (observed - executed).total_seconds() <= 5:
            return False
        trace_context = proof.get("trace_context")
        if isinstance(trace_context, dict):
            contexts = {str(trace_context[k]) for k in ("id", "parent_id") if trace_context.get(k)}
            carrier_contexts = set(identity["carrier_contexts"])
            if contexts and carrier_contexts and not contexts.intersection(carrier_contexts):
                return False
        payload = _json({"identity": identity, "reason": record.reason,
                         "run_id": record.trace_run_id, "proof": proof})
        if len(payload.encode()) > self.MAX_BYTES:
            return False  # Never truncate a proof into something unverifiable.
        digest = hashlib.sha256(payload.encode()).hexdigest()
        old = self.db.execute("SELECT payload, conflict FROM exact_proofs_rc13 WHERE event_key=?", (key,)).fetchone()
        if old:
            # Two different proven results for the SAME exact event need investigation.
            # Never silently replace the first proof or choose whichever was latest.
            previous = json.loads(old["payload"])
            current = json.loads(payload)
            if previous != current:
                with self.db:
                    self.db.execute("UPDATE exact_proofs_rc13 SET conflict=1 WHERE event_key=?", (key,))
                return False
            return not old["conflict"]
        with self.db:
            self.db.execute("INSERT INTO exact_proofs_rc13 VALUES (?, ?, ?, ?, 0)",
                            (key, identity["event_time"], payload, digest))
        self.prune()
        return True

    def restore(self, record):
        if record.reason:
            return False  # Fresh RC12 evidence always takes precedence.
        key, identity = self._key(record)
        if not key:
            return False
        row = self.db.execute("SELECT * FROM exact_proofs_rc13 WHERE event_key=?", (key,)).fetchone()
        if not row or row["conflict"]:
            return False
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["digest"]:
            return False
        data = json.loads(row["payload"])
        if data.get("identity") != identity:
            return False
        record.reason = data["reason"]
        record.reason_code = "ha_logbook+retained_exact_trace"
        record.trace_run_id = data["run_id"]
        record.trigger[PROOF_KEY] = deepcopy(data["proof"])
        return True
