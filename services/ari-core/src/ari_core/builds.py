"""ARI's build list: what ARI wants to build for itself, and what Alec decided.

ARI proposes; Alec approves, holds, or declines. An approved build is a brief for a
coding agent to pick up. ARI never starts building on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from ari_memory.tables import BuildProposalRow
from sqlalchemy import select
from sqlalchemy.orm import Session

PROPOSED = "proposed"
APPROVED = "approved"
HELD = "held"
DECLINED = "declined"
DONE = "done"
# Set by ARI's builder (ari_core.builder), never by a decision.
BUILDING = "building"
BUILT = "built"
STUCK = "stuck"
SHIPPING = "shipping"
DECISIONS = {"approve": APPROVED, "hold": HELD, "decline": DECLINED, "done": DONE}
STILL_OPEN = (PROPOSED, APPROVED, HELD, BUILDING, BUILT, STUCK, SHIPPING)


@dataclass(frozen=True, slots=True)
class Build:
    id: UUID
    title: str
    why: str
    brief: str
    skill_id: str | None
    status: str
    created_at: datetime
    branch: str | None = None
    result: str | None = None

    def describe(self) -> dict[str, str | None]:
        return {
            "id": str(self.id),
            "title": self.title,
            "why": self.why,
            "brief": self.brief,
            "skill_id": self.skill_id,
            "status": self.status,
            "proposed_at": self.created_at.isoformat(),
            "branch": self.branch,
            "result": self.result,
        }


def propose_build(
    session: Session,
    *,
    title: str,
    why: str,
    brief: str,
    now: datetime,
    skill_id: str | None = None,
    source: str = "ari.review",
) -> tuple[Build, bool]:
    """Add a build to the list. A build already on it is returned instead, unchanged."""
    wanted = title.strip().lower()
    for build in list_builds(session, statuses=STILL_OPEN):
        if build.title.strip().lower() == wanted or (skill_id and build.skill_id == skill_id):
            return build, False
    row = BuildProposalRow(
        id=uuid4(),
        title=title.strip(),
        why=why.strip(),
        brief=brief.strip(),
        skill_id=skill_id,
        status=PROPOSED,
        source=source,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return _to_model(row), True


def decide_build(session: Session, build_id: UUID, decision: str, *, now: datetime) -> Build | None:
    status = DECISIONS.get(decision)
    row = session.get(BuildProposalRow, build_id)
    if status is None or row is None:
        return None
    row.status = status
    row.decided_at = now
    session.commit()
    return _to_model(row)


def list_builds(session: Session, *, statuses: tuple[str, ...] = STILL_OPEN) -> list[Build]:
    rows = session.scalars(
        select(BuildProposalRow).where(BuildProposalRow.status.in_(statuses)).order_by(BuildProposalRow.created_at)
    ).all()
    return [_to_model(row) for row in rows]


def _to_model(row: BuildProposalRow) -> Build:
    return Build(
        id=row.id,
        title=row.title,
        why=row.why,
        brief=row.brief,
        skill_id=row.skill_id,
        status=row.status,
        created_at=row.created_at,
        branch=row.branch,
        result=row.result,
    )
