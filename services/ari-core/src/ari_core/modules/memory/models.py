from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

MemoryBlockLayer = Literal[
    "session",
    "daily",
    "weekly",
    "open_loop",
    "long_term",
    "self_model",
]


@dataclass(frozen=True, slots=True)
class MemoryBlock:
    layer: MemoryBlockLayer
    kind: str
    title: str
    body: str
    source: str
    importance: int = 3
    confidence: float = 1.0
    tags: tuple[str, ...] = ()
    subject_ids: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    id: str = field(default_factory=lambda: f"memory-block-{uuid4()}")
    created_at: str = field(default_factory=lambda: _now_iso())
    updated_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
