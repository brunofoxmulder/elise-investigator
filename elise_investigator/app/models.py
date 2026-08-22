from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Evidence:
    kind: str
    summary: str
    timestamp: str | None = None
    source: str | None = None
    strength: str = "supporting"
    raw: Any = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.raw is None:
            data.pop("raw", None)
        return data


@dataclass(slots=True)
class InvestigationRequest:
    entity_id: str
    observed_time: str | None = None
    observed_value: Any = None
    attribute: str | None = None
    user_declaration: str | None = None
    window_minutes: int | None = None


@dataclass(slots=True)
class InvestigationResult:
    status: str
    entity_id: str
    entity_name: str | None
    event_type: str
    event_time: str | None
    observed: dict[str, Any]
    cause: dict[str, Any]
    chain: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    answer_text: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "event_type": self.event_type,
            "event_time": self.event_time,
            "observed": self.observed,
            "cause": self.cause,
            "chain": self.chain,
            "evidence": [item.to_dict() for item in self.evidence],
            "candidates": self.candidates,
            "limits": self.limits,
            "answer_text": self.answer_text,
            "meta": self.meta,
        }
