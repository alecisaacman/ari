import json
from pathlib import Path

from ...core.paths import DB_PATH
from .controller import build_repo_context, plan_execution_goal, run_execution_goal
from .engine import (
    approve_operator_action,
    create_operator_action,
    execute_command,
    get_execution_snapshot,
    get_operator_action,
    patch_file,
    read_file,
    run_operator_action,
    write_file,
)
from .inspection import get_execution_run, list_execution_runs
from .models import ExecutionGoal
from .tools import get_execution_tool_registry


def handle_api_execution_command(args, db_path: Path = DB_PATH) -> int:
    print(
        json.dumps(
            execute_command(
                args.command,
                cwd=args.cwd,
                timeout_seconds=args.timeout_seconds,
            )
        )
    )
    return 0


def handle_api_execution_read_file(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps(read_file(args.path)))
    return 0


def handle_api_execution_write_file(args, db_path: Path = DB_PATH) -> int:
    print(
        json.dumps(
            write_file(
                args.path,
                args.content,
                action_id=args.action_id,
                db_path=db_path,
            )
        )
    )
    return 0


def handle_api_execution_patch_file(args, db_path: Path = DB_PATH) -> int:
    print(
        json.dumps(
            patch_file(
                args.path,
                find_text=args.find,
                replace_text=args.replace,
                action_id=args.action_id,
                db_path=db_path,
            )
        )
    )
    return 0


def handle_api_execution_goal(args, db_path: Path = DB_PATH) -> int:
    result = run_execution_goal(
        ExecutionGoal(
            objective=args.goal,
            max_cycles=args.max_cycles,
        ),
        execution_root=args.execution_root,
        db_path=db_path,
        planner_mode=args.planner,
    )
    print(json.dumps(result.to_dict()))
    return 0


def handle_api_execution_plan(args, db_path: Path = DB_PATH) -> int:
    result = plan_execution_goal(
        ExecutionGoal(
            objective=args.goal,
            max_cycles=args.max_cycles,
        ),
        execution_root=args.execution_root,
        db_path=db_path,
        planner_mode=args.planner,
    )
    print(json.dumps(result))
    return 0


def handle_api_execution_tools(args, db_path: Path = DB_PATH) -> int:
    del args, db_path
    print(json.dumps(get_execution_tool_registry().prompt_payload()))
    return 0


def handle_api_execution_context(args, db_path: Path = DB_PATH) -> int:
    del db_path
    print(json.dumps({"context": build_repo_context(args.execution_root).to_dict()}))
    return 0


def handle_api_execution_runs_list(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps({"runs": list_execution_runs(limit=args.limit, db_path=db_path)}))
    return 0


def handle_api_execution_runs_show(args, db_path: Path = DB_PATH) -> int:
    run = get_execution_run(args.id, db_path=db_path)
    if run is None:
        print(json.dumps({"error": f"Execution run {args.id} not found."}))
        return 1
    print(json.dumps({"run": run}))
    return 0


def handle_api_execution_action_create(args, db_path: Path = DB_PATH) -> int:
    operations = json.loads(args.operations_json)
    if not isinstance(operations, list):
        raise ValueError("operations_json must decode to a list.")
    approval_required = (
        None if args.approval_required == "auto" else args.approval_required == "true"
    )
    print(
        json.dumps(
            create_operator_action(
                title=args.title,
                summary=args.summary,
                operations=operations,
                verify_command=args.verify_command or "",
                working_directory=args.working_directory or ".",
                approval_required=approval_required,
                db_path=db_path,
            )
        )
    )
    return 0


def handle_api_execution_action_get(args, db_path: Path = DB_PATH) -> int:
    action = get_operator_action(args.id, db_path=db_path)
    print(json.dumps({"action": action}))
    return 0


def handle_api_execution_action_list(args, db_path: Path = DB_PATH) -> int:
    from .engine import get_execution_snapshot

    snapshot = get_execution_snapshot(limit=args.limit, db_path=db_path)
    print(json.dumps({"actions": snapshot["recent_actions"]}))
    return 0


def handle_api_execution_action_approve(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps({"action": approve_operator_action(args.id, db_path=db_path)}))
    return 0


def handle_api_execution_action_run(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps(run_operator_action(args.id, db_path=db_path)))
    return 0


def handle_api_execution_snapshot(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps(get_execution_snapshot(limit=args.limit, db_path=db_path)))
    return 0
