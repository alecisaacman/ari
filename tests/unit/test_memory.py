from datetime import UTC, date, datetime
from uuid import uuid4

from ari_memory import (
    AlertRepository,
    Base,
    ControllerEventRepository,
    ConversationStateRepository,
    OrchestrationRunRepository,
    SignalRepository,
    WeeklyStateRepository,
)
from ari_state import (
    Alert,
    AlertChannel,
    AlertEscalationLevel,
    ControllerEvent,
    ControllerEventType,
    ConversationState,
    EvidenceItem,
    OrchestrationRun,
    Signal,
    SignalSeverity,
    WeeklyState,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_conversation_state_repository_upserts_by_channel() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ConversationStateRepository(session)

        assert repository.get("imessage") is None

        created = repository.upsert(
            ConversationState(
                channel="imessage",
                cursor=100,
                messages=[{"role": "user", "content": "hello"}],
                updated_at=datetime(2026, 6, 19, 0, 0, tzinfo=UTC),
            )
        )
        session.commit()

        fetched = repository.get("imessage")
        assert fetched is not None
        assert fetched.cursor == 100
        assert fetched.messages == [{"role": "user", "content": "hello"}]

        updated = repository.upsert(
            ConversationState(
                channel="imessage",
                cursor=200,
                messages=[{"role": "user", "content": "second"}],
                updated_at=datetime(2026, 6, 19, 1, 0, tzinfo=UTC),
            )
        )
        session.commit()

        assert updated.cursor == 200
        assert repository.get("imessage").cursor == 200
        # upsert by channel, not a new row each time
        assert updated.id == created.id


def test_weekly_state_repository_upserts_and_gets() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = WeeklyStateRepository(session)

        created = repository.upsert(
            WeeklyState(
                week_start=date(2026, 4, 6),
                outcomes=["Ship the spine", "Lock explainability"],
                cannot_drift=["Daily check cadence"],
                blockers=["Pending schema review"],
                lesson="",
                last_review_at=datetime(2026, 4, 6, 15, 0, tzinfo=UTC),
            )
        )
        session.commit()

        fetched = repository.get(date(2026, 4, 6))
        assert fetched is not None
        assert fetched.week_start == created.week_start
        assert fetched.outcomes == created.outcomes
        assert fetched.cannot_drift == created.cannot_drift
        assert fetched.blockers == created.blockers
        assert fetched.lesson == created.lesson
        assert fetched.last_review_at == datetime(2026, 4, 6, 15, 0, tzinfo=UTC)

        updated = repository.upsert(
            WeeklyState(
                week_start=date(2026, 4, 6),
                outcomes=["Ship the spine", "Add signals"],
                cannot_drift=["Explainable alerts"],
                blockers=["None"],
                lesson="Protect the shared model first.",
                last_review_at=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
            )
        )

        assert updated.outcomes == ["Ship the spine", "Add signals"]
        assert updated.lesson == "Protect the shared model first."


def test_signal_repository_persists_explainable_evidence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    signal = Signal(
        state_date=date(2026, 4, 10),
        fingerprint="signal-fingerprint",
        kind="open_loop_accumulation",
        severity=SignalSeverity.WARNING,
        summary="7 open loops are active.",
        reason="Open loops exceeded the operating threshold.",
        evidence=[
            EvidenceItem(
                kind="open_loop_stats",
                summary="Open loop volume exceeds the baseline threshold.",
                entity_type="open_loop",
                entity_id=uuid4(),
                payload={
                    "total_open_loops": 7,
                    "stale_open_loop_ids": [str(uuid4())],
                },
            )
        ],
        related_entity_type="weekly_state",
        related_entity_id=uuid4(),
        detected_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
    )

    with Session(engine) as session:
        repository = SignalRepository(session)
        created = repository.create(signal)
        session.commit()

        fetched = repository.get(signal.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.state_date == date(2026, 4, 10)
        assert fetched.fingerprint == "signal-fingerprint"
        assert fetched.reason == signal.reason
        assert fetched.evidence[0].kind == "open_loop_stats"
        assert fetched.evidence[0].payload["total_open_loops"] == 7
        assert fetched.related_entity_type == "weekly_state"
        assert fetched.detected_at == datetime(2026, 4, 10, 12, 0, tzinfo=UTC)


def test_alert_repository_persists_reason_and_source_signal_ids() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    source_signal_id = uuid4()
    alert = Alert(
        state_date=date(2026, 4, 10),
        fingerprint="alert-fingerprint",
        channel=AlertChannel.HUB,
        escalation_level=AlertEscalationLevel.ELEVATED,
        title="Trajectory drift",
        message="Today's priorities are not reinforcing this week's outcomes.",
        reason="No meaningful overlap was found between the weekly outcomes and priorities.",
        source_signal_ids=[source_signal_id],
        created_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
    )

    with Session(engine) as session:
        repository = AlertRepository(session)
        created = repository.create(alert)
        session.commit()

        fetched = repository.get(alert.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.state_date == date(2026, 4, 10)
        assert fetched.fingerprint == "alert-fingerprint"
        assert fetched.reason == alert.reason
        assert fetched.source_signal_ids == [source_signal_id]
        assert fetched.escalation_level == AlertEscalationLevel.ELEVATED
        assert fetched.created_at == datetime(2026, 4, 10, 12, 0, tzinfo=UTC)


def test_orchestration_run_repository_persists_run_history() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    signal_id = uuid4()
    alert_id = uuid4()

    with Session(engine) as session:
        repository = OrchestrationRunRepository(session)
        created = repository.create(
            OrchestrationRun(
                state_date=date(2026, 4, 10),
                state_fingerprint="state-fingerprint",
                executed_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
                signal_ids=[signal_id],
                alert_ids=[alert_id],
            )
        )
        session.commit()

        fetched = repository.get_latest_for_state_date(date(2026, 4, 10))
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.state_fingerprint == "state-fingerprint"
        assert fetched.signal_ids == [signal_id]
        assert fetched.alert_ids == [alert_id]


def test_controller_event_repository_persists_ordered_event_stream() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    run_id = uuid4()

    with Session(engine) as session:
        repository = ControllerEventRepository(session)
        created = repository.create_many(
            [
                ControllerEvent(
                    run_id=run_id,
                    sequence_number=0,
                    occurred_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
                    event_type=ControllerEventType.OBSERVATION_INTAKE,
                    summary="Controller intake captured persisted signals and alerts.",
                    payload={"signal_ids": ["a"]},
                ),
                ControllerEvent(
                    run_id=run_id,
                    sequence_number=1,
                    occurred_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
                    event_type=ControllerEventType.DECISION_SELECTED,
                    summary="Controller selected a canonical decision for this cycle.",
                    payload={"decision_summary": "Inspect the file."},
                ),
            ]
        )
        session.commit()

        fetched = repository.list_for_run(run_id)

    assert [event.id for event in fetched] == [event.id for event in created]
    assert fetched[0].event_type == ControllerEventType.OBSERVATION_INTAKE
    assert fetched[1].event_type == ControllerEventType.DECISION_SELECTED
