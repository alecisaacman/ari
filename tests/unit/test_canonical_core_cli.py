from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "ari_core" or module_name.startswith("ari_core."):
            sys.modules.pop(module_name, None)


def test_canonical_core_cli_persists_notes_tasks_memory_and_project_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main
    from ari_core.modules.execution import (
        ModelPlanner,
        get_coding_loop_retry_approval,
        run_one_step_coding_loop,
        store_coding_loop_retry_approval,
    )

    db_path = ari_home / "modules" / "networking-crm" / "state" / "networking.db"

    memory_output = StringIO()
    with redirect_stdout(memory_output):
        exit_code = main(
            [
                "api",
                "memory",
                "remember",
                "--type",
                "priority",
                "--title",
                "Canonical focus",
                "--body",
                "Converge ARI into the canonical repo.",
                "--tags-json",
                json.dumps(["canon", "integration"]),
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_memory = json.loads(memory_output.getvalue())
    assert saved_memory["type"] == "priority"
    assert saved_memory["title"] == "Canonical focus"

    task_output = StringIO()
    with redirect_stdout(task_output):
        exit_code = main(
            [
                "api",
                "tasks",
                "create",
                "--title",
                "Finish canonical repo convergence",
                "--notes",
                "Route the hub through the canonical brain seams.",
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_task = json.loads(task_output.getvalue())
    assert saved_task["title"] == "Finish canonical repo convergence"
    assert saved_task["status"] == "open"

    note_output = StringIO()
    with redirect_stdout(note_output):
        exit_code = main(
            [
                "api",
                "notes",
                "save",
                "--title",
                "Canonical integration note",
                "--body",
                "ACE now points at ari-core inside services/ari-core.",
                "--json",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_note = json.loads(note_output.getvalue())
    assert saved_note["title"] == "Canonical integration note"

    project_payload = {
        "id": "project-canon",
        "title": "Canonical repo convergence",
        "goal": "Make ARI the single brain in the canonical repository.",
        "completion_criteria": "Core, API, and hub all resolve through canonical services.",
        "status": "active",
        "source": "integration",
        "created_at": "2026-04-15T01:30:00Z",
        "updated_at": "2026-04-15T01:30:00Z",
    }
    project_output = StringIO()
    with redirect_stdout(project_output):
        exit_code = main(
            [
                "api",
                "coordination",
                "put",
                "--entity",
                "project",
                "--payload-json",
                json.dumps(project_payload),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    saved_project = json.loads(project_output.getvalue())
    assert saved_project["id"] == "project-canon"
    assert saved_project["title"] == "Canonical repo convergence"

    awareness_output = StringIO()
    with redirect_stdout(awareness_output):
        exit_code = main(
            [
                "api",
                "policy",
                "awareness",
                "derive",
                "--payload-json",
                json.dumps(
                    {
                        "pendingApprovals": [],
                        "recentIntent": ["Integrate the real ARI system into the canonical repo."],
                        "recentDecisions": [],
                    }
                ),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    awareness = json.loads(awareness_output.getvalue())
    assert awareness["summary"]
    assert awareness["currentFocus"]

    execution_root = tmp_path / "execution-root"
    execution_root.mkdir()
    (execution_root / "README.md").write_text("canonical execution root\n", encoding="utf-8")
    goal_output = StringIO()
    with redirect_stdout(goal_output):
        exit_code = main(
            [
                "api",
                "execution",
                "goal",
                "--goal",
                "write file proof.txt with execution core ready",
                "--execution-root",
                str(execution_root),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    goal_result = json.loads(goal_output.getvalue())
    assert goal_result["status"] == "completed"
    assert goal_result["decisions"][0]["planner_name"] == "rule_based"
    assert (execution_root / "proof.txt").read_text(encoding="utf-8") == "execution core ready"

    plan_output = StringIO()
    with redirect_stdout(plan_output):
        exit_code = main(
            [
                "api",
                "execution",
                "plan",
                "--goal",
                "write file preview.txt with not yet",
                "--execution-root",
                str(execution_root),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    plan = json.loads(plan_output.getvalue())
    assert plan["status"] == "planned"
    assert plan["decision"]["planner_name"] == "rule_based"
    assert not (execution_root / "preview.txt").exists()

    plans_output = StringIO()
    with redirect_stdout(plans_output):
        exit_code = main(
            ["api", "execution", "plans", "list", "--limit", "3"],
            db_path=db_path,
        )
    assert exit_code == 0
    plans = json.loads(plans_output.getvalue())["plans"]
    assert plans[0]["id"] == plan["id"]

    plan_show_output = StringIO()
    with redirect_stdout(plan_show_output):
        exit_code = main(
            ["api", "execution", "plans", "show", "--id", plan["id"]],
            db_path=db_path,
        )
    assert exit_code == 0
    shown_plan = json.loads(plan_show_output.getvalue())["plan"]
    assert shown_plan["id"] == plan["id"]
    assert shown_plan["status"] == "planned"

    runs_output = StringIO()
    with redirect_stdout(runs_output):
        exit_code = main(
            [
                "api",
                "execution",
                "runs",
                "list",
                "--limit",
                "3",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    runs = json.loads(runs_output.getvalue())["runs"]
    assert runs[0]["id"] == goal_result["id"]
    assert runs[0]["planner_config"]["selected"] == "rule_based"

    run_output = StringIO()
    with redirect_stdout(run_output):
        exit_code = main(
            [
                "api",
                "execution",
                "runs",
                "show",
                "--id",
                goal_result["id"],
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    shown = json.loads(run_output.getvalue())["run"]
    assert shown["id"] == goal_result["id"]
    assert shown["results"][0]["verified"] is True

    tools_output = StringIO()
    with redirect_stdout(tools_output):
        exit_code = main(
            ["api", "execution", "tools"],
            db_path=db_path,
        )
    assert exit_code == 0
    tools = json.loads(tools_output.getvalue())
    assert "write_file" in tools["allowed_actions"]
    assert tools["tools"][0]["action_type"] == "read_file"

    context_output = StringIO()
    with redirect_stdout(context_output):
        exit_code = main(
            [
                "api",
                "execution",
                "context",
                "--execution-root",
                str(execution_root),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    context = json.loads(context_output.getvalue())["context"]
    assert context["repo_root"] == str(execution_root.resolve())
    assert "proof.txt" in context["files_sample"]
    assert context["language_summary"]["markdown"] == 1

    coding_loop_output = StringIO()
    with redirect_stdout(coding_loop_output):
        exit_code = main(
            [
                "api",
                "execution",
                "coding-loop",
                "--goal",
                "write file loop-proof.txt with inspected",
                "--execution-root",
                str(execution_root),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    coding_loop = json.loads(coding_loop_output.getvalue())["coding_loop"]
    assert coding_loop["status"] == "success"
    assert coding_loop["reason"]
    assert coding_loop["preview_id"]
    assert coding_loop["execution_run_id"]
    assert coding_loop["execution_occurred"] is True
    assert coding_loop["approval_required_reason"] is None
    assert coding_loop["retry_proposal"] is None
    assert coding_loop["retry_approval"] is None
    assert coding_loop["retry_approval_status"] is None
    assert (execution_root / "loop-proof.txt").read_text(encoding="utf-8") == "inspected"

    coding_loops_output = StringIO()
    with redirect_stdout(coding_loops_output):
        exit_code = main(
            ["api", "execution", "coding-loops", "list", "--limit", "3"],
            db_path=db_path,
        )
    assert exit_code == 0
    coding_loops = json.loads(coding_loops_output.getvalue())["coding_loops"]
    assert coding_loops[0]["id"] == coding_loop["id"]
    assert coding_loops[0]["execution_run_id"] == coding_loop["execution_run_id"]

    coding_loop_show_output = StringIO()
    with redirect_stdout(coding_loop_show_output):
        exit_code = main(
            ["api", "execution", "coding-loops", "show", "--id", coding_loop["id"]],
            db_path=db_path,
        )
    assert exit_code == 0
    shown_coding_loop = json.loads(coding_loop_show_output.getvalue())["coding_loop"]
    assert shown_coding_loop["id"] == coding_loop["id"]
    assert shown_coding_loop["status"] == "success"

    coding_loop_chain_output = StringIO()
    with redirect_stdout(coding_loop_chain_output):
        exit_code = main(
            ["api", "execution", "coding-loops", "chain", "--id", coding_loop["id"]],
            db_path=db_path,
        )
    assert exit_code == 0
    coding_loop_chain = json.loads(coding_loop_chain_output.getvalue())["chain"]
    assert coding_loop_chain["root_coding_loop_result_id"] == coding_loop["id"]
    assert coding_loop_chain["terminal_status"] == "stopped"
    assert coding_loop_chain["chain_depth"] == 0

    unsafe_loop_output = StringIO()
    with redirect_stdout(unsafe_loop_output):
        exit_code = main(
            [
                "api",
                "execution",
                "coding-loop",
                "--goal",
                "run rm -rf .",
                "--execution-root",
                str(execution_root),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    unsafe_loop = json.loads(unsafe_loop_output.getvalue())["coding_loop"]
    assert unsafe_loop["status"] == "unsafe"
    assert unsafe_loop["execution_run_id"] is None
    assert unsafe_loop["execution_occurred"] is False

    ask_user_loop_output = StringIO()
    with redirect_stdout(ask_user_loop_output):
        exit_code = main(
            [
                "api",
                "execution",
                "coding-loop",
                "--goal",
                "Invent a broad product strategy",
                "--execution-root",
                str(execution_root),
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    ask_user_loop = json.loads(ask_user_loop_output.getvalue())["coding_loop"]
    assert ask_user_loop["status"] == "ask_user"
    assert ask_user_loop["execution_run_id"] is None
    assert ask_user_loop["execution_occurred"] is False

    retry_result = run_one_step_coding_loop(
        "Create a proof file",
        execution_root=execution_root,
        db_path=db_path,
        planner=ModelPlanner(
            lambda payload: json.dumps(
                {
                    "confidence": 0.9,
                    "reason": "Write content that will fail explicit verification.",
                    "actions": [
                        {
                            "type": "write_file",
                            "path": "loop-proof.txt",
                            "content": "wrong",
                        }
                    ],
                    "verification": [
                        {
                            "type": "file_content",
                            "target": "loop-proof.txt",
                            "expected": "inspected",
                        }
                    ],
                }
            )
        ),
    )
    assert retry_result.retry_approval is not None
    retry_approval_id = retry_result.retry_approval.approval_id

    retry_approvals_output = StringIO()
    with redirect_stdout(retry_approvals_output):
        exit_code = main(
            ["api", "execution", "retry-approvals", "list", "--limit", "3"],
            db_path=db_path,
        )
    assert exit_code == 0
    retry_approvals = json.loads(retry_approvals_output.getvalue())["retry_approvals"]
    assert retry_approvals[0]["approval_id"] == retry_approval_id
    assert retry_approvals[0]["approval_status"] == "pending"

    retry_approval_show_output = StringIO()
    with redirect_stdout(retry_approval_show_output):
        exit_code = main(
            ["api", "execution", "retry-approvals", "show", "--id", retry_approval_id],
            db_path=db_path,
        )
    assert exit_code == 0
    shown_retry_approval = json.loads(retry_approval_show_output.getvalue())["retry_approval"]
    assert shown_retry_approval["source_execution_run_id"] == retry_result.execution_run_id
    assert shown_retry_approval["proposed_retry_goal"] == "write file loop-proof.txt with inspected"

    retry_approval_approve_output = StringIO()
    with redirect_stdout(retry_approval_approve_output):
        exit_code = main(
            [
                "api",
                "execution",
                "retry-approvals",
                "approve",
                "--id",
                retry_approval_id,
                "--approved-by",
                "alec",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    approved_retry_approval = json.loads(
        retry_approval_approve_output.getvalue()
    )["retry_approval"]
    assert approved_retry_approval["approval_status"] == "approved"
    assert approved_retry_approval["approval"]["approved_by"] == "alec"
    assert (execution_root / "loop-proof.txt").read_text(encoding="utf-8") == "wrong"

    retry_approval_execute_output = StringIO()
    with redirect_stdout(retry_approval_execute_output):
        exit_code = main(
            [
                "api",
                "execution",
                "retry-approvals",
                "execute",
                "--id",
                retry_approval_id,
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    executed_retry_approval = json.loads(retry_approval_execute_output.getvalue())
    assert (
        executed_retry_approval["retry_approval"]["retry_execution_status"]
        == "completed"
    )
    assert executed_retry_approval["execution_run"]["status"] == "completed"
    assert (execution_root / "loop-proof.txt").read_text(encoding="utf-8") == "inspected"

    retry_approval_review_output = StringIO()
    with redirect_stdout(retry_approval_review_output):
        exit_code = main(
            [
                "api",
                "execution",
                "retry-approvals",
                "review",
                "--id",
                retry_approval_id,
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    retry_review_payload = json.loads(retry_approval_review_output.getvalue())
    retry_review = retry_review_payload["review"]
    assert retry_review["status"] == "stop"
    assert retry_review["retry_execution_status"] == "completed"
    assert retry_review["approval_required"] is False
    assert retry_review_payload["continuation"]["eligible"] is False
    assert retry_review_payload["continuation"]["status"] == "stop"

    (execution_root / "loop-second-proof.txt").write_text("old", encoding="utf-8")
    second_retry_result = run_one_step_coding_loop(
        "Create a second proof file",
        execution_root=execution_root,
        db_path=db_path,
        planner=ModelPlanner(
            lambda payload: json.dumps(
                {
                    "confidence": 0.9,
                    "reason": "Write content that will fail explicit verification.",
                    "actions": [
                        {
                            "type": "write_file",
                            "path": "loop-second-proof.txt",
                            "content": "wrong",
                        }
                    ],
                    "verification": [
                        {
                            "type": "file_content",
                            "target": "loop-second-proof.txt",
                            "expected": "inspected twice",
                        }
                    ],
                }
            )
        ),
    )
    assert second_retry_result.retry_approval is not None
    second_approval = get_coding_loop_retry_approval(
        second_retry_result.retry_approval.approval_id,
        db_path=db_path,
    )
    assert second_approval is not None
    store_coding_loop_retry_approval(
        replace(
            second_approval,
            retry_execution_run_id=second_retry_result.execution_run_id,
            retry_execution_status="exhausted",
            retry_execution_reason=(
                "Retryable execution failed until max_cycles was exhausted."
            ),
            executed_at="2026-05-04T14:10:00Z",
        ),
        db_path=db_path,
    )
    propose_next_output = StringIO()
    with redirect_stdout(propose_next_output):
        exit_code = main(
            [
                "api",
                "execution",
                "retry-approvals",
                "propose-next",
                "--id",
                second_retry_result.retry_approval.approval_id,
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    next_retry_approval = json.loads(propose_next_output.getvalue())["retry_approval"]
    assert next_retry_approval["approval_status"] == "pending"
    assert (
        next_retry_approval["prior_retry_approval_id"]
        == second_retry_result.retry_approval.approval_id
    )
    assert next_retry_approval["prior_retry_execution_run_id"] == (
        second_retry_result.execution_run_id
    )

    shown_second_result_output = StringIO()
    with redirect_stdout(shown_second_result_output):
        exit_code = main(
            [
                "api",
                "execution",
                "coding-loops",
                "show",
                "--id",
                second_retry_result.id,
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    shown_second_result = json.loads(shown_second_result_output.getvalue())["coding_loop"]
    assert shown_second_result["next_retry_approval_id"] == (
        next_retry_approval["approval_id"]
    )
    assert shown_second_result["post_run_review"]["status"] == "propose_retry"

    second_chain_output = StringIO()
    with redirect_stdout(second_chain_output):
        exit_code = main(
            [
                "api",
                "execution",
                "coding-loops",
                "chain",
                "--id",
                second_retry_result.id,
                "--max-depth",
                "5",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    second_chain = json.loads(second_chain_output.getvalue())["chain"]
    assert second_chain["terminal_status"] == "pending_approval"
    assert second_chain["chain_depth"] == 2
    assert second_chain["retry_approvals"][0]["continuation"]["status"] == (
        "duplicate_exists"
    )
    assert second_chain["retry_approvals"][1]["approval_id"] == (
        next_retry_approval["approval_id"]
    )

    approve_next_output = StringIO()
    with redirect_stdout(approve_next_output):
        exit_code = main(
            [
                "api",
                "execution",
                "coding-loops",
                "approve-latest",
                "--id",
                second_retry_result.id,
                "--approved-by",
                "alec",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    approve_latest = json.loads(approve_next_output.getvalue())["approval_mutation"]
    assert approve_latest["updated_retry_approval"]["approval_id"] == (
        next_retry_approval["approval_id"]
    )
    assert approve_latest["refreshed_chain"]["terminal_status"] == (
        "executable_approved_retry_available"
    )

    advance_chain_output = StringIO()
    with redirect_stdout(advance_chain_output):
        exit_code = main(
            [
                "api",
                "execution",
                "coding-loops",
                "advance",
                "--id",
                second_retry_result.id,
                "--max-depth",
                "5",
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    advancement = json.loads(advance_chain_output.getvalue())["advancement"]
    assert advancement["prior_terminal_status"] == (
        "executable_approved_retry_available"
    )
    assert advancement["action_taken"] == "executed_approved_retry"
    assert advancement["executed_retry_approval_id"] == next_retry_approval["approval_id"]
    assert advancement["retry_execution_run_id"]
    assert advancement["refreshed_terminal_status"] == "stopped"
    assert (execution_root / "loop-second-proof.txt").read_text(
        encoding="utf-8"
    ) == "inspected twice"
    assert db_path.exists()


def test_canonical_core_cli_execution_help_stays_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARI_HOME", str(tmp_path / "ari-home"))
    _purge_modules()

    from ari_core.ari import main

    help_output = StringIO()
    with redirect_stdout(help_output):
        exit_code = main(["execution", "help"])

    assert exit_code == 0
    rendered = help_output.getvalue()
    assert "execution coding-loop" in rendered
    assert "Help commands do not invoke Codex" in rendered
    assert "Help commands do not invoke OpenAI" in rendered
