from __future__ import annotations

from datetime import datetime, timezone

from ari_events.types import NormalizedInput


class RawInputNormalizer:
    """Normalizes raw input into a predictable event-ready envelope."""

    def normalize(self, raw: dict[str, object]) -> NormalizedInput:
        source = str(raw.get("source", "unknown")).strip() or "unknown"
        title = str(raw.get("title", "")).strip()
        body = str(raw.get("body", "")).strip()
        occurred_at = self._coerce_datetime(raw.get("occurred_at"))
        normalized_text = " ".join(part for part in [title, body] if part).strip().lower()
        payload = dict(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {}

        return NormalizedInput(
            source=source,
            occurred_at=occurred_at,
            title=title or "Untitled event",
            body=body,
            normalized_text=normalized_text,
            payload=payload,
        )

    def _coerce_datetime(self, value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return datetime.now(tz=timezone.utc)
