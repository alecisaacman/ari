"""The dispatch-safety boundary for recovered actions.

ARI cannot revoke a side effect after it starts. What it can enforce for the
current in-process, single-host effects (filesystem writes and allowlisted
subprocesses) is:

- Pre-dispatch: only the current fence generation, issued to the active attempt
  for the exact reserved execution, can cross into the effect. Crossing is a
  compare-and-swap committed while the logical action's dispatch lock is held.
- In flight: the dispatch lock for a logical action (task_id, action_id) is an OS
  `flock` held from the crossing commit through the effect until the dispatch is
  recorded as returned. Subprocess children inherit it. The kernel releases it
  only when every holder has exited or closed it.
- Quiescence: if ARI acquires that lock while a fence is still `crossing`, nothing
  is inside that dispatch any more, so its effect can no longer land. This is the
  fact that makes redispatch after confirmed absence safe. A held lock fails closed.

These guarantees hold only for effects that cross this boundary on this host with
this lock directory. They are not provider-side idempotency, and they do not stop
an effect that is already in progress.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import DispatchFenceState
from .ledger import ExecutionLedger, _decode_row, _json, sanitize_payload

Clock = Callable[[], datetime]

# Fence states proving that no effect from that dispatch can still land.
QUIESCENT_FENCE_STATES = frozenset(
    {
        DispatchFenceState.RETURNED,
        DispatchFenceState.QUIESCED,
        DispatchFenceState.REVOKED,
    }
)


class DispatchFenceRejected(ValueError):
    """The fence does not authorize crossing into the effect."""


class DispatchQuiescenceUnproven(ValueError):
    """ARI cannot prove that an earlier dispatch can no longer take effect."""


@dataclass(frozen=True, slots=True)
class DispatchQuiescenceResult:
    fence_id: str
    execution_id: str
    task_id: str
    action_id: str
    previous_state: DispatchFenceState
    state: DispatchFenceState
    changed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DispatchLock:
    """An exclusive, non-blocking `flock` on one logical action's lock file.

    Release only closes this descriptor, never `LOCK_UN`, so a subprocess that
    inherited the descriptor keeps the lock held for as long as it lives.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def try_acquire(self) -> bool:
        if self.fd is not None:
            raise RuntimeError("Dispatch lock is already held by this handle.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return True

    def release(self) -> None:
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


class DispatchFences:
    """Durable dispatch fences plus the per-action locks that make them enforceable."""

    def __init__(
        self,
        db_path: Path,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.ledger = ExecutionLedger(db_path)
        # Derived from the database, never configured: every dispatcher sharing a
        # ledger must contend on the same locks for mutual exclusion to hold.
        self.lock_dir = db_path.parent / "dispatch-locks"
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def lock_key(task_id: str, action_id: str) -> str:
        material = f"{task_id}\0{action_id}".encode()
        return hashlib.sha256(material).hexdigest()

    def lock_for(self, task_id: str, action_id: str) -> DispatchLock:
        return DispatchLock(self.lock_dir / f"{self.lock_key(task_id, action_id)}.lock")

    @classmethod
    def issue(
        cls,
        connection: sqlite3.Connection,
        *,
        execution_id: str,
        task_id: str,
        action_id: str,
        idempotency_key: str,
        attempt_id: str,
        now: str,
    ) -> str:
        """Issue the next-generation fence for a newly reserved execution."""
        row = connection.execute(
            """
            select coalesce(max(generation), 0) + 1 as next_generation
            from ari_execution_dispatch_fences where task_id = ? and action_id = ?
            """,
            (task_id, action_id),
        ).fetchone()
        fence_id = f"dispatch-fence-{uuid4()}"
        connection.execute(
            """
            insert into ari_execution_dispatch_fences (
                fence_id, execution_id, task_id, action_id, idempotency_key, attempt_id,
                generation, lock_key, state, issued_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fence_id,
                execution_id,
                task_id,
                action_id,
                idempotency_key,
                attempt_id,
                int(row["next_generation"]),
                cls.lock_key(task_id, action_id),
                DispatchFenceState.ISSUED,
                now,
            ),
        )
        return fence_id

    @staticmethod
    def validate_crossing(
        connection: sqlite3.Connection,
        *,
        execution_id: str,
        task_id: str,
        action_id: str,
        idempotency_key: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        """Return the fence that authorizes this exact crossing, or refuse.

        The caller must hold the logical action's dispatch lock and must commit the
        crossing in the same transaction.
        """
        row = connection.execute(
            "select * from ari_execution_dispatch_fences where execution_id = ?",
            (execution_id,),
        ).fetchone()
        if row is None:
            raise DispatchFenceRejected("No dispatch fence was issued for this execution.")
        fence = _decode_row(row)
        if fence["task_id"] != task_id or fence["action_id"] != action_id:
            raise DispatchFenceRejected("The dispatch fence belongs to a different action.")
        if fence["idempotency_key"] != idempotency_key:
            raise DispatchFenceRejected("The dispatch fence was issued for a different digest.")
        if fence["attempt_id"] != attempt_id:
            raise DispatchFenceRejected("The dispatch fence was issued to another attempt.")
        if fence["state"] != DispatchFenceState.ISSUED:
            raise DispatchFenceRejected(
                f"The dispatch fence is {fence['state']}; a fence crosses at most once."
            )
        latest = connection.execute(
            """
            select max(generation) as generation from ari_execution_dispatch_fences
            where task_id = ? and action_id = ?
            """,
            (task_id, action_id),
        ).fetchone()
        if int(latest["generation"]) != int(fence["generation"]):
            raise DispatchFenceRejected("A newer dispatch generation supersedes this fence.")
        unproven = connection.execute(
            """
            select fence_id from ari_execution_dispatch_fences
            where task_id = ? and action_id = ? and state = ? and fence_id != ?
            """,
            (task_id, action_id, DispatchFenceState.CROSSING, fence["fence_id"]),
        ).fetchone()
        if unproven is not None:
            raise DispatchFenceRejected(
                "An earlier dispatch of this action has not been proven quiescent."
            )
        return fence

    @staticmethod
    def mark_crossing(connection: sqlite3.Connection, fence_id: str, *, now: str) -> None:
        updated = connection.execute(
            """
            update ari_execution_dispatch_fences set state = ?, crossing_at = ?
            where fence_id = ? and state = ?
            """,
            (DispatchFenceState.CROSSING, now, fence_id, DispatchFenceState.ISSUED),
        )
        if updated.rowcount != 1:
            raise DispatchFenceRejected("The dispatch fence changed before crossing.")

    def mark_returned(self, fence_id: str, *, outcome: dict[str, Any]) -> None:
        """Record that the dispatch call returned; called before the lock is released."""
        with self.ledger._transaction() as connection:
            connection.execute(
                """
                update ari_execution_dispatch_fences
                set state = ?, returned_at = ?, outcome_json = ?
                where fence_id = ? and state = ?
                """,
                (
                    DispatchFenceState.RETURNED,
                    self._now(),
                    _json(sanitize_payload(outcome)),
                    fence_id,
                    DispatchFenceState.CROSSING,
                ),
            )

    @staticmethod
    def revoke_unused(
        connection: sqlite3.Connection,
        execution_id: str,
        *,
        now: str,
        reason: str,
    ) -> None:
        """Revoke a fence that never crossed; a crossing fence is left untouched."""
        connection.execute(
            """
            update ari_execution_dispatch_fences
            set state = ?, revoked_at = ?, terminal_by = 'ari', terminal_reason = ?
            where execution_id = ? and state = ?
            """,
            (DispatchFenceState.REVOKED, now, reason, execution_id, DispatchFenceState.ISSUED),
        )

    def prove_quiescent(
        self,
        *,
        task_id: str,
        execution_id: str,
        proven_by: str,
        reason: str,
    ) -> DispatchQuiescenceResult:
        """Prove that no effect from this execution's dispatch can still land.

        The proof is mechanical: acquire the logical action's dispatch lock. If any
        process or inheriting subprocess is still inside the dispatch, the lock is
        held and this fails closed.
        """
        if not proven_by.strip() or not reason.strip():
            raise ValueError("proven_by and reason are required.")
        fence = self.ledger._one(
            "select * from ari_execution_dispatch_fences where execution_id = ?",
            (execution_id,),
        )
        if fence is None or fence["task_id"] != task_id:
            raise DispatchQuiescenceUnproven(
                "No dispatch fence exists for this execution; quiescence cannot be proven."
            )
        lock = self.lock_for(task_id, str(fence["action_id"]))
        if not lock.try_acquire():
            raise DispatchQuiescenceUnproven(
                "The action's dispatch lock is held; a dispatch may still be in flight."
            )
        try:
            with self.ledger._transaction() as connection:
                current = _decode_row(
                    connection.execute(
                        "select * from ari_execution_dispatch_fences where fence_id = ?",
                        (fence["fence_id"],),
                    ).fetchone()
                )
                previous = DispatchFenceState(current["state"])
                if previous in QUIESCENT_FENCE_STATES:
                    return self._quiescence(current, previous, changed=False)
                now = self._now()
                resulting = (
                    DispatchFenceState.QUIESCED
                    if previous is DispatchFenceState.CROSSING
                    else DispatchFenceState.REVOKED
                )
                timestamp_column = (
                    "quiesced_at" if resulting is DispatchFenceState.QUIESCED else "revoked_at"
                )
                connection.execute(
                    f"""
                    update ari_execution_dispatch_fences
                    set state = ?, {timestamp_column} = ?, terminal_by = ?, terminal_reason = ?
                    where fence_id = ? and state = ?
                    """,
                    (resulting, now, proven_by, reason, current["fence_id"], previous),
                )
                _insert_quiescence_event(
                    connection,
                    task_id=task_id,
                    attempt_id=str(current["attempt_id"]),
                    payload={
                        "fence_id": current["fence_id"],
                        "execution_id": execution_id,
                        "action_id": current["action_id"],
                        "generation": current["generation"],
                        "previous_state": previous,
                        "state": resulting,
                        "proven_by": proven_by,
                        "reason": reason,
                        "proof": "dispatch_lock_acquired",
                    },
                    now=now,
                )
                current["state"] = resulting
                return self._quiescence(current, previous, changed=True)
        finally:
            lock.release()

    @staticmethod
    def _quiescence(
        fence: dict[str, Any],
        previous: DispatchFenceState,
        *,
        changed: bool,
    ) -> DispatchQuiescenceResult:
        return DispatchQuiescenceResult(
            fence_id=str(fence["fence_id"]),
            execution_id=str(fence["execution_id"]),
            task_id=str(fence["task_id"]),
            action_id=str(fence["action_id"]),
            previous_state=previous,
            state=DispatchFenceState(fence["state"]),
            changed=changed,
        )

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("Dispatch fence clock must be timezone-aware.")
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _insert_quiescence_event(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    attempt_id: str,
    payload: dict[str, Any],
    now: str,
) -> None:
    sequence = ExecutionLedger._next_sequence(connection, "ari_execution_events", task_id)
    connection.execute(
        """
        insert into ari_execution_events (
            event_id, task_id, attempt_id, sequence, event_type,
            payload_json, provenance_json, created_at
        ) values (?, ?, ?, ?, 'action.dispatch_quiesced', ?, ?, ?)
        """,
        (
            f"event-{uuid4()}",
            task_id,
            attempt_id,
            sequence,
            _json(sanitize_payload(payload)),
            _json({"authority": "ari", "operation": "dispatch_quiescence_proof"}),
            now,
        ),
    )
