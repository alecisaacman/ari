from ari_state import Event, EventCategory

from ari_events.types import NormalizedInput


class EventClassifier:
    """Maps normalized inputs into the canonical event model."""

    def classify(self, normalized: NormalizedInput) -> Event:
        category = self._infer_category(normalized)
        return Event(
            source=normalized.source,
            category=category,
            occurred_at=normalized.occurred_at,
            title=normalized.title,
            body=normalized.body,
            payload=normalized.payload,
            normalized_text=normalized.normalized_text,
        )

    def _infer_category(self, normalized: NormalizedInput) -> EventCategory:
        explicit_category = normalized.payload.get("event_category")
        if isinstance(explicit_category, str):
            try:
                return EventCategory(explicit_category)
            except ValueError:
                pass

        text = normalized.normalized_text
        source = normalized.source.lower()
        payload = normalized.payload

        if "daily check" in text or payload.get("daily_state"):
            return EventCategory.DAILY_UPDATE
        if "weekly plan" in text or "weekly planning" in text or payload.get("weekly_plan"):
            return EventCategory.WEEKLY_PLANNING
        if "weekly reflection" in text or payload.get("weekly_reflection"):
            return EventCategory.WEEKLY_REFLECTION
        if "open loop resolved" in text or payload.get("open_loop_status") == "closed":
            return EventCategory.OPEN_LOOP_RESOLVE
        if "open loop" in text and ("added" in text or "new" in text):
            return EventCategory.OPEN_LOOP_ADD
        if "open loop" in text or payload.get("open_loop_id"):
            return EventCategory.OPEN_LOOP_UPDATE
        if "project" in text or payload.get("project_id"):
            return EventCategory.PROJECT_UPDATE
        if source == "signal-engine" or payload.get("signal_id"):
            return EventCategory.SIGNAL_GENERATED
        if source == "alert-engine" or payload.get("alert_id"):
            return EventCategory.ALERT_GENERATED
        if "intelligence" in text or payload.get("intelligence_item"):
            return EventCategory.INTELLIGENCE_ITEM
        return EventCategory.CAPTURE
