from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class RequestJournal:
    """Small local journal of what Investigator receives and returns."""

    def __init__(self, path: str | Path, *, retention_hours: int = 12):
        self.path = Path(path)
        self.retention_hours = max(1, min(int(retention_hours), 72))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS investigator_io (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requested_at TEXT NOT NULL,
                route TEXT NOT NULL,
                request_json TEXT NOT NULL,
                response_json TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_investigator_io_time ON investigator_io(requested_at DESC, id DESC)"
        )
        self._db.commit()

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    def set_retention_hours(self, value: int) -> None:
        self.retention_hours = max(1, min(int(value), 72))
        self.prune()

    def append(
        self,
        route: str,
        request_payload: Any,
        response_payload: Any,
        *,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(timezone.utc)
        self._db.execute(
            "INSERT INTO investigator_io(requested_at, route, request_json, response_json) VALUES (?, ?, ?, ?)",
            (
                self._iso(current),
                str(route),
                self._dump(request_payload),
                self._dump(response_payload),
            ),
        )
        self._db.commit()
        self.prune(now=current)

    def recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 100))
        rows = self._db.execute(
            "SELECT * FROM investigator_io ORDER BY requested_at DESC, id DESC LIMIT ?",
            (bounded,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "time": str(row["requested_at"]),
                "route": str(row["route"]),
                "request": json.loads(row["request_json"]),
                "response": json.loads(row["response_json"]),
            }
            for row in rows
        ]

    def prune(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        cutoff = current.astimezone(timezone.utc) - timedelta(hours=self.retention_hours)
        cursor = self._db.execute(
            "DELETE FROM investigator_io WHERE requested_at < ?",
            (self._iso(cutoff),),
        )
        self._db.commit()
        return max(0, int(cursor.rowcount))

    def close(self) -> None:
        self._db.close()
