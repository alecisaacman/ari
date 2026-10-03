"""The dispatch-safety boundary for recovered actions.

ARI cannot revoke a side effect after it starts. What it enforces for the current
in-process, single-host effects (filesystem writes and command-capability subprocesses) is:

- Pre-dispatch: only the current fence generation, issued to the active attempt for
  the exact reserved execution, can cross into the effect, and only when every
  earlier dispatch of the action has been proven unable to land. Crossing is a
  compare-and-swap committed while the logical action's dispatch lock is held.
- In flight: the dispatch lock for a logical action (task_id, action_id) is an OS
  `flock` held from the crossing commit through the effect until the dispatch is
  recorded as returned. It gives local mutual exclusion between dispatchers.
- Landing ruled out: a fence earns a one-time `landing_token` only when ARI has
  established that its dispatch can no longer produce the effect. That is possible
  only for `in_process` effects: the dispatch call returned, or the exact lock inode
  the dispatcher held could be acquired (so the dispatching process is gone). For
  `unbounded` effects (subprocesses and anything ARI cannot track) neither fact
  rules out a descendant landing the effect later, so no token is ever issued.

A dispatch returning, or its lock being free, is never by itself "safe to redispatch".
Redispatch also needs an absence observation bound to the landing token; see
`EffectReconciler`. None of this is provider-side idempotency or exactly-once.
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

from .contracts import DispatchFenceState, EffectTerminality
from .ledger import ExecutionLedger, _decode_row, _json, sanitize_payload

Clock = Callable[[], datetime]
TerminalityClassifier = Callable[[dict[str, Any]], EffectTerminality]

# Built-in actions whose effect `execute_action` performs synchronously in the calling
# thread. Everything else, including run_command, is unbounded.
IN_PROCESS_ACTION_TYPES = frozenset({"read_file", "write_file", "patch_file"})

# Fence states that may follow a crossing. Whether any of them rules out a late
# effect depends on the fence's terminality; only `landing_token` records that.
POST_CROSSING_STATES = frozenset(
    {
        DispatchFenceState.CROSSING,
        DispatchFenceState.RETURNED,
        DispatchFenceState.LOCK_RELEASED,
    }
)


def classify_effect_terminality(action: dict[str, Any]) -> EffectTerminality:
    """Classify an action dispatched through the built-in `execute_action`."""
    action_type = str(action.get("type") or action.get("kind") or "").strip()
    if action_type in IN_PROCESS_ACTION_TYPES:
        return EffectTerminality.IN_PROCESS
    return EffectTerminality.UNBOUNDED


def unbounded_terminality(_action: dict[str, Any]) -> EffectTerminality:
    """The classification for executors ARI cannot inspect."""
    return EffectTerminality.UNBOUNDED


class DispatchFenceRejected(ValueError):
    """The fence does not authorize crossing into the effect."""


class DispatchLandingUnproven(ValueError):
    """ARI cannot establish that an earlier dispatch can no longer produce its effect."""


@dataclass(frozen=True, slots=True)
class LockIdentity:
    path: str
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class DispatchLandingProof:
    fence_id: str
    execution_id: str
    task_id: str
    action_id: str
    previous_state: DispatchFenceState
    state: DispatchFenceState
    terminality: EffectTerminality
    landing_token: str
    changed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DispatchLock:
    """An exclusive, non-blocking `flock` on one logical action's lock file.

    Release only closes this descriptor, never `LOCK_UN`, so a subprocess that
    inherited the descriptor keeps the lock held for as long as it lives. The lock is
    only meaningful for the inode it was taken on, recorded in `identity`.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None
        self.identity: LockIdentity | None = None
        self.refusal: str | None = None

    def try_acquire(self, *, create: bool = True) -> bool:
        if self.fd is not None:
            raise RuntimeError("Dispatch lock is already held by this handle.")
        self.refusal = None
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_RDWR | (os.O_CREAT if create else 0), 0o600)
        except FileNotFoundError:
            if create:
                raise
            self.refusal = "The dispatch lock file no longer exists."
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            self.refusal = "The dispatch lock is held; a dispatch may still be in flight."
            return False
        except BaseException:
            os.close(fd)
            raise
        # A lock on an inode that is no longer at the path excludes nobody: the file
        # was unlinked or replaced between open and flock.
        held = os.fstat(fd)
        try:
            current = os.stat(self.path)
        except FileNotFoundError:
            current = None
        if current is None or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            os.close(fd)
            self.refusal = "The dispatch lock file was replaced while it was being locked."
            return False
        self.fd = fd
        self.identity = LockIdentity(str(self.path), int(held.st_dev), int(held.st_ino))
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
        # Derived from the canonical database path, never configured: dispatchers that
        # reach one database through symlinks or relative paths contend on the same
        # locks. Hard links to the database are not supported (nor by SQLite); proofs
        # still fail closed for them because they check the recorded lock inode.
        self.lock_dir = Path(db_path).resolve().parent / "dispatch-locks"
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
        effect_terminality: EffectTerminality,
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
                generation, lock_key, state, issued_at, effect_terminality
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                EffectTerminality(effect_terminality),
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
        # Any earlier dispatch that crossed and was never proven unable to land blocks
        # this one, whatever its recorded state: returned and lock_released do not
        # rule out a descendant landing an unbounded effect.
        placeholders = ", ".join("?" for _ in POST_CROSSING_STATES)
        unproven = connection.execute(
            f"""
            select fence_id from ari_execution_dispatch_fences
            where task_id = ? and action_id = ? and fence_id != ?
              and state in ({placeholders}) and landing_token is null
            """,
            (task_id, action_id, fence["fence_id"], *sorted(POST_CROSSING_STATES)),
        ).fetchone()
        if unproven is not None:
            raise DispatchFenceRejected(
                "An earlier dispatch of this action has not been proven unable to land."
            )
        return fence

    @staticmethod
    def mark_crossing(
        connection: sqlite3.Connection,
        fence_id: str,
        *,
        lock: LockIdentity,
        now: str,
    ) -> None:
        updated = connection.execute(
            """
            update ari_execution_dispatch_fences
            set state = ?, crossing_at = ?, lock_path = ?, lock_device = ?, lock_inode = ?
            where fence_id = ? and state = ?
            """,
            (
                DispatchFenceState.CROSSING,
                now,
                lock.path,
                lock.device,
                lock.inode,
                fence_id,
                DispatchFenceState.ISSUED,
            ),
        )
        if updated.rowcount != 1:
            raise DispatchFenceRejected("The dispatch fence changed before crossing.")

    def mark_returned(self, fence_id: str, *, outcome: dict[str, Any]) -> None:
        """Record that the dispatch call returned; called before the lock is released.

        For an in_process effect the call returning is the effect's end, so landing is
        ruled out here. For an unbounded effect it is not.
        """
        now = self._now()
        with self.ledger._transaction() as connection:
            connection.execute(
                """
                update ari_execution_dispatch_fences
                set state = ?, returned_at = ?, outcome_json = ?,
                    landing_token = case when effect_terminality = ? then ? else null end,
                    landing_ruled_out_at = case when effect_terminality = ? then ? else null end
                where fence_id = ? and state = ?
                """,
                (
                    DispatchFenceState.RETURNED,
                    now,
                    _json(sanitize_payload(outcome)),
                    EffectTerminality.IN_PROCESS,
                    _new_landing_token(),
                    EffectTerminality.IN_PROCESS,
                    now,
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
            set state = ?, revoked_at = ?, terminal_by = 'ari', terminal_reason = ?,
                landing_token = ?, landing_ruled_out_at = ?
            where execution_id = ? and state = ?
            """,
            (
                DispatchFenceState.REVOKED,
                now,
                reason,
                _new_landing_token(),
                now,
                execution_id,
                DispatchFenceState.ISSUED,
            ),
        )

    def rule_out_landing(
        self,
        *,
        task_id: str,
        execution_id: str,
        proven_by: str,
        reason: str,
    ) -> DispatchLandingProof:
        """Establish that this execution's dispatch can no longer produce its effect.

        Returns the fence's landing token. A reconciler must obtain it *before*
        observing the effect and present it with an absence reconciliation; only that
        observation can make the action safe to redispatch.

        Fails closed with `DispatchLandingUnproven` when the effect is unbounded, when
        the dispatcher's lock is held, or when the lock file is missing or is not the
        inode the dispatcher held.
        """
        if not proven_by.strip() or not reason.strip():
            raise ValueError("proven_by and reason are required.")
        fence = self.ledger._one(
            "select * from ari_execution_dispatch_fences where execution_id = ?",
            (execution_id,),
        )
        if fence is None or fence["task_id"] != task_id:
            raise DispatchLandingUnproven(
                "No dispatch fence exists for this execution; landing cannot be ruled out."
            )
        if fence["landing_token"] is not None:
            return self._proof(fence, DispatchFenceState(fence["state"]), changed=False)
        state = DispatchFenceState(fence["state"])
        terminality = _terminality(fence)
        if state is DispatchFenceState.ISSUED or state is DispatchFenceState.REVOKED:
            # Never crossed. Revoking is a compare-and-swap against crossing, so no
            # lock is needed: whichever commits first wins.
            return self._settle(
                fence,
                expected=state,
                resulting=DispatchFenceState.REVOKED,
                proven_by=proven_by,
                reason=reason,
                proof="fence_never_crossed",
            )
        if terminality is not EffectTerminality.IN_PROCESS:
            raise DispatchLandingUnproven(
                f"The dispatch is {state} but its effect is {terminality}: a descendant "
                "process or external system may still produce it, so landing cannot be "
                "ruled out."
            )
        if state is not DispatchFenceState.CROSSING:
            raise DispatchLandingUnproven(
                f"The dispatch fence is {state} without a landing proof."
            )
        recorded = _recorded_lock(fence)
        if recorded is None:
            raise DispatchLandingUnproven(
                "The dispatcher's lock identity was not recorded; landing cannot be ruled out."
            )
        lock = DispatchLock(Path(recorded.path))
        if not lock.try_acquire(create=False):
            raise DispatchLandingUnproven(str(lock.refusal))
        try:
            assert lock.identity is not None
            if (lock.identity.device, lock.identity.inode) != (recorded.device, recorded.inode):
                raise DispatchLandingUnproven(
                    "The dispatch lock file is not the one the dispatcher held; it was "
                    "deleted or replaced, so acquiring it proves nothing."
                )
            return self._settle(
                fence,
                expected=DispatchFenceState.CROSSING,
                resulting=DispatchFenceState.LOCK_RELEASED,
                proven_by=proven_by,
                reason=reason,
                proof="dispatcher_lock_inode_acquired",
            )
        finally:
            lock.release()

    def _settle(
        self,
        fence: dict[str, Any],
        *,
        expected: DispatchFenceState,
        resulting: DispatchFenceState,
        proven_by: str,
        reason: str,
        proof: str,
    ) -> DispatchLandingProof:
        now = self._now()
        token = _new_landing_token()
        timestamp_column = (
            "lock_released_at" if resulting is DispatchFenceState.LOCK_RELEASED else "revoked_at"
        )
        with self.ledger._transaction() as connection:
            updated = connection.execute(
                f"""
                update ari_execution_dispatch_fences
                set state = ?, {timestamp_column} = coalesce({timestamp_column}, ?),
                    terminal_by = coalesce(terminal_by, ?),
                    terminal_reason = coalesce(terminal_reason, ?),
                    landing_token = ?, landing_ruled_out_at = ?
                where fence_id = ? and state = ? and landing_token is null
                """,
                (resulting, now, proven_by, reason, token, now, fence["fence_id"], expected),
            )
            current = _decode_row(
                connection.execute(
                    "select * from ari_execution_dispatch_fences where fence_id = ?",
                    (fence["fence_id"],),
                ).fetchone()
            )
            if updated.rowcount != 1:
                if current["landing_token"] is not None:
                    return self._proof(current, DispatchFenceState(current["state"]), changed=False)
                raise DispatchLandingUnproven(
                    f"The dispatch fence moved to {current['state']} during the proof."
                )
            _insert_landing_event(
                connection,
                task_id=str(current["task_id"]),
                attempt_id=str(current["attempt_id"]),
                payload={
                    "fence_id": current["fence_id"],
                    "execution_id": current["execution_id"],
                    "action_id": current["action_id"],
                    "generation": current["generation"],
                    "previous_state": expected,
                    "state": resulting,
                    "effect_terminality": current["effect_terminality"],
                    "proven_by": proven_by,
                    "reason": reason,
                    "proof": proof,
                },
                now=now,
            )
            return self._proof(current, expected, changed=True)

    @staticmethod
    def _proof(
        fence: dict[str, Any],
        previous: DispatchFenceState,
        *,
        changed: bool,
    ) -> DispatchLandingProof:
        return DispatchLandingProof(
            fence_id=str(fence["fence_id"]),
            execution_id=str(fence["execution_id"]),
            task_id=str(fence["task_id"]),
            action_id=str(fence["action_id"]),
            previous_state=previous,
            state=DispatchFenceState(fence["state"]),
            terminality=_terminality(fence),
            landing_token=str(fence["landing_token"]),
            changed=changed,
        )

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("Dispatch fence clock must be timezone-aware.")
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_landing_token() -> str:
    return f"landing-{uuid4()}"


def _terminality(fence: dict[str, Any]) -> EffectTerminality:
    # Legacy fences carry no classification; nothing about their end is trusted.
    value = fence.get("effect_terminality")
    return EffectTerminality.UNBOUNDED if value is None else EffectTerminality(value)


def _recorded_lock(fence: dict[str, Any]) -> LockIdentity | None:
    if fence.get("lock_path") is None or fence.get("lock_inode") is None:
        return None
    return LockIdentity(
        str(fence["lock_path"]), int(fence["lock_device"]), int(fence["lock_inode"])
    )


def _insert_landing_event(
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
        ) values (?, ?, ?, ?, 'action.dispatch_landing_ruled_out', ?, ?, ?)
        """,
        (
            f"event-{uuid4()}",
            task_id,
            attempt_id,
            sequence,
            _json(sanitize_payload(payload)),
            _json({"authority": "ari", "operation": "dispatch_landing_proof"}),
            now,
        ),
    )
