from datetime import UTC, datetime

from ari_events import EventClassifier, RawInputNormalizer
from ari_state import EventCategory


def test_raw_input_normalizer_builds_canonical_text() -> None:
    normalizer = RawInputNormalizer()

    normalized = normalizer.normalize(
        {
            "source": "slack",
            "title": "Follow up with vendor",
            "body": "Task needs reply today",
            "occurred_at": datetime(2026, 4, 10, 9, 30, tzinfo=UTC),
        }
    )

    assert normalized.source == "slack"
    assert normalized.normalized_text == "follow up with vendor task needs reply today"


def test_event_classifier_maps_open_loop_update() -> None:
    normalizer = RawInputNormalizer()
    classifier = EventClassifier()

    normalized = normalizer.normalize(
        {
            "source": "slack",
            "title": "Open loop updated",
            "body": "Follow up with the team",
            "payload": {"open_loop_id": "abc123"},
            "occurred_at": datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        }
    )
    event = classifier.classify(normalized)

    assert event.category == EventCategory.OPEN_LOOP_UPDATE
    assert event.normalized_text == "open loop updated follow up with the team"


def test_event_classifier_prefers_explicit_event_category() -> None:
    normalizer = RawInputNormalizer()
    classifier = EventClassifier()

    normalized = normalizer.normalize(
        {
            "source": "capture-inbox",
            "title": "Useful article",
            "body": "Possible strategy input",
            "payload": {"event_category": "intelligence_item"},
            "occurred_at": datetime(2026, 4, 10, 11, 0, tzinfo=UTC),
        }
    )
    event = classifier.classify(normalized)

    assert event.category == EventCategory.INTELLIGENCE_ITEM
