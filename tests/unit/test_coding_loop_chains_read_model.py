from __future__ import annotations

import importlib
import json


def test_coding_loop_chains_read_model_is_json_serializable(monkeypatch) -> None:
    module = _chains_module()
    monkeypatch.setattr(module, "list_coding_loop_results", _list_results)
    monkeypatch.setattr(module, "inspect_coding_loop_chain", _inspect_chain)

    model = module.get_coding_loop_chains_read_model()

    payload = model.to_dict()
    assert payload["total_recent_count"] == 1
    assert json.loads(json.dumps(payload))["chains"][0]["coding_loop_result_id"] == (
        "coding-loop-result-1"
    )


def test_coding_loop_chains_read_model_includes_chain_summaries(monkeypatch) -> None:
    module = _chains_module()
    monkeypatch.setattr(module, "list_coding_loop_results", _list_results)
    monkeypatch.setattr(module, "inspect_coding_loop_chain", _inspect_chain)

    payload = module.get_coding_loop_chains_read_model().to_dict()

    assert payload["total_recent_count"] == 1
    chain = payload["chains"][0]
    assert chain["coding_loop_result_id"] == "coding-loop-result-1"
    assert chain["original_goal"] == "Fix proof"
    assert chain["initial_status"] == "retryable_failure"
    assert chain["terminal_status"] == "pending_approval"
    assert chain["chain_depth"] == 1
    assert chain["approval_count"] == 1
    assert chain["retry_execution_count"] == 0
    assert chain["latest_approval_status"] == "pending"
    assert chain["latest_retry_execution_status"] is None
    assert chain["latest_review_decision"] == "not_executed"
    assert chain["continuation_decision"] == "not_executed"
    assert chain["stop_reason"] == "Retry has not executed."
    assert chain["inspection_hint"] == (
        "api execution coding-loops chain --id coding-loop-result-1"
    )


def test_coding_loop_chains_read_model_represents_unavailable_source(monkeypatch) -> None:
    module = _chains_module()

    def raise_unavailable(*, limit, db_path):
        raise RuntimeError("chain store offline")

    monkeypatch.setattr(module, "list_coding_loop_results", raise_unavailable)

    payload = module.get_coding_loop_chains_read_model().to_dict()

    assert payload["total_recent_count"] == 0
    assert payload["chains"] == ()
    assert "RuntimeError: chain store offline" in payload["unavailable_reason"]
    assert payload["source_of_truth"] == (
        "durable coding-loop results and canonical chain inspection"
    )


def test_coding_loop_chains_read_model_is_read_only(monkeypatch) -> None:
    module = _chains_module()
    calls: list[str] = []

    def list_only(*, limit, db_path):
        calls.append("list")
        return _list_results(limit=limit, db_path=db_path)

    def inspect_only(result_id, *, max_depth, db_path):
        calls.append(f"inspect:{result_id}")
        return _inspect_chain(result_id, max_depth=max_depth, db_path=db_path)

    monkeypatch.setattr(module, "list_coding_loop_results", list_only)
    monkeypatch.setattr(module, "inspect_coding_loop_chain", inspect_only)

    payload = module.get_coding_loop_chains_read_model().to_dict()

    assert calls == ["list", "inspect:coding-loop-result-1"]
    assert "inspection-only" in payload["authority_warning"]
    assert "must not approve, reject, execute, advance chains" in (
        payload["authority_warning"]
    )


def _chains_module():
    return importlib.import_module("ari_core.modules.overview.coding_loop_chains")


def _list_results(*, limit, db_path):
    return [{"id": "coding-loop-result-1"}]


def _inspect_chain(result_id, *, max_depth, db_path):
    assert result_id == "coding-loop-result-1"
    return {
        "root_coding_loop_result_id": "coding-loop-result-1",
        "original_goal": "Fix proof",
        "initial_status": "retryable_failure",
        "initial_reason": "Verification failed.",
        "initial_execution_run_id": "execution-run-1",
        "retry_approvals": [
            {
                "approval_id": "approval-1",
                "approval_status": "pending",
                "retry_execution_run_id": None,
                "retry_execution_status": None,
                "post_run_review": {
                    "status": "not_executed",
                    "reason": "Retry has not executed.",
                },
                "continuation": {
                    "status": "not_executed",
                    "reason": "Retry has not executed.",
                },
                "created_at": "2026-05-06T00:00:00Z",
            }
        ],
        "terminal_status": "pending_approval",
        "chain_depth": 1,
        "created_at": "2026-05-06T00:00:00Z",
        "updated_at": "2026-05-06T00:01:00Z",
    }
