from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ari_core.core.paths import DB_PATH
from ari_core.modules.execution.inspection import (
    inspect_coding_loop_chain,
    list_coding_loop_results,
)


@dataclass(frozen=True, slots=True)
class CodingLoopChainSummary:
    coding_loop_result_id: str
    original_goal: str
    initial_status: str
    terminal_status: str
    chain_depth: int
    approval_count: int
    retry_execution_count: int
    latest_approval_status: str | None
    latest_retry_execution_status: str | None
    latest_review_decision: str | None
    continuation_decision: str | None
    stop_reason: str | None
    created_at: str
    updated_at: str | None
    inspection_hint: str


@dataclass(frozen=True, slots=True)
class CodingLoopChainsReadModel:
    generated_at: str
    total_recent_count: int
    chains: tuple[CodingLoopChainSummary, ...]
    unavailable_reason: str | None
    source_of_truth: str
    authority_warning: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_coding_loop_chains_read_model(
    *,
    db_path: Path = DB_PATH,
    limit: int = 10,
    max_depth: int = 10,
) -> CodingLoopChainsReadModel:
    source_of_truth = "durable coding-loop results and canonical chain inspection"
    authority_warning = (
        "This read model is inspection-only. ACE may display coding-loop chains but "
        "must not approve, reject, execute, advance chains, mutate memory, or own chain state."
    )
    try:
        results = list_coding_loop_results(limit=limit, db_path=db_path)
        chains = tuple(
            _summarize_chain(chain)
            for result in results
            if (chain := inspect_coding_loop_chain(
                str(result.get("id") or ""),
                max_depth=max_depth,
                db_path=db_path,
            ))
            is not None
        )
    except Exception as error:  # pragma: no cover - exercised through tests via monkeypatch.
        return CodingLoopChainsReadModel(
            generated_at=_now_iso(),
            total_recent_count=0,
            chains=(),
            unavailable_reason=(
                f"Coding-loop chains are unavailable: {type(error).__name__}: {error}"
            ),
            source_of_truth=source_of_truth,
            authority_warning=authority_warning,
        )

    return CodingLoopChainsReadModel(
        generated_at=_now_iso(),
        total_recent_count=len(chains),
        chains=chains,
        unavailable_reason=None,
        source_of_truth=source_of_truth,
        authority_warning=authority_warning,
    )


def _summarize_chain(chain: dict[str, Any]) -> CodingLoopChainSummary:
    approvals = _dict_list(chain.get("retry_approvals"))
    latest = approvals[-1] if approvals else None
    review = _nested_dict(latest, "post_run_review")
    continuation = _nested_dict(latest, "continuation")
    result_id = str(chain.get("root_coding_loop_result_id") or "")
    return CodingLoopChainSummary(
        coding_loop_result_id=result_id,
        original_goal=str(chain.get("original_goal") or ""),
        initial_status=str(chain.get("initial_status") or ""),
        terminal_status=str(chain.get("terminal_status") or "unknown/incomplete"),
        chain_depth=_int_value(chain.get("chain_depth"), len(approvals)),
        approval_count=len(approvals),
        retry_execution_count=sum(
            1 for approval in approvals if approval.get("retry_execution_run_id") is not None
        ),
        latest_approval_status=_string_or_none(
            None if latest is None else latest.get("approval_status")
        ),
        latest_retry_execution_status=_string_or_none(
            None if latest is None else latest.get("retry_execution_status")
        ),
        latest_review_decision=_string_or_none(None if review is None else review.get("status")),
        continuation_decision=_string_or_none(
            None if continuation is None else continuation.get("status")
        ),
        stop_reason=_stop_reason(chain, latest, review, continuation),
        created_at=str(chain.get("created_at") or ""),
        updated_at=_string_or_none(chain.get("updated_at")),
        inspection_hint=f"api execution coding-loops chain --id {result_id}",
    )


def _stop_reason(
    chain: dict[str, Any],
    latest: dict[str, Any] | None,
    review: dict[str, Any] | None,
    continuation: dict[str, Any] | None,
) -> str | None:
    if continuation is not None:
        reason = _string_or_none(continuation.get("reason"))
        if reason:
            return reason
    if review is not None:
        reason = _string_or_none(review.get("reason"))
        if reason:
            return reason
    if latest is not None:
        reason = _string_or_none(latest.get("retry_execution_reason"))
        if reason:
            return reason
    return _string_or_none(chain.get("initial_reason"))


def _nested_dict(payload: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if payload is None:
        return None
    value = payload.get(key)
    return value if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int_value(value: object, fallback: int) -> int:
    return value if isinstance(value, int) else fallback


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
