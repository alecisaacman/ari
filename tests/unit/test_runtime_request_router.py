from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


def test_classify_request_routes_self_improvement_goals() -> None:
    from ari_core.runtime.request_router import classify_request

    decision = classify_request("improve ARI's autonomous coding loop safely")
    assert decision.route == "self_improve"


def test_classify_request_routes_repo_inspection_goals() -> None:
    from ari_core.runtime.request_router import classify_request

    decision = classify_request("inspect repo status and what changed")
    assert decision.route == "repo_inspect"


def test_route_request_dispatches_note_capture(tmp_path: Path) -> None:
    from ari_core.runtime.request_router import route_request

    db_path = tmp_path / "state" / "networking.db"
    routed = route_request("remember this design tradeoff for later", cwd=tmp_path, db_path=db_path)

    assert routed.route == "document_or_note_capture"
    assert routed.result["title"].startswith("remember this design tradeoff")


def test_route_goal_request_returns_unified_cli_contract(tmp_path: Path) -> None:
    from ari_core.runtime.request_router import route_goal_request
    response = route_goal_request("inspect repo status and what changed", cwd=tmp_path)

    payload = response.to_dict()
    assert payload["contractVersion"] == "ari.cli.v1"
    assert payload["identity"] == "ARI"
    assert payload["surface"] == "terminal"
    assert payload["route"] == "repo_inspect"
    assert payload["status"] in {"completed", "attention_needed"}
    assert "repo" in payload["summary"].lower()


def test_main_routes_direct_string_input_to_natural_language_surface(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            ["inspect", "repo", "status"],
            db_path=tmp_path / "state" / "networking.db",
        )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["contractVersion"] == "ari.cli.v1"
    assert payload["identity"] == "ARI"
    assert payload["route"] == "repo_inspect"
    assert payload["status"] in {"completed", "attention_needed"}
    assert "summary" in payload


def test_main_accepts_interactive_goal_input(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "plan the next safe ARI slice")

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main([], db_path=tmp_path / "state" / "networking.db")

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["contractVersion"] == "ari.cli.v1"
    assert payload["route"] == "plan_only"
    assert payload["status"] == "planned"
