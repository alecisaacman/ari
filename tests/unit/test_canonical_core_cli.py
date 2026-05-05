from __future__ import annotations

import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest


def _purge_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "ari_core" or module_name.startswith("ari_core."):
            sys.modules.pop(module_name, None)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_canonical_core_cli_self_doc_seed_from_commits_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ari@example.com")
    _git(repo, "config", "user.name", "ARI Test")
    (repo / "README.md").write_text("ARI\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "Initial ARI baseline")
    base_ref = _git(repo, "rev-parse", "HEAD")

    docs_dir = repo / "docs" / "skills"
    tests_dir = repo / "tests" / "unit"
    docs_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    (docs_dir / "self-documentation-skill.md").write_text(
        "Document content seed generation.\n",
        encoding="utf-8",
    )
    (tests_dir / "test_self_documentation_content_seed.py").write_text(
        "def test_seed():\n    assert True\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Generate self-documentation content seeds")
    head_ref = _git(repo, "rev-parse", "HEAD")

    before_files = {
        path.relative_to(repo)
        for path in repo.rglob("*")
        if ".git" not in path.relative_to(repo).parts
    }
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "self-doc",
                "seed",
                "from-commits",
                "--from",
                base_ref,
                "--to",
                head_ref,
                "--repo-root",
                str(repo),
                "--test-output",
                ".venv312/bin/python -m pytest tests/unit -q\n181 passed",
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 0
    seed = json.loads(output.getvalue())
    assert seed["seed_id"].startswith("content-seed-")
    assert seed["source_commit_range"] == f"{base_ref}..{head_ref}"
    assert seed["source_commits"] == [
        {
            "hash": head_ref,
            "subject": "Generate self-documentation content seeds",
        }
    ]
    assert "docs/skills/self-documentation-skill.md" in seed["source_files"]
    assert "tests/unit/test_self_documentation_content_seed.py" in seed["source_files"]
    assert seed["hook_options"]
    assert seed["demo_idea"]
    assert seed["claims_to_avoid"]
    after_files = {
        path.relative_to(repo)
        for path in repo.rglob("*")
        if ".git" not in path.relative_to(repo).parts
    }
    assert after_files == before_files


def test_canonical_core_cli_self_doc_seed_from_commits_invalid_range(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "self-doc",
                "seed",
                "from-commits",
                "--from",
                "missing-start",
                "--to",
                "missing-end",
                "--repo-root",
                str(repo),
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert "Unable to inspect git commits" in payload["error"]


def _content_seed_payload() -> dict[str, object]:
    return {
        "seed_id": "content-seed-cli-test",
        "source_commit_range": "abc123..def456",
        "source_commits": [
            {
                "hash": "def456789abc",
                "subject": "Generate self-documentation content seeds",
            }
        ],
        "source_files": [
            "services/ari-core/src/ari_core/modules/self_documentation/content_seed.py",
            "tests/unit/test_self_documentation_content_seed.py",
        ],
        "title": "ARI starts turning its own build history into content seeds",
        "one_sentence_summary": "This seed summarizes 1 commit touching 2 files.",
        "why_it_matters": "It keeps ARI content grounded in actual build evidence.",
        "proof_points": [
            "Commit def456789abc: Generate self-documentation content seeds",
            "Changed 2 file(s): content_seed.py and tests.",
        ],
        "demo_idea": "Show a commit range becoming a factual content seed.",
        "hook_options": ["ARI is learning to document itself without making things up."],
        "visual_moments": ["Show the commit range and generated seed JSON."],
        "suggested_voiceover": "ARI is turning real build evidence into content seeds.",
        "suggested_linkedin_post": "ARI is grounding self-documentation in commits.",
        "suggested_short_caption": "ARI self-doc, backed by commits.",
        "risk_notes": [],
        "redaction_notes": ["No sensitive-looking input was detected."],
        "claims_to_avoid": [
            "Do not claim this feature records, edits, exports, or publishes media."
        ],
        "next_content_angle": "Show package generation from a seed JSON file.",
        "created_at": "2026-05-05T00:00:00Z",
    }


def test_canonical_core_cli_self_doc_package_from_seed_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps(_content_seed_payload()), encoding="utf-8")
    before_paths = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "self-doc",
                "package",
                "from-seed-json",
                "--json-file",
                str(seed_file),
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 0
    package = json.loads(output.getvalue())
    assert package["package_id"].startswith("content-package-")
    assert package["source_seed_id"] == "content-seed-cli-test"
    assert package["shot_list"]
    assert package["terminal_demo_plan"]
    assert package["claims_to_avoid"] == [
        "Do not claim this feature records, edits, exports, or publishes media."
    ]
    after_paths = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after_paths == before_paths


def test_canonical_core_cli_self_doc_package_from_missing_seed_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "self-doc",
                "package",
                "from-seed-json",
                "--json-file",
                str(tmp_path / "missing.json"),
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert "Unable to read ContentSeed JSON file" in payload["error"]


def test_canonical_core_cli_self_doc_package_from_invalid_seed_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{not json", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "self-doc",
                "package",
                "from-seed-json",
                "--json-file",
                str(invalid_file),
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert "Invalid ContentSeed JSON" in payload["error"]


def test_canonical_core_cli_self_doc_package_from_incomplete_seed_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    incomplete_file = tmp_path / "incomplete.json"
    incomplete_file.write_text(json.dumps({"seed_id": "content-seed-bad"}), encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "self-doc",
                "package",
                "from-seed-json",
                "--json-file",
                str(incomplete_file),
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert "source_commits" in payload["error"]


def test_canonical_core_cli_skills_route_json(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "skills",
                "route",
                "--goal",
                "make a content seed from recent commits",
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 0
    route = json.loads(output.getvalue())
    assert route["status"] == "route_to_skill"
    assert route["recommended_skill_id"] == "ari.native.self_documentation"
    assert route["required_authority_boundary"]
    assert route["verification_expectation"]


def test_canonical_core_cli_skills_list_json(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            ["api", "skills", "list", "--json"],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 0
    skills = json.loads(output.getvalue())["skills"]
    skill_ids = {skill["skill_id"] for skill in skills}
    assert "ari.native.coding_loop" in skill_ids
    assert "ari.native.self_documentation" in skill_ids
    assert "ari.native.file_organization" in skill_ids
    assert "ari.native.document_processing" in skill_ids
    assert "ari.native.research_gathering" in skill_ids
    first_skill = skills[0]
    assert first_skill["name"]
    assert first_skill["capability_summary"]
    assert first_skill["authority_boundary"]
    assert first_skill["verification_expectation"]
    assert first_skill["memory_effect_expectation"]
    assert first_skill["inspection_surfaces"]
    assert first_skill["safety_constraints"]
    assert first_skill["docs_refs"]


def test_canonical_core_cli_skills_show_json(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "skills",
                "show",
                "--id",
                "ari.native.coding_loop",
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 0
    skill = json.loads(output.getvalue())["skill"]
    assert skill["skill_id"] == "ari.native.coding_loop"
    assert skill["authority_boundary"]
    assert skill["verification_expectation"]
    assert skill["memory_effect_expectation"]


def test_canonical_core_cli_skills_show_unknown_id_fails_safely(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "skills",
                "show",
                "--id",
                "ari.native.nope",
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert "Unknown skill id" in payload["error"]


def test_canonical_core_cli_skills_readiness_json(tmp_path: Path, monkeypatch) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "skills",
                "readiness",
                "--id",
                "ari.native.coding_loop",
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 0
    readiness = json.loads(output.getvalue())["readiness"]
    assert readiness["skill_id"] == "ari.native.coding_loop"
    assert readiness["status"] == "active"
    assert readiness["required_authority_boundary"]
    assert readiness["required_verification"]
    assert readiness["satisfied_gates"]


def test_canonical_core_cli_skills_readiness_unknown_id_fails_safely(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "api",
                "skills",
                "readiness",
                "--id",
                "ari.native.nope",
                "--json",
            ],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exit_code == 1
    payload = json.loads(output.getvalue())
    assert "Unknown skill id" in payload["error"]
    assert payload["readiness"]["status"] == "unknown_skill"


def test_canonical_core_cli_skills_route_missing_goal_fails_safely(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ari_home = tmp_path / "ari-home"
    monkeypatch.setenv("ARI_HOME", str(ari_home))
    _purge_modules()

    from ari_core.ari import main

    stderr = StringIO()
    with redirect_stderr(stderr), pytest.raises(SystemExit) as exc:
        main(
            ["api", "skills", "route", "--json"],
            db_path=ari_home / "modules" / "networking-crm" / "state" / "networking.db",
        )

    assert exc.value.code == 2
    assert "--goal" in stderr.getvalue()


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
                "coding-loops",
                "propose-next",
                "--id",
                second_retry_result.id,
            ],
            db_path=db_path,
        )
    assert exit_code == 0
    next_proposal = json.loads(propose_next_output.getvalue())["next_approval_proposal"]
    next_retry_approval = next_proposal["new_retry_approval"]
    assert next_retry_approval["approval_status"] == "pending"
    assert next_proposal["refreshed_chain"]["terminal_status"] == "pending_approval"
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
