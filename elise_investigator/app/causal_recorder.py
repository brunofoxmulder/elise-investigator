from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

OriginType = Literal["automation", "script", "user", "alexa", "integration", "unknown"]
Confidence = Literal["confirmed", "probable", "indeterminate"]


@dataclass(slots=True)
class CausalRecord:
    """One compact causal fact captured when an entity actually changes.

    The recorder deliberately stores only the useful causal projection plus
    identifiers that let Investigator reopen the technical proof later. Full
    Home Assistant traces are not duplicated in the database and are never
    part of the lightweight payload intended for a conversation agent.
    """

    entity_id: str
    event_time: str
    event_kind: str
    before_value: Any = None
    after_value: Any = None
    entity_name: str | None = None
    attribute: str | None = None
    origin_type: OriginType = "unknown"
    source_entity_id: str | None = None
    source_name: str | None = None
    reason: str | None = None
    reason_code: str | None = None
    trigger: dict[str, Any] | None = None
    factors: list[dict[str, Any]] | None = None
    confidence: Confidence = "indeterminate"
    trace_run_id: str | None = None
    trace_path: str | None = None
    record_id: int | None = None

    def normalized_time(self) -> datetime:
        value = datetime.fromisoformat(self.event_time.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def llm_payload(self) -> dict[str, Any]:
        """Return the intentionally tiny contract exposed to a LLM.

        The LLM is allowed to phrase established facts, not to inspect or
        reinterpret the causal proof. Automation/script implementation names,
        trace identifiers and raw triggers therefore stay private here.
        """

        payload: dict[str, Any] = {
            "entity": self.entity_name or self.entity_id,
            "event": self.event_kind,
            "time": self.event_time,
            "confidence": self.confidence,
        }
        if self.after_value is not None:
            payload["value"] = self.after_value
        if self.attribute:
            payload["attribute"] = self.attribute
        if self.origin_type in {"automation", "script"}:
            if self.reason:
                payload["reason"] = self.reason
        elif self.origin_type == "alexa":
            payload["source"] = "Alexa"
        elif self.origin_type == "user":
            payload["source"] = "utilisateur"
        elif self.origin_type not in {"unknown", "integration"}:
            payload["source"] = self.origin_type
        return payload


class CausalRecorder:
    """Persistent rolling causal journal owned by Élise Investigator.

    Writing this SQLite file does not write to Home Assistant. The only data
    retained are compact causal records and proof references. Retention is
    enforced both on insert and on explicit prune calls.
    """

    MIN_RETENTION_HOURS = 1
    MAX_RETENTION_HOURS = 72

    def __init__(self, path: str | Path, *, retention_hours: int = 12):
        self.path = Path(path)
        self.retention_hours = self._validate_retention(retention_hours)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA busy_timeout=3000")
        self._create_schema()

    @classmethod
    def _validate_retention(cls, value: int) -> int:
        hours = int(value)
        if not cls.MIN_RETENTION_HOURS <= hours <= cls.MAX_RETENTION_HOURS:
            raise ValueError(
                f"retention_hours doit être compris entre {cls.MIN_RETENTION_HOURS} et "
                f"{cls.MAX_RETENTION_HOURS}"
            )
        return hours

    def _create_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS causal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                entity_name TEXT,
                event_time TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                attribute TEXT,
                origin_type TEXT NOT NULL,
                source_entity_id TEXT,
                source_name TEXT,
                reason TEXT,
                reason_code TEXT,
                trigger_json TEXT,
                factors_json TEXT,
                confidence TEXT NOT NULL,
                trace_run_id TEXT,
                trace_path TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_causal_entity_time
                ON causal_events(entity_id, event_time DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_causal_event_time
                ON causal_events(event_time);
            """
        )
        self._db.commit()

    def set_retention_hours(self, value: int) -> None:
        self.retention_hours = self._validate_retention(value)
        self.prune()

    @staticmethod
    def _dump(value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _load(value: str | None) -> Any:
        if value is None:
            return None
        return json.loads(value)

    @staticmethod
    def _utc_iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def record(self, item: CausalRecord, *, now: datetime | None = None) -> CausalRecord:
        event_time = item.normalized_time()
        item.event_time = self._utc_iso(event_time)
        created = now or datetime.now(timezone.utc)
        cursor = self._db.execute(
            """
            INSERT INTO causal_events (
                entity_id, entity_name, event_time, event_kind,
                before_json, after_json, attribute, origin_type,
                source_entity_id, source_name, reason, reason_code,
                trigger_json, factors_json, confidence,
                trace_run_id, trace_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.entity_id,
                item.entity_name,
                item.event_time,
                item.event_kind,
                self._dump(item.before_value),
                self._dump(item.after_value),
                item.attribute,
                item.origin_type,
                item.source_entity_id,
                item.source_name,
                item.reason,
                item.reason_code,
                self._dump(item.trigger),
                self._dump(item.factors),
                item.confidence,
                item.trace_run_id,
                item.trace_path,
                self._utc_iso(created),
            ),
        )
        self._db.commit()
        item.record_id = int(cursor.lastrowid)
        self.prune(now=created)
        return item

    def update(self, item: CausalRecord) -> CausalRecord:
        """Replace the causal projection of an already captured event.

        The event identity/time/effect may be normalized again, but the row id is
        preserved. This is used when the stream stores an event immediately and a
        bounded background investigation later enriches its proof.
        """
        if item.record_id is None:
            raise ValueError("record_id est obligatoire pour mettre à jour un événement")
        item.event_time = self._utc_iso(item.normalized_time())
        cursor = self._db.execute(
            """
            UPDATE causal_events SET
                entity_id = ?, entity_name = ?, event_time = ?, event_kind = ?,
                before_json = ?, after_json = ?, attribute = ?, origin_type = ?,
                source_entity_id = ?, source_name = ?, reason = ?, reason_code = ?,
                trigger_json = ?, factors_json = ?, confidence = ?,
                trace_run_id = ?, trace_path = ?
            WHERE id = ?
            """,
            (
                item.entity_id,
                item.entity_name,
                item.event_time,
                item.event_kind,
                self._dump(item.before_value),
                self._dump(item.after_value),
                item.attribute,
                item.origin_type,
                item.source_entity_id,
                item.source_name,
                item.reason,
                item.reason_code,
                self._dump(item.trigger),
                self._dump(item.factors),
                item.confidence,
                item.trace_run_id,
                item.trace_path,
                int(item.record_id),
            ),
        )
        self._db.commit()
        if cursor.rowcount != 1:
            raise KeyError(f"Événement causal introuvable: {item.record_id}")
        return item

    def get(self, record_id: int) -> CausalRecord | None:
        row = self._db.execute("SELECT * FROM causal_events WHERE id = ?", (int(record_id),)).fetchone()
        return self._row_to_record(row) if row else None

    def latest(self, entity_id: str, *, attribute: str | None = None) -> CausalRecord | None:
        sql = "SELECT * FROM causal_events WHERE entity_id = ?"
        params: list[Any] = [entity_id]
        if attribute is not None:
            sql += " AND attribute = ?"
            params.append(attribute)
        sql += " ORDER BY event_time DESC, id DESC LIMIT 1"
        row = self._db.execute(sql, params).fetchone()
        return self._row_to_record(row) if row else None

    def for_entity(self, entity_id: str, *, limit: int = 50) -> list[CausalRecord]:
        bounded = max(1, min(int(limit), 500))
        rows = self._db.execute(
            "SELECT * FROM causal_events WHERE entity_id = ? ORDER BY event_time DESC, id DESC LIMIT ?",
            (entity_id, bounded),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _same_value(actual: Any, expected: Any) -> bool:
        if expected is None:
            return True
        if actual is None:
            return False
        if str(actual) == str(expected):
            return True
        try:
            return abs(float(actual) - float(expected)) < 1e-9
        except (TypeError, ValueError):
            return False

    def find_best(
        self,
        entity_id: str,
        *,
        observed_time: str | None = None,
        observed_value: Any = None,
        attribute: str | None = None,
        limit: int = 100,
    ) -> CausalRecord | None:
        """Resolve a recorded event using explicit user clues, else return latest.

        When a time is supplied, the nearest matching value/attribute wins. Without
        time, the latest matching value wins. A value clue is never silently ignored.
        """
        candidates = self.for_entity(entity_id, limit=limit)
        if attribute is not None:
            candidates = [item for item in candidates if item.attribute == attribute]
        if observed_value is not None:
            candidates = [item for item in candidates if self._same_value(item.after_value, observed_value)]
        if not candidates:
            return None
        if not observed_time:
            return candidates[0]
        try:
            wanted = datetime.fromisoformat(str(observed_time).replace("Z", "+00:00"))
            if wanted.tzinfo is None:
                wanted = wanted.replace(tzinfo=timezone.utc)
            wanted = wanted.astimezone(timezone.utc)
        except ValueError:
            return candidates[0]
        return min(candidates, key=lambda item: abs((item.normalized_time() - wanted).total_seconds()))

    def recent(self, *, limit: int = 100) -> list[CausalRecord]:
        bounded = max(1, min(int(limit), 1000))
        rows = self._db.execute(
            "SELECT * FROM causal_events ORDER BY event_time DESC, id DESC LIMIT ?",
            (bounded,),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def prune(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        cutoff = current.astimezone(timezone.utc) - timedelta(hours=self.retention_hours)
        cursor = self._db.execute(
            "DELETE FROM causal_events WHERE event_time < ?",
            (self._utc_iso(cutoff),),
        )
        self._db.commit()
        return max(0, int(cursor.rowcount))

    def count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) AS n FROM causal_events").fetchone()
        return int(row["n"]) if row else 0

    def _row_to_record(self, row: sqlite3.Row) -> CausalRecord:
        return CausalRecord(
            record_id=int(row["id"]),
            entity_id=str(row["entity_id"]),
            entity_name=row["entity_name"],
            event_time=str(row["event_time"]),
            event_kind=str(row["event_kind"]),
            before_value=self._load(row["before_json"]),
            after_value=self._load(row["after_json"]),
            attribute=row["attribute"],
            origin_type=str(row["origin_type"]),
            source_entity_id=row["source_entity_id"],
            source_name=row["source_name"],
            reason=row["reason"],
            reason_code=row["reason_code"],
            trigger=self._load(row["trigger_json"]),
            factors=self._load(row["factors_json"]),
            confidence=str(row["confidence"]),
            trace_run_id=row["trace_run_id"],
            trace_path=row["trace_path"],
        )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "CausalRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
