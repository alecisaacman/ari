import json
from pathlib import Path

from ...core.paths import DB_PATH
from .coding_loop import (
    approve_stored_coding_loop_retry_approval,
    get_coding_loop_retry_approval,
    list_coding_loop_retry_approvals,
    reject_stored_coding_loop_retry_approval,
    run_one_step_coding_loop,
)
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
from .inspection import (
    get_execution_plan_preview,
    get_execution_run,
    inspect_coding_loop_result,
    inspect_coding_loop_retry_approval,
    list_execution_plan_previews,
    list_execution_runs,
)
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


def handle_api_execution_coding_loop(args, db_path: Path = DB_PATH) -> int:
    result = run_one_step_coding_loop(
        args.goal,
        execution_root=args.execution_root,
        db_path=db_path,
        planner_mode=args.planner,
    )
    print(json.dumps({"coding_loop": inspect_coding_loop_result(result)}))
    return 0


def handle_api_execution_retry_approvals_list(args, db_path: Path = DB_PATH) -> int:
    approvals = [
        inspect_coding_loop_retry_approval(approval)
        for approval in list_coding_loop_retry_approvals(limit=args.limit, db_path=db_path)
    ]
    print(json.dumps({"retry_approvals": approvals}))
    return 0


def handle_api_execution_retry_approvals_show(args, db_path: Path = DB_PATH) -> int:
    approval = get_coding_loop_retry_approval(args.id, db_path=db_path)
    if approval is None:
        print(json.dumps({"error": f"Coding-loop retry approval {args.id} not found."}))
        return 1
    print(json.dumps({"retry_approval": inspect_coding_loop_retry_approval(approval)}))
    return 0


def handle_api_execution_retry_approvals_approve(args, db_path: Path = DB_PATH) -> int:
    try:
        approval = approve_stored_coding_loop_retry_approval(
            args.id,
            approved_by=args.approved_by,
            db_path=db_path,
        )
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    print(json.dumps({"retry_approval": inspect_coding_loop_retry_approval(approval)}))
    return 0


def handle_api_execution_retry_approvals_reject(args, db_path: Path = DB_PATH) -> int:
    try:
        approval = reject_stored_coding_loop_retry_approval(
            args.id,
            rejected_reason=args.reason,
            rejected_by=args.rejected_by,
            db_path=db_path,
        )
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    print(json.dumps({"retry_approval": inspect_coding_loop_retry_approval(approval)}))
    return 0


def handle_api_execution_plans_list(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps({"plans": list_execution_plan_previews(limit=args.limit, db_path=db_path)}))
    return 0


def handle_api_execution_plans_show(args, db_path: Path = DB_PATH) -> int:
    preview = get_execution_plan_preview(args.id, db_path=db_path)
    if preview is None:
        print(json.dumps({"error": f"Execution plan preview {args.id} not found."}))
        return 1
    print(json.dumps({"plan": preview}))
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
