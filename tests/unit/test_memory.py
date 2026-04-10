from datetime import UTC, date, datetime

from ari_memory import Base, WeeklyStateRepository
from ari_state import WeeklyState
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


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
        assert fetched.last_review_at == datetime(2026, 4, 6, 15, 0)

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
