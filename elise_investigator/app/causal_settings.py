from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CausalSettings:
    retention_hours: int = 12
    deep_fallback: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CausalSettings":
        raw = data if isinstance(data, dict) else {}
        retention = int(raw.get("retention_hours", 12))
        if not 1 <= retention <= 72:
            retention = 12
        fallback = raw.get("deep_fallback", True)
        if not isinstance(fallback, bool):
            fallback = True
        return cls(retention_hours=retention, deep_fallback=fallback)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CausalSettingsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> CausalSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = None
        return CausalSettings.from_dict(data)

    def save(self, settings: CausalSettings) -> CausalSettings:
        validated = CausalSettings.from_dict(settings.to_dict())
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(validated.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
        return validated
