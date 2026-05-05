# ruff: noqa: E501
import argparse
import json
import sys
from pathlib import Path

from .core.paths import DB_PATH
from .modules.coordination.api import (
    handle_api_coordination_get,
    handle_api_coordination_list,
    handle_api_coordination_put,
)
from .modules.execution.api import (
    handle_api_execution_action_approve,
    handle_api_execution_action_create,
    handle_api_execution_action_get,
    handle_api_execution_action_list,
    handle_api_execution_action_run,
    handle_api_execution_coding_loop,
    handle_api_execution_coding_loops_advance,
    handle_api_execution_coding_loops_approve_latest,
    handle_api_execution_coding_loops_chain,
    handle_api_execution_coding_loops_list,
    handle_api_execution_coding_loops_propose_next,
    handle_api_execution_coding_loops_reject_latest,
    handle_api_execution_coding_loops_show,
    handle_api_execution_command,
    handle_api_execution_context,
    handle_api_execution_goal,
    handle_api_execution_patch_file,
    handle_api_execution_plan,
    handle_api_execution_plans_list,
    handle_api_execution_plans_show,
    handle_api_execution_read_file,
    handle_api_execution_retry_approvals_approve,
    handle_api_execution_retry_approvals_execute,
    handle_api_execution_retry_approvals_list,
    handle_api_execution_retry_approvals_propose_next,
    handle_api_execution_retry_approvals_reject,
    handle_api_execution_retry_approvals_review,
    handle_api_execution_retry_approvals_show,
    handle_api_execution_runs_list,
    handle_api_execution_runs_show,
    handle_api_execution_snapshot,
    handle_api_execution_tools,
    handle_api_execution_write_file,
)
from .modules.execution.executor import execute_action
from .modules.memory.api import (
    handle_api_memory_block_create,
    handle_api_memory_block_get,
    handle_api_memory_block_list,
    handle_api_memory_block_search,
    handle_api_memory_capture_coding_loop_chain,
    handle_api_memory_capture_execution,
    handle_api_memory_capture_retry_approval,
    handle_api_memory_context,
    handle_api_memory_explain_coding_loop_chain,
    handle_api_memory_explain_execution,
    handle_api_memory_explain_retry_approval,
    handle_api_memory_get,
    handle_api_memory_list,
    handle_api_memory_remember,
    handle_api_memory_search,
    handle_api_memory_self_model_ensure,
    handle_api_memory_self_model_show,
)
from .modules.networking.cli import (
    handle_add_contact,
    handle_add_followup,
    handle_add_note,
    handle_complete_followup,
    handle_due,
    handle_init_db,
    handle_list_contacts,
    handle_list_followups,
    handle_show_contact,
    handle_status,
    handle_today,
)
from .modules.notes.api import handle_api_notes_save, handle_api_notes_search
from .modules.overview import get_ari_operating_overview
from .modules.policy.api import (
    handle_api_policy_awareness_derive,
    handle_api_policy_awareness_latest,
    handle_api_policy_awareness_store,
    handle_api_policy_improvement_detect,
    handle_api_policy_improvement_focus,
    handle_api_policy_orchestration_classify,
    handle_api_policy_project_draft,
    handle_api_policy_project_focus,
)
from .modules.self_documentation import (
    content_seed_from_dict,
    generate_content_package_from_seed,
    generate_content_seed_from_commits,
)
from .modules.skills import (
    evaluate_skill_readiness,
    get_skill_manifest,
    list_skill_manifests,
    propose_missing_skill,
    route_goal_to_skill,
)
from .modules.tasks.api import (
    handle_api_tasks_create,
    handle_api_tasks_get,
    handle_api_tasks_list,
    handle_api_tasks_search,
)
from .runtime.loop_runner import handle_runtime_codex_loop
from .runtime.request_router import handle_natural_language_request
from .runtime.scenario_harness import handle_runtime_playground_run, handle_runtime_smoke_test
from .runtime.self_improvement_runner import handle_runtime_self_improve
from .suits.documentation.clip import handle_clip_build
from .suits.documentation.content import handle_content_linkedin, handle_script_short_video
from .suits.documentation.demo import handle_demo_record, handle_demo_terminal, handle_session_build
from .suits.documentation.frame import handle_frame_build
from .suits.documentation.record import handle_record_plan
from .suits.documentation.storyboard import handle_storyboard_short_video
from .suits.documentation.video import handle_video_build

HELP_TOKENS = {"--help", "-h", "help"}


def _is_local_help_request(args: list[str]) -> bool:
    """Return true when the CLI input should be handled locally.

    Help/introspection requests must never route into Codex, OpenAI, or worker loops.
    """
    if not args:
        return False

    return any(arg in HELP_TOKENS for arg in args)


def _local_help_text(args: list[str]) -> str:
    """Return stable local help text for ARI CLI surfaces."""
    joined = " ".join(args)

    if joined.startswith("execution"):
        return """ARI CLI — execution help

Local execution inspection commands:

  execution context
      Inspect repo/context inputs used for planning.

  execution plans
      List or inspect persisted execution plan previews.

  execution plans show <preview_id>
      Show one persisted execution plan preview.

  execution coding-loop
      Run one approval-aware coding-loop step and inspect the result.

  execution retry-approvals
      Inspect or mutate durable coding-loop retry approval artifacts.

Notes:
  - Help commands are handled locally.
  - Help commands do not invoke Codex.
  - Help commands do not invoke OpenAI.
  - Help commands do not create worker runs.
  - Natural-language goals are still supported outside help mode.
"""

    return """ARI CLI — local help

Available command categories:

  execution
      Inspect execution context and plan previews.

  memory
      Inspect memory context if available.

  help, --help, -h
      Show local help without invoking workers.

Examples:

  python -m ari_core.ari --help
  python -m ari_core.ari execution help
  python -m ari_core.ari execution context
  python -m ari_core.ari execution plans

Notes:
  - ARI also accepts natural-language goals.
  - Help/introspection commands are local only.
  - Help does not invoke Codex, OpenAI, or external APIs.
"""

LEGACY_NETWORKING_TOP_LEVEL = {"today", "contacts", "followups"}
LEGACY_DOCUMENTATION_TOP_LEVEL = {
    "content",
    "script",
    "demo",
    "video",
    "clip",
    "frame",
    "storyboard",
    "record",
    "session",
}
TOP_LEVEL_COMMANDS = {
    "networking",
    "docs",
    "api",
    "runtime",
    *LEGACY_NETWORKING_TOP_LEVEL,
    *LEGACY_DOCUMENTATION_TOP_LEVEL,
}


def _handle_api_self_doc_seed_from_commits(args: argparse.Namespace) -> int:
    try:
        seed = generate_content_seed_from_commits(
            from_ref=args.from_ref,
            to_ref=args.to_ref,
            repo_root=Path(args.repo_root),
            test_output=args.test_output,
            user_framing=args.user_framing,
        )
    except ValueError as exc:
        if args.as_json:
            print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"Unable to generate content seed: {exc}", file=sys.stderr)
        return 1

    payload = seed.to_dict()
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Content seed: {payload['title']}")
    print(f"Seed id: {payload['seed_id']}")
    print(f"Source range: {payload['source_commit_range']}")
    print(f"Commits: {len(payload['source_commits'])}")
    print(f"Files: {len(payload['source_files'])}")
    print(f"Demo idea: {payload['demo_idea']}")
    if payload["risk_notes"]:
        print("Risk notes:")
        for note in payload["risk_notes"]:
            print(f"- {note}")
    return 0


def _handle_api_self_doc_package_from_seed_json(args: argparse.Namespace) -> int:
    seed_path = Path(args.json_file)
    try:
        raw_payload = json.loads(seed_path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            raise ValueError("ContentSeed JSON must be an object.")
        seed = content_seed_from_dict(raw_payload)
        package = generate_content_package_from_seed(seed)
    except OSError as exc:
        return _print_self_doc_package_error(f"Unable to read ContentSeed JSON file: {exc}", args)
    except json.JSONDecodeError as exc:
        return _print_self_doc_package_error(f"Invalid ContentSeed JSON: {exc}", args)
    except ValueError as exc:
        return _print_self_doc_package_error(str(exc), args)

    payload = package.to_dict()
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Content package: {payload['title']}")
    print(f"Package id: {payload['package_id']}")
    print(f"Source seed id: {payload['source_seed_id']}")
    print(f"Content angle: {payload['content_angle']}")
    print(f"Shots: {len(payload['shot_list'])}")
    print(f"Terminal demo steps: {len(payload['terminal_demo_plan'])}")
    print("Approval required before recording: yes")
    print("Approval required before posting: yes")
    return 0


def _print_self_doc_package_error(message: str, args: argparse.Namespace) -> int:
    if args.as_json:
        print(json.dumps({"error": message}, indent=2, sort_keys=True))
    else:
        print(f"Unable to generate content package: {message}", file=sys.stderr)
    return 1


def _handle_api_skills_route(args: argparse.Namespace) -> int:
    recommendation = route_goal_to_skill(args.goal)
    payload = recommendation.to_dict()
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Skill route: {payload['status']}")
    print(f"Route id: {payload['route_id']}")
    print(f"Goal: {payload['goal']}")
    if payload["recommended_skill_id"]:
        print(f"Recommended skill: {payload['recommended_skill_id']}")
    if payload["missing_skill_candidate_id"]:
        print(f"Missing skill candidate: {payload['missing_skill_candidate_id']}")
    if payload["clarification_question"]:
        print(f"Clarification: {payload['clarification_question']}")
    print(f"Reason: {payload['reason']}")
    return 0


def _handle_api_skills_list(args: argparse.Namespace) -> int:
    payload = {"skills": [manifest.to_dict() for manifest in list_skill_manifests()]}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    for manifest in payload["skills"]:
        print(
            f"{manifest['skill_id']} | {manifest['lifecycle_status']} | "
            f"{manifest['implementation_status']}"
        )
    return 0


def _handle_api_skills_show(args: argparse.Namespace) -> int:
    manifest = get_skill_manifest(args.skill_id)
    if manifest is None:
        message = f"Unknown skill id: {args.skill_id}"
        if args.as_json:
            print(json.dumps({"error": message}, indent=2, sort_keys=True))
        else:
            print(message, file=sys.stderr)
        return 1

    payload = {"skill": manifest.to_dict()}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    skill = payload["skill"]
    print(f"Skill: {skill['skill_id']}")
    print(f"Name: {skill['name']}")
    print(f"Lifecycle: {skill['lifecycle_status']}")
    print(f"Implementation: {skill['implementation_status']}")
    print(f"Purpose: {skill['purpose']}")
    print(f"Authority: {skill['authority_boundary']}")
    return 0


def _handle_api_skills_readiness(args: argparse.Namespace) -> int:
    report = evaluate_skill_readiness(args.skill_id)
    if report.status.value == "unknown_skill":
        message = f"Unknown skill id: {args.skill_id}"
        if args.as_json:
            print(json.dumps({"error": message, "readiness": report.to_dict()}, indent=2, sort_keys=True))
        else:
            print(message, file=sys.stderr)
        return 1

    payload = {"readiness": report.to_dict()}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    readiness = payload["readiness"]
    print(f"Skill readiness: {readiness['skill_id']}")
    print(f"Status: {readiness['status']}")
    print(f"Reason: {readiness['reason']}")
    print(f"Recommended next step: {readiness['recommended_next_step']}")
    return 0


def _handle_api_skills_propose(args: argparse.Namespace) -> int:
    proposal = propose_missing_skill(goal=args.goal, skill_id=args.skill_id)
    payload = {"proposal": proposal.to_dict()}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    proposal_payload = payload["proposal"]
    print(f"Missing skill proposal: {proposal_payload['proposal_id']}")
    if proposal_payload["source_goal"]:
        print(f"Goal: {proposal_payload['source_goal']}")
    if proposal_payload["candidate_skill_id"]:
        print(f"Candidate skill: {proposal_payload['candidate_skill_id']}")
    else:
        print("Candidate skill: none selected")
    print(f"Readiness: {proposal_payload['current_readiness_status']}")
    print(f"First slice: {proposal_payload['proposed_first_slice']}")
    print(f"Reason: {proposal_payload['reason_skill_is_needed']}")
    return 0


def _handle_api_overview_show(args: argparse.Namespace) -> int:
    overview = get_ari_operating_overview()
    payload = {"overview": overview.to_dict()}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    overview_payload = payload["overview"]
    print(f"ARI overview: {overview_payload['system_label']}")
    print(f"Dashboard mode: {overview_payload['dashboard_mode']}")
    print(f"Active skills: {overview_payload['active_skill_count']}")
    print(f"Prototype skills: {overview_payload['prototype_skill_count']}")
    print(f"Candidate skills: {overview_payload['candidate_skill_count']}")
    print(f"Authority: {overview_payload['authority_warning']}")
    return 0


def execute(action: dict, execution_root: Path | str | None = None) -> dict:
    """Run a minimal bounded execution action through canonical ARI."""

    return execute_action(action, execution_root=execution_root)


def _normalize_legacy_argv(argv: list[str] | None) -> list[str]:
    args = list(argv or [])
    if not args:
        return args
    if args[0] in LEGACY_NETWORKING_TOP_LEVEL:
        return ["networking", *args]
    if args[0] in LEGACY_DOCUMENTATION_TOP_LEVEL:
        return ["docs", *args]
    return args


def _maybe_handle_natural_language(argv: list[str] | None, db_path: Path = DB_PATH) -> int | None:
    args = list(argv or [])
    if not args:
        goal = input("ARI> ").strip()
        if not goal:
            raise ValueError("goal is required")
        return handle_natural_language_request(goal, cwd=Path.cwd(), db_path=db_path)

    if args[0] not in TOP_LEVEL_COMMANDS:
        goal = " ".join(args).strip()
        if not goal:
            raise ValueError("goal is required")
        return handle_natural_language_request(goal, cwd=Path.cwd(), db_path=db_path)

    return None


def _add_networking_parsers(subparsers: argparse._SubParsersAction) -> None:
    networking_parser = subparsers.add_parser("networking", help="Networking CRM module commands.")
    networking_subparsers = networking_parser.add_subparsers(
        dest="networking_command", required=True
    )

    networking_subparsers.add_parser("today", help="Show today's follow-up summary.")
    networking_subparsers.add_parser("status", help="Show networking module status.")
    networking_subparsers.add_parser(
        "init-db", help="Create the networking module SQLite database."
    )

    contacts_parser = networking_subparsers.add_parser("contacts", help="Contact commands.")
    contacts_subparsers = contacts_parser.add_subparsers(dest="contacts_command", required=True)
    contacts_subparsers.add_parser("list", help="List saved contacts.")
    contacts_show_parser = contacts_subparsers.add_parser(
        "show", help="Show a contact with notes and follow-ups."
    )
    contacts_show_parser.add_argument("--id", type=int, required=True, help="Existing contact id.")
    contacts_add_parser = contacts_subparsers.add_parser("add", help="Add a networking contact.")
    contacts_add_parser.add_argument("--name", required=True, help="Full name for the contact.")
    contacts_add_parser.add_argument("--company", help="Company name.")
    contacts_add_parser.add_argument("--role", dest="role_title", help="Role or title.")
    contacts_add_parser.add_argument("--location", help="Location or city.")
    contacts_add_parser.add_argument("--source", help="Where you met or found them.")
    contacts_add_parser.add_argument("--email", help="Email address.")
    contacts_add_parser.add_argument("--linkedin-url", help="LinkedIn profile URL.")
    contacts_note_parser = contacts_subparsers.add_parser(
        "add-note", help="Attach a note to a contact."
    )
    contacts_note_parser.add_argument(
        "--contact-id", type=int, required=True, help="Existing contact id."
    )
    contacts_note_parser.add_argument("--body", required=True, help="Note text.")

    followups_parser = networking_subparsers.add_parser("followups", help="Follow-up commands.")
    followups_subparsers = followups_parser.add_subparsers(dest="followups_command", required=True)
    followups_subparsers.add_parser("list", help="List saved follow-ups.")
    followups_subparsers.add_parser("due", help="Show overdue and today's pending follow-ups.")
    followups_add_parser = followups_subparsers.add_parser(
        "add", help="Add a follow-up for a contact."
    )
    followups_add_parser.add_argument(
        "--contact-id", type=int, required=True, help="Existing contact id."
    )
    followups_add_parser.add_argument(
        "--due-on", required=True, help="Due date in YYYY-MM-DD format."
    )
    followups_add_parser.add_argument("--reason", help="Reason or context for the follow-up.")
    followups_complete_parser = followups_subparsers.add_parser(
        "complete", help="Mark a follow-up as completed."
    )
    followups_complete_parser.add_argument(
        "--id", type=int, required=True, help="Existing follow-up id."
    )


def _add_docs_parsers(subparsers: argparse._SubParsersAction) -> None:
    docs_parser = subparsers.add_parser("docs", help="Documentation machine suit commands.")
    docs_subparsers = docs_parser.add_subparsers(dest="docs_command", required=True)

    content_parser = docs_subparsers.add_parser("content", help="Content workflow commands.")
    content_subparsers = content_parser.add_subparsers(dest="content_command", required=True)
    linkedin_parser = content_subparsers.add_parser(
        "linkedin", help="Generate a LinkedIn-ready draft."
    )
    linkedin_parser.add_argument(
        "--topic", required=True, help="Topic or project thread to draft about."
    )
    linkedin_parser.add_argument(
        "--style", choices=["story", "tactical", "insight"], help="Drafting style."
    )
    linkedin_parser.add_argument(
        "--format", choices=["full", "short"], default="full", help="Draft render mode."
    )
    linkedin_parser.add_argument(
        "--save", action="store_true", help="Save the generated draft under ~/ARI/content/."
    )
    mode_group = linkedin_parser.add_mutually_exclusive_group()
    mode_group.add_argument("--short", action="store_true", help="Generate a shorter draft.")
    mode_group.add_argument(
        "--detailed", action="store_true", help="Generate a more reflective draft."
    )

    script_parser = docs_subparsers.add_parser("script", help="Script workflow commands.")
    script_subparsers = script_parser.add_subparsers(dest="script_command", required=True)
    short_video_parser = script_subparsers.add_parser(
        "short-video", help="Generate a short-form video script."
    )
    short_video_parser.add_argument(
        "--topic", required=True, help="Topic or project thread to script about."
    )
    short_video_parser.add_argument(
        "--style", choices=["story", "tactical", "insight"], help="Scripting style."
    )

    demo_parser = docs_subparsers.add_parser("demo", help="Demo capture workflow commands.")
    demo_subparsers = demo_parser.add_subparsers(dest="demo_command", required=True)
    terminal_parser = demo_subparsers.add_parser(
        "terminal", help="Capture a terminal command for demo reuse."
    )
    terminal_parser.add_argument(
        "--command",
        dest="shell_command",
        required=True,
        help="Shell command string to run and capture.",
    )
    terminal_parser.add_argument("--save-name", help="Optional artifact name.")
    record_parser = demo_subparsers.add_parser(
        "record", help="Run a command while capturing a screen recording."
    )
    record_parser.add_argument(
        "--command",
        dest="shell_command",
        required=True,
        help="Shell command string to run while recording.",
    )
    record_parser.add_argument("--save-name", help="Optional artifact name.")
    record_parser.add_argument(
        "--pre-delay", type=float, default=1.0, help="Seconds to wait before executing the command."
    )
    record_parser.add_argument(
        "--post-delay", type=float, default=2.0, help="Seconds to wait after the command finishes."
    )

    video_parser = docs_subparsers.add_parser("video", help="Video artifact workflow commands.")
    video_subparsers = video_parser.add_subparsers(dest="video_command", required=True)
    video_build_parser = video_subparsers.add_parser(
        "build", help="Record a command execution into an ARI video artifact."
    )
    video_build_parser.add_argument(
        "--command",
        dest="shell_command",
        required=True,
        help="Shell command to run while recording.",
    )
    video_build_parser.add_argument("--save-name", help="Optional artifact name.")
    video_build_parser.add_argument(
        "--pre-delay", type=float, default=1.0, help="Seconds to wait before executing the command."
    )
    video_build_parser.add_argument(
        "--post-delay", type=float, default=2.0, help="Seconds to wait after the command finishes."
    )

    clip_parser = docs_subparsers.add_parser("clip", help="Clip artifact workflow commands.")
    clip_subparsers = clip_parser.add_subparsers(dest="clip_command", required=True)
    clip_build_parser = clip_subparsers.add_parser(
        "build", help="Trim an existing ARI video into a reusable clip."
    )
    clip_build_parser.add_argument(
        "--video", required=True, help="Path to an existing raw .mov artifact created by ARI."
    )
    clip_build_parser.add_argument("--save-name", help="Optional artifact name.")
    clip_build_parser.add_argument(
        "--mode",
        choices=["default", "proof"],
        default="default",
        help="Standard trim or proof-aware trim.",
    )
    clip_build_parser.add_argument(
        "--trim-start",
        type=float,
        default=0.5,
        help="Seconds to trim from the start of the source video.",
    )
    clip_build_parser.add_argument(
        "--trim-end",
        type=float,
        default=0.5,
        help="Seconds to trim from the end of the source video.",
    )

    frame_parser = docs_subparsers.add_parser("frame", help="Frame artifact workflow commands.")
    frame_subparsers = frame_parser.add_subparsers(dest="frame_command", required=True)
    frame_build_parser = frame_subparsers.add_parser(
        "build", help="Crop an existing ARI video into a framed artifact."
    )
    frame_build_parser.add_argument(
        "--video",
        required=True,
        help="Path to an existing raw or clipped .mov artifact created by ARI.",
    )
    frame_build_parser.add_argument("--save-name", help="Optional artifact name.")
    frame_build_parser.add_argument(
        "--mode", choices=["center", "terminal", "vertical"], default="terminal", help="Crop mode."
    )
    frame_build_parser.add_argument(
        "--anchor",
        choices=["auto", "frontmost", "terminal", "browser"],
        default="auto",
        help="Window anchor mode.",
    )
    frame_build_parser.add_argument("--window-title", help="Optional partial window-title match.")
    frame_build_parser.add_argument(
        "--padding", type=int, default=40, help="Padding around the detected window."
    )
    frame_build_parser.add_argument(
        "--width", type=int, default=800, help="Crop width for center and terminal modes."
    )
    frame_build_parser.add_argument(
        "--height", type=int, default=600, help="Crop height for center and terminal modes."
    )

    storyboard_parser = docs_subparsers.add_parser(
        "storyboard", help="Storyboard planning commands."
    )
    storyboard_subparsers = storyboard_parser.add_subparsers(
        dest="storyboard_command", required=True
    )
    short_video_storyboard_parser = storyboard_subparsers.add_parser(
        "short-video", help="Generate a short-form video storyboard."
    )
    short_video_storyboard_parser.add_argument(
        "--topic", required=True, help="Topic or project thread to plan around."
    )
    short_video_storyboard_parser.add_argument(
        "--style", choices=["story", "tactical", "insight"], help="Storyboard style."
    )
    short_video_storyboard_parser.add_argument(
        "--demo-file", help="Optional saved demo artifact path from `ari docs demo terminal`."
    )
    short_video_storyboard_parser.add_argument(
        "--save",
        action="store_true",
        help="Save the generated storyboard under ~/ARI/storyboards/.",
    )

    record_plan_parser = docs_subparsers.add_parser("record", help="Recording planning commands.")
    record_plan_subparsers = record_plan_parser.add_subparsers(dest="record_command", required=True)
    record_plan = record_plan_subparsers.add_parser(
        "plan", help="Generate a short-form recording plan."
    )
    record_plan.add_argument(
        "--topic", required=True, help="Topic or project thread to plan around."
    )
    record_plan.add_argument(
        "--style", choices=["story", "tactical", "insight"], help="Recording plan style."
    )
    record_plan.add_argument(
        "--demo-file", help="Optional saved demo artifact path from `ari docs demo terminal`."
    )
    record_plan.add_argument(
        "--save", action="store_true", help="Save the generated plan under ~/ARI/recordings/."
    )

    session_parser = docs_subparsers.add_parser(
        "session", help="Session documentation workflow commands."
    )
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)
    session_build_parser = session_subparsers.add_parser(
        "build", help="Build a structured session file from recent local demo activity."
    )
    session_build_parser.add_argument(
        "--limit", type=int, default=5, help="Number of recent demo files to aggregate."
    )
    session_build_parser.add_argument("--save-name", help="Optional artifact name.")


def _add_api_parsers(subparsers: argparse._SubParsersAction) -> None:
    api_parser = subparsers.add_parser("api", help="Canonical ARI API commands.")
    api_subparsers = api_parser.add_subparsers(dest="api_command", required=True)

    overview_parser = api_subparsers.add_parser(
        "overview", help="Read-only ARI operating overview commands."
    )
    overview_subparsers = overview_parser.add_subparsers(
        dest="api_overview_command", required=True
    )
    overview_show_parser = overview_subparsers.add_parser(
        "show", help="Show the ARI-owned dashboard overview read model."
    )
    overview_show_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    self_doc_parser = api_subparsers.add_parser(
        "self-doc", help="ARI self-documentation skill commands."
    )
    self_doc_subparsers = self_doc_parser.add_subparsers(
        dest="api_self_doc_command", required=True
    )
    self_doc_seed_parser = self_doc_subparsers.add_parser(
        "seed", help="Generate factual self-documentation content seeds."
    )
    self_doc_seed_subparsers = self_doc_seed_parser.add_subparsers(
        dest="api_self_doc_seed_command", required=True
    )
    self_doc_from_commits_parser = self_doc_seed_subparsers.add_parser(
        "from-commits", help="Generate a ContentSeed from a local git commit range."
    )
    self_doc_from_commits_parser.add_argument(
        "--from", dest="from_ref", required=True, help="Starting git ref, exclusive."
    )
    self_doc_from_commits_parser.add_argument(
        "--to", dest="to_ref", required=True, help="Ending git ref, inclusive."
    )
    self_doc_from_commits_parser.add_argument(
        "--repo-root", default=".", help="Local git repository root. Defaults to cwd."
    )
    self_doc_from_commits_parser.add_argument(
        "--test-output", default=None, help="Optional test output text to include as evidence."
    )
    self_doc_from_commits_parser.add_argument(
        "--user-framing", default=None, help="Optional user-approved narrative framing."
    )
    self_doc_from_commits_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    self_doc_package_parser = self_doc_subparsers.add_parser(
        "package", help="Generate read-only self-documentation content packages."
    )
    self_doc_package_subparsers = self_doc_package_parser.add_subparsers(
        dest="api_self_doc_package_command", required=True
    )
    self_doc_package_from_seed_parser = self_doc_package_subparsers.add_parser(
        "from-seed-json", help="Generate a ContentPackage from a local ContentSeed JSON file."
    )
    self_doc_package_from_seed_parser.add_argument(
        "--json-file", required=True, help="Path to a local ContentSeed JSON file."
    )
    self_doc_package_from_seed_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    skills_parser = api_subparsers.add_parser(
        "skills", help="Read-only ARI skill inventory and routing commands."
    )
    skills_subparsers = skills_parser.add_subparsers(dest="api_skills_command", required=True)
    skills_list_parser = skills_subparsers.add_parser(
        "list", help="List static ARI skill manifests."
    )
    skills_list_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    skills_show_parser = skills_subparsers.add_parser(
        "show", help="Show one static ARI skill manifest."
    )
    skills_show_parser.add_argument("--id", dest="skill_id", required=True, help="Skill id.")
    skills_show_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    skills_readiness_parser = skills_subparsers.add_parser(
        "readiness", help="Evaluate read-only readiness gates for one skill."
    )
    skills_readiness_parser.add_argument(
        "--id", dest="skill_id", required=True, help="Skill id."
    )
    skills_readiness_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    skills_route_parser = skills_subparsers.add_parser(
        "route", help="Classify a goal and recommend a native skill route."
    )
    skills_route_parser.add_argument("--goal", required=True, help="Goal to route.")
    skills_route_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    skills_propose_parser = skills_subparsers.add_parser(
        "propose", help="Create a read-only missing-skill implementation proposal."
    )
    skills_propose_target = skills_propose_parser.add_mutually_exclusive_group(required=True)
    skills_propose_target.add_argument("--goal", help="Goal that appears to need a skill.")
    skills_propose_target.add_argument("--skill-id", help="Candidate skill id to propose.")
    skills_propose_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_parser = api_subparsers.add_parser(
        "memory", help="Canonical ARI structured memory API commands."
    )
    memory_subparsers = memory_parser.add_subparsers(dest="api_memory_command", required=True)

    memory_remember_parser = memory_subparsers.add_parser(
        "remember", help="Remember canonical ARI structured memory."
    )
    memory_remember_parser.add_argument("--type", required=True, help="Structured memory type.")
    memory_remember_parser.add_argument("--title", required=True, help="Memory title.")
    memory_remember_parser.add_argument("--body", required=True, help="Memory content.")
    memory_remember_parser.add_argument(
        "--tags-json", dest="tags_json", default="[]", help="JSON array of memory tags."
    )
    memory_remember_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_list_parser = memory_subparsers.add_parser(
        "list", help="List canonical ARI structured memory."
    )
    memory_list_parser.add_argument(
        "--type", action="append", default=[], help="Structured memory type filter. Repeatable."
    )
    memory_list_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum memories to return."
    )
    memory_list_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_search_parser = memory_subparsers.add_parser(
        "search", help="Search canonical ARI structured memory."
    )
    memory_search_parser.add_argument("--query", default="", help="Query text.")
    memory_search_parser.add_argument(
        "--type", action="append", default=[], help="Structured memory type filter. Repeatable."
    )
    memory_search_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum memories to return."
    )
    memory_search_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_get_parser = memory_subparsers.add_parser(
        "get", help="Get a canonical ARI structured memory record by id."
    )
    memory_get_parser.add_argument("--id", required=True, help="Memory id.")
    memory_get_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_context_parser = memory_subparsers.add_parser(
        "context", help="Build structured memory context for a query."
    )
    memory_context_parser.add_argument("--query", default="", help="Query text.")
    memory_context_parser.add_argument(
        "--layer", action="append", default=[], help="Memory layer filter. Repeatable."
    )
    memory_context_parser.add_argument("--limit", type=int, default=10, help="Maximum blocks.")
    memory_context_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_blocks_parser = memory_subparsers.add_parser(
        "blocks", help="Structured layered memory block commands."
    )
    memory_blocks_subparsers = memory_blocks_parser.add_subparsers(
        dest="api_memory_blocks_command",
        required=True,
    )
    memory_block_create = memory_blocks_subparsers.add_parser(
        "create", help="Create a structured ARI memory block."
    )
    memory_block_create.add_argument(
        "--layer",
        required=True,
        choices=["session", "daily", "weekly", "open_loop", "long_term", "self_model"],
        help="Memory layer.",
    )
    memory_block_create.add_argument("--kind", required=True, help="Memory kind.")
    memory_block_create.add_argument("--title", required=True, help="Memory block title.")
    memory_block_create.add_argument("--body", required=True, help="Memory block body.")
    memory_block_create.add_argument("--source", default="manual", help="Memory source.")
    memory_block_create.add_argument("--importance", type=int, default=3, help="1-5 importance.")
    memory_block_create.add_argument(
        "--confidence", type=float, default=1.0, help="0-1 confidence."
    )
    memory_block_create.add_argument("--tags-json", default="[]", help="JSON array of tags.")
    memory_block_create.add_argument(
        "--subject-ids-json", default="[]", help="JSON array of linked subject ids."
    )
    memory_block_create.add_argument(
        "--evidence-json", default="[]", help="JSON array of evidence objects."
    )
    memory_block_create.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_block_list = memory_blocks_subparsers.add_parser(
        "list", help="List structured ARI memory blocks."
    )
    memory_block_list.add_argument("--layer", default=None, help="Optional layer filter.")
    memory_block_list.add_argument("--limit", type=int, default=20, help="Maximum blocks.")
    memory_block_list.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_block_search = memory_blocks_subparsers.add_parser(
        "search", help="Search structured ARI memory blocks."
    )
    memory_block_search.add_argument("--query", default="", help="Query text.")
    memory_block_search.add_argument("--layer", default=None, help="Optional layer filter.")
    memory_block_search.add_argument("--limit", type=int, default=20, help="Maximum blocks.")
    memory_block_search.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_block_get = memory_blocks_subparsers.add_parser(
        "get", help="Get a structured ARI memory block by id."
    )
    memory_block_get.add_argument("--id", required=True, help="Memory block id.")
    memory_block_get.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_capture_parser = memory_subparsers.add_parser(
        "capture", help="Capture canonical runtime traces into structured memory."
    )
    memory_capture_subparsers = memory_capture_parser.add_subparsers(
        dest="api_memory_capture_command",
        required=True,
    )
    memory_capture_execution = memory_capture_subparsers.add_parser(
        "execution", help="Capture execution run traces into session memory blocks."
    )
    memory_capture_execution.add_argument("--id", default=None, help="Execution run id.")
    memory_capture_execution.add_argument(
        "--limit", type=int, default=10, help="Recent run limit when id is omitted."
    )
    memory_capture_execution.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    memory_capture_retry = memory_capture_subparsers.add_parser(
        "retry-approval",
        help="Capture coding-loop retry approval traces into session memory blocks.",
    )
    memory_capture_retry.add_argument("--id", required=True, help="Retry approval id.")
    memory_capture_retry.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    memory_capture_chain = memory_capture_subparsers.add_parser(
        "coding-loop-chain",
        help="Capture coding-loop chain lifecycle summaries into session memory blocks.",
    )
    memory_capture_chain.add_argument("--id", required=True, help="Coding-loop result id.")
    memory_capture_chain.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_explain_parser = memory_subparsers.add_parser(
        "explain", help="Explain canonical ARI memory and runtime traces."
    )
    memory_explain_subparsers = memory_explain_parser.add_subparsers(
        dest="api_memory_explain_command",
        required=True,
    )
    memory_explain_execution = memory_explain_subparsers.add_parser(
        "execution", help="Explain an execution run from trace and memory."
    )
    memory_explain_execution.add_argument("--id", required=True, help="Execution run id.")
    memory_explain_execution.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    memory_explain_retry = memory_explain_subparsers.add_parser(
        "retry-approval",
        help="Explain a coding-loop retry approval from trace and memory.",
    )
    memory_explain_retry.add_argument("--id", required=True, help="Retry approval id.")
    memory_explain_retry.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )
    memory_explain_chain = memory_explain_subparsers.add_parser(
        "coding-loop-chain",
        help="Explain a coding-loop chain lifecycle from trace and memory.",
    )
    memory_explain_chain.add_argument("--id", required=True, help="Coding-loop result id.")
    memory_explain_chain.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    memory_self_model_parser = memory_subparsers.add_parser(
        "self-model", help="Manage ARI self-model memory."
    )
    memory_self_model_subparsers = memory_self_model_parser.add_subparsers(
        dest="api_memory_self_model_command",
        required=True,
    )
    memory_self_model_subparsers.add_parser(
        "ensure", help="Ensure canonical ARI self-model blocks exist."
    ).add_argument("--json", dest="as_json", action="store_true", help="Render JSON output.")
    memory_self_model_subparsers.add_parser(
        "show", help="Show canonical ARI self-model blocks."
    ).add_argument("--json", dest="as_json", action="store_true", help="Render JSON output.")

    coordination_parser = api_subparsers.add_parser(
        "coordination", help="Canonical ARI coordination runtime commands."
    )
    coordination_subparsers = coordination_parser.add_subparsers(
        dest="api_coordination_command", required=True
    )

    coordination_put_parser = coordination_subparsers.add_parser(
        "put", help="Upsert canonical coordination state."
    )
    coordination_put_parser.add_argument(
        "--entity", required=True, help="Coordination entity name."
    )
    coordination_put_parser.add_argument(
        "--payload-json", required=True, help="JSON object payload."
    )

    coordination_get_parser = coordination_subparsers.add_parser(
        "get", help="Get canonical coordination state by id."
    )
    coordination_get_parser.add_argument(
        "--entity", required=True, help="Coordination entity name."
    )
    coordination_get_parser.add_argument("--id", required=True, help="Record id.")

    coordination_list_parser = coordination_subparsers.add_parser(
        "list", help="List canonical coordination state."
    )
    coordination_list_parser.add_argument(
        "--entity", required=True, help="Coordination entity name."
    )
    coordination_list_parser.add_argument(
        "--limit", type=int, default=50, help="Maximum records to return."
    )

    policy_parser = api_subparsers.add_parser(
        "policy", help="Canonical ARI policy engine commands."
    )
    policy_subparsers = policy_parser.add_subparsers(dest="api_policy_command", required=True)

    policy_awareness_parser = policy_subparsers.add_parser(
        "awareness", help="Canonical awareness derivation and persistence."
    )
    policy_awareness_subparsers = policy_awareness_parser.add_subparsers(
        dest="api_policy_awareness_command", required=True
    )
    policy_awareness_derive = policy_awareness_subparsers.add_parser(
        "derive", help="Derive an awareness snapshot."
    )
    policy_awareness_derive.add_argument(
        "--payload-json", required=True, help="JSON object payload."
    )
    policy_awareness_store = policy_awareness_subparsers.add_parser(
        "store", help="Store an awareness snapshot."
    )
    policy_awareness_store.add_argument(
        "--payload-json", required=True, help="JSON object payload."
    )
    policy_awareness_subparsers.add_parser(
        "latest", help="Get the latest canonical awareness snapshot."
    )

    policy_orchestration_parser = policy_subparsers.add_parser(
        "orchestration-classify", help="Classify builder output canonically."
    )
    policy_orchestration_parser.add_argument(
        "--payload-json", required=True, help="JSON object payload."
    )

    policy_improvement_parser = policy_subparsers.add_parser(
        "improvements", help="Canonical self-improvement policy commands."
    )
    policy_improvement_subparsers = policy_improvement_parser.add_subparsers(
        dest="api_policy_improvement_command", required=True
    )
    policy_improvement_detect = policy_improvement_subparsers.add_parser(
        "detect", help="Detect ranked capability gaps."
    )
    policy_improvement_detect.add_argument(
        "--payload-json", required=True, help="JSON object payload."
    )
    policy_improvement_subparsers.add_parser("focus", help="Get the top self-improvement focus.")

    policy_project_parser = policy_subparsers.add_parser(
        "project", help="Canonical project-planning policy commands."
    )
    policy_project_subparsers = policy_project_parser.add_subparsers(
        dest="api_policy_project_command", required=True
    )
    policy_project_draft = policy_project_subparsers.add_parser(
        "draft", help="Build a canonical project draft."
    )
    policy_project_draft.add_argument("--payload-json", required=True, help="JSON object payload.")
    policy_project_subparsers.add_parser(
        "focus", help="Sync and return the canonical project focus."
    )

    notes_parser = api_subparsers.add_parser("notes", help="Canonical ARI notes API commands.")
    notes_subparsers = notes_parser.add_subparsers(dest="api_notes_command", required=True)

    notes_save_parser = notes_subparsers.add_parser("save", help="Save a canonical ARI note.")
    notes_save_parser.add_argument("--title", required=True, help="Note title.")
    notes_save_parser.add_argument("--body", required=True, help="Note body.")
    notes_save_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    notes_search_parser = notes_subparsers.add_parser("search", help="Search canonical ARI notes.")
    notes_search_parser.add_argument("--query", default="", help="Query text.")
    notes_search_parser.add_argument(
        "--limit", type=int, default=10, help="Maximum notes to return."
    )
    notes_search_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    tasks_parser = api_subparsers.add_parser("tasks", help="Canonical ARI tasks API commands.")
    tasks_subparsers = tasks_parser.add_subparsers(dest="api_tasks_command", required=True)

    tasks_create_parser = tasks_subparsers.add_parser("create", help="Create a canonical ARI task.")
    tasks_create_parser.add_argument("--title", required=True, help="Task title.")
    tasks_create_parser.add_argument("--notes", default="", help="Task notes.")
    tasks_create_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    tasks_list_parser = tasks_subparsers.add_parser("list", help="List canonical ARI tasks.")
    tasks_list_parser.add_argument("--limit", type=int, default=20, help="Maximum tasks to return.")
    tasks_list_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    tasks_get_parser = tasks_subparsers.add_parser("get", help="Get a canonical ARI task by id.")
    tasks_get_parser.add_argument("--id", required=True, help="Task id.")
    tasks_get_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    tasks_search_parser = tasks_subparsers.add_parser("search", help="Search canonical ARI tasks.")
    tasks_search_parser.add_argument("--query", default="", help="Query text.")
    tasks_search_parser.add_argument(
        "--limit", type=int, default=10, help="Maximum tasks to return."
    )
    tasks_search_parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Render JSON output."
    )

    execution_parser = api_subparsers.add_parser(
        "execution", help="Canonical ARI execution and operator commands."
    )
    execution_subparsers = execution_parser.add_subparsers(
        dest="api_execution_command", required=True
    )

    command_parser = execution_subparsers.add_parser(
        "command", help="Execute an allowlisted terminal command."
    )
    command_parser.add_argument("--command", required=True, help="Allowlisted terminal command.")
    command_parser.add_argument(
        "--cwd", default=".", help="Working directory relative to the execution root."
    )
    command_parser.add_argument(
        "--timeout-seconds", type=int, default=60, help="Command timeout in seconds."
    )

    read_file_parser = execution_subparsers.add_parser(
        "read-file", help="Read a file inside the execution root."
    )
    read_file_parser.add_argument(
        "--path", required=True, help="Path relative to the execution root."
    )

    write_file_parser = execution_subparsers.add_parser(
        "write-file", help="Replace file content inside the execution root."
    )
    write_file_parser.add_argument(
        "--path", required=True, help="Path relative to the execution root."
    )
    write_file_parser.add_argument("--content", required=True, help="Full file content.")
    write_file_parser.add_argument(
        "--action-id", help="Optional coding action id for mutation logging."
    )

    patch_file_parser = execution_subparsers.add_parser(
        "patch-file", help="Apply a simple search/replace patch inside the execution root."
    )
    patch_file_parser.add_argument(
        "--path", required=True, help="Path relative to the execution root."
    )
    patch_file_parser.add_argument("--find", required=True, help="Exact text to replace.")
    patch_file_parser.add_argument("--replace", required=True, help="Replacement text.")
    patch_file_parser.add_argument(
        "--action-id", help="Optional coding action id for mutation logging."
    )

    goal_parser = execution_subparsers.add_parser("goal", help="Run a bounded execution goal.")
    goal_parser.add_argument("--goal", required=True, help="Goal for the execution controller.")
    goal_parser.add_argument("--max-cycles", type=int, default=1, help="Maximum planner cycles.")
    goal_parser.add_argument(
        "--planner",
        choices=["rule_based", "model"],
        default="rule_based",
        help="Planner mode. Model mode falls back unless a completion function is configured.",
    )
    goal_parser.add_argument(
        "--execution-root",
        default=None,
        help="Optional execution root. Defaults to ARI_EXECUTION_ROOT or project root.",
    )

    plan_parser = execution_subparsers.add_parser(
        "plan", help="Preview a bounded execution plan without running actions."
    )
    plan_parser.add_argument("--goal", required=True, help="Goal for the execution planner.")
    plan_parser.add_argument("--max-cycles", type=int, default=1, help="Maximum planner cycles.")
    plan_parser.add_argument(
        "--planner",
        choices=["rule_based", "model"],
        default="rule_based",
        help="Planner mode. Model mode falls back unless a completion function is configured.",
    )
    plan_parser.add_argument(
        "--execution-root",
        default=None,
        help="Optional execution root. Defaults to ARI_EXECUTION_ROOT or project root.",
    )

    coding_loop_parser = execution_subparsers.add_parser(
        "coding-loop",
        help="Run one approval-aware coding-loop step and inspect the result.",
    )
    coding_loop_parser.add_argument("--goal", required=True, help="Coding goal for one loop step.")
    coding_loop_parser.add_argument(
        "--planner",
        choices=["rule_based", "model"],
        default="rule_based",
        help="Planner mode. Model mode falls back unless a completion function is configured.",
    )
    coding_loop_parser.add_argument(
        "--execution-root",
        default=None,
        help="Optional execution root. Defaults to ARI_EXECUTION_ROOT or project root.",
    )

    coding_loops_parser = execution_subparsers.add_parser(
        "coding-loops", help="Inspect persisted coding-loop results."
    )
    coding_loops_subparsers = coding_loops_parser.add_subparsers(
        dest="api_execution_coding_loops_command",
        required=True,
    )
    coding_loops_list_parser = coding_loops_subparsers.add_parser(
        "list", help="List recent coding-loop results."
    )
    coding_loops_list_parser.add_argument(
        "--limit", type=int, default=10, help="Maximum coding-loop results."
    )
    coding_loops_show_parser = coding_loops_subparsers.add_parser(
        "show", help="Show a coding-loop result."
    )
    coding_loops_show_parser.add_argument("--id", required=True, help="Coding-loop result id.")
    coding_loops_chain_parser = coding_loops_subparsers.add_parser(
        "chain",
        help="Show a bounded retry approval chain for a coding-loop result.",
    )
    coding_loops_chain_parser.add_argument("--id", required=True, help="Coding-loop result id.")
    coding_loops_chain_parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum retry approvals to traverse.",
    )
    coding_loops_advance_parser = coding_loops_subparsers.add_parser(
        "advance",
        help="Advance a coding-loop retry chain by at most one approved retry.",
    )
    coding_loops_advance_parser.add_argument("--id", required=True, help="Coding-loop result id.")
    coding_loops_advance_parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum retry approvals to traverse before advancing.",
    )
    coding_loops_approve_latest_parser = coding_loops_subparsers.add_parser(
        "approve-latest",
        help="Approve the latest pending retry approval in a coding-loop chain.",
    )
    coding_loops_approve_latest_parser.add_argument(
        "--id", required=True, help="Coding-loop result id."
    )
    coding_loops_approve_latest_parser.add_argument(
        "--approved-by",
        required=True,
        help="Authority label for the approver.",
    )
    coding_loops_approve_latest_parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum retry approvals to traverse before approving.",
    )
    coding_loops_reject_latest_parser = coding_loops_subparsers.add_parser(
        "reject-latest",
        help="Reject the latest pending retry approval in a coding-loop chain.",
    )
    coding_loops_reject_latest_parser.add_argument(
        "--id", required=True, help="Coding-loop result id."
    )
    coding_loops_reject_latest_parser.add_argument(
        "--reason",
        required=True,
        help="Reason for rejection.",
    )
    coding_loops_reject_latest_parser.add_argument(
        "--rejected-by",
        default=None,
        help="Optional authority label for the rejector.",
    )
    coding_loops_reject_latest_parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum retry approvals to traverse before rejecting.",
    )
    coding_loops_propose_next_parser = coding_loops_subparsers.add_parser(
        "propose-next",
        help="Create the next pending retry approval from an eligible chain review.",
    )
    coding_loops_propose_next_parser.add_argument(
        "--id", required=True, help="Coding-loop result id."
    )
    coding_loops_propose_next_parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum retry approvals to traverse before proposing.",
    )

    plans_parser = execution_subparsers.add_parser(
        "plans", help="Inspect persisted execution plan previews."
    )
    plans_subparsers = plans_parser.add_subparsers(
        dest="api_execution_plans_command",
        required=True,
    )
    plans_list_parser = plans_subparsers.add_parser(
        "list", help="List recent execution plan previews."
    )
    plans_list_parser.add_argument("--limit", type=int, default=10, help="Maximum previews.")
    plans_show_parser = plans_subparsers.add_parser("show", help="Show an execution plan preview.")
    plans_show_parser.add_argument("--id", required=True, help="Execution plan preview id.")

    runs_parser = execution_subparsers.add_parser("runs", help="Inspect execution runs.")
    runs_subparsers = runs_parser.add_subparsers(
        dest="api_execution_runs_command",
        required=True,
    )
    runs_list_parser = runs_subparsers.add_parser("list", help="List recent execution runs.")
    runs_list_parser.add_argument("--limit", type=int, default=10, help="Maximum runs to return.")
    runs_show_parser = runs_subparsers.add_parser("show", help="Show an execution run.")
    runs_show_parser.add_argument("--id", required=True, help="Execution run id.")

    retry_approvals_parser = execution_subparsers.add_parser(
        "retry-approvals",
        help="Inspect or mutate coding-loop retry approval artifacts.",
    )
    retry_approvals_subparsers = retry_approvals_parser.add_subparsers(
        dest="api_execution_retry_approvals_command",
        required=True,
    )
    retry_approvals_list_parser = retry_approvals_subparsers.add_parser(
        "list",
        help="List recent coding-loop retry approvals.",
    )
    retry_approvals_list_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum retry approvals to return.",
    )
    retry_approvals_show_parser = retry_approvals_subparsers.add_parser(
        "show",
        help="Show a coding-loop retry approval.",
    )
    retry_approvals_show_parser.add_argument("--id", required=True, help="Approval id.")
    retry_approvals_approve_parser = retry_approvals_subparsers.add_parser(
        "approve",
        help="Approve a coding-loop retry approval without executing it.",
    )
    retry_approvals_approve_parser.add_argument("--id", required=True, help="Approval id.")
    retry_approvals_approve_parser.add_argument(
        "--approved-by",
        required=True,
        help="Authority label for the approver.",
    )
    retry_approvals_reject_parser = retry_approvals_subparsers.add_parser(
        "reject",
        help="Reject a coding-loop retry approval without executing it.",
    )
    retry_approvals_reject_parser.add_argument("--id", required=True, help="Approval id.")
    retry_approvals_reject_parser.add_argument(
        "--reason",
        required=True,
        help="Reason for rejection.",
    )
    retry_approvals_reject_parser.add_argument(
        "--rejected-by",
        default=None,
        help="Optional authority label for the rejector.",
    )
    retry_approvals_execute_parser = retry_approvals_subparsers.add_parser(
        "execute",
        help="Execute one approved coding-loop retry approval.",
    )
    retry_approvals_execute_parser.add_argument("--id", required=True, help="Approval id.")
    retry_approvals_review_parser = retry_approvals_subparsers.add_parser(
        "review",
        help="Review the post-run state of one coding-loop retry approval.",
    )
    retry_approvals_review_parser.add_argument("--id", required=True, help="Approval id.")
    retry_approvals_propose_next_parser = retry_approvals_subparsers.add_parser(
        "propose-next",
        help="Create a pending follow-up approval from a propose_retry review.",
    )
    retry_approvals_propose_next_parser.add_argument(
        "--id",
        required=True,
        help="Approval id.",
    )

    execution_subparsers.add_parser("tools", help="List canonical execution tools.")

    context_parser = execution_subparsers.add_parser(
        "context", help="Inspect canonical repo context used for execution planning."
    )
    context_parser.add_argument(
        "--execution-root",
        default=None,
        help="Optional execution root. Defaults to ARI_EXECUTION_ROOT or project root.",
    )

    action_parser = execution_subparsers.add_parser(
        "actions", help="Canonical coding action lifecycle commands."
    )
    action_subparsers = action_parser.add_subparsers(
        dest="api_execution_action_command", required=True
    )

    action_create_parser = action_subparsers.add_parser("create", help="Create a coding action.")
    action_create_parser.add_argument("--title", required=True, help="Short action title.")
    action_create_parser.add_argument("--summary", default="", help="Optional summary.")
    action_create_parser.add_argument(
        "--operations-json", required=True, help="JSON array of file operations."
    )
    action_create_parser.add_argument(
        "--verify-command", default="", help="Allowlisted verification command."
    )
    action_create_parser.add_argument(
        "--working-directory", default=".", help="Working directory relative to the execution root."
    )
    action_create_parser.add_argument(
        "--approval-required",
        choices=["auto", "true", "false"],
        default="auto",
        help="Whether approval is required before running.",
    )

    action_get_parser = action_subparsers.add_parser("get", help="Get a coding action.")
    action_get_parser.add_argument("--id", required=True, help="Coding action id.")

    action_list_parser = action_subparsers.add_parser("list", help="List coding actions.")
    action_list_parser.add_argument(
        "--limit", type=int, default=6, help="Maximum actions to return."
    )

    action_approve_parser = action_subparsers.add_parser("approve", help="Approve a coding action.")
    action_approve_parser.add_argument("--id", required=True, help="Coding action id.")

    action_run_parser = action_subparsers.add_parser("run", help="Run a coding action end to end.")
    action_run_parser.add_argument("--id", required=True, help="Coding action id.")

    snapshot_parser = execution_subparsers.add_parser(
        "snapshot", help="Get the current coding execution snapshot."
    )
    snapshot_parser.add_argument("--limit", type=int, default=6, help="Maximum actions to return.")


def _add_runtime_parsers(subparsers: argparse._SubParsersAction) -> None:
    runtime_parser = subparsers.add_parser("runtime", help="Local-first ARI runtime loop commands.")
    runtime_subparsers = runtime_parser.add_subparsers(dest="runtime_command", required=True)

    codex_loop_parser = runtime_subparsers.add_parser(
        "codex-loop", help="Run a bounded ARI-controlled Codex worker loop."
    )
    codex_loop_parser.add_argument(
        "--goal", required=True, help="Coding goal for the Codex worker."
    )
    codex_loop_parser.add_argument(
        "--max-cycles", type=int, default=1, help="Maximum bounded worker cycles."
    )
    codex_loop_parser.add_argument(
        "--cwd", default=str(Path.cwd()), help="Working directory for the worker loop."
    )

    self_improve_parser = runtime_subparsers.add_parser(
        "self-improve", help="Run a bounded ARI self-improvement loop through Codex."
    )
    self_improve_parser.add_argument(
        "--goal", required=True, help="High-level self-improvement goal."
    )
    self_improve_parser.add_argument(
        "--max-cycles", type=int, default=2, help="Maximum bounded self-improvement cycles."
    )
    self_improve_parser.add_argument(
        "--cwd", default=str(Path.cwd()), help="Repository root for self-improvement work."
    )

    smoke_test_parser = runtime_subparsers.add_parser(
        "smoke-test", help="Run real-usage ARI scenarios in a disposable playground workspace."
    )
    smoke_test_parser.add_argument(
        "--scenario", default="all", help="Scenario name to run, or 'all'."
    )
    smoke_test_parser.add_argument(
        "--workspace", default="", help="Optional disposable workspace path."
    )
    smoke_test_parser.add_argument(
        "--reset-workspace",
        action="store_true",
        help="Reset the playground workspace before running.",
    )
    smoke_test_parser.add_argument(
        "--use-real-codex",
        action="store_true",
        help="Use the configured real Codex command instead of the safe playground worker.",
    )

    playground_run_parser = runtime_subparsers.add_parser(
        "playground-run",
        help="Run one natural-language goal inside a disposable playground workspace.",
    )
    playground_run_parser.add_argument(
        "--goal", required=True, help="Natural-language goal to run in the playground."
    )
    playground_run_parser.add_argument(
        "--workspace", default="", help="Optional disposable workspace path."
    )
    playground_run_parser.add_argument(
        "--reset-workspace",
        action="store_true",
        help="Reset the playground workspace before running.",
    )
    playground_run_parser.add_argument(
        "--use-real-codex",
        action="store_true",
        help="Use the configured real Codex command instead of the safe playground worker.",
    )


def _add_legacy_alias_parsers(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("today", help=argparse.SUPPRESS)

    contacts_parser = subparsers.add_parser("contacts", help=argparse.SUPPRESS)
    contacts_subparsers = contacts_parser.add_subparsers(dest="contacts_command", required=True)
    contacts_subparsers.add_parser("list", help=argparse.SUPPRESS)
    contacts_show_parser = contacts_subparsers.add_parser("show", help=argparse.SUPPRESS)
    contacts_show_parser.add_argument("--id", type=int, required=True, help=argparse.SUPPRESS)
    contacts_add_parser = contacts_subparsers.add_parser("add", help=argparse.SUPPRESS)
    contacts_add_parser.add_argument("--name", required=True, help=argparse.SUPPRESS)
    contacts_add_parser.add_argument("--company", help=argparse.SUPPRESS)
    contacts_add_parser.add_argument("--role", dest="role_title", help=argparse.SUPPRESS)
    contacts_add_parser.add_argument("--location", help=argparse.SUPPRESS)
    contacts_add_parser.add_argument("--source", help=argparse.SUPPRESS)
    contacts_add_parser.add_argument("--email", help=argparse.SUPPRESS)
    contacts_add_parser.add_argument("--linkedin-url", help=argparse.SUPPRESS)
    contacts_note_parser = contacts_subparsers.add_parser("add-note", help=argparse.SUPPRESS)
    contacts_note_parser.add_argument(
        "--contact-id", type=int, required=True, help=argparse.SUPPRESS
    )
    contacts_note_parser.add_argument("--body", required=True, help=argparse.SUPPRESS)

    followups_parser = subparsers.add_parser("followups", help=argparse.SUPPRESS)
    followups_subparsers = followups_parser.add_subparsers(dest="followups_command", required=True)
    followups_subparsers.add_parser("list", help=argparse.SUPPRESS)
    followups_subparsers.add_parser("due", help=argparse.SUPPRESS)
    followups_add_parser = followups_subparsers.add_parser("add", help=argparse.SUPPRESS)
    followups_add_parser.add_argument(
        "--contact-id", type=int, required=True, help=argparse.SUPPRESS
    )
    followups_add_parser.add_argument("--due-on", required=True, help=argparse.SUPPRESS)
    followups_add_parser.add_argument("--reason", help=argparse.SUPPRESS)
    followups_complete_parser = followups_subparsers.add_parser("complete", help=argparse.SUPPRESS)
    followups_complete_parser.add_argument("--id", type=int, required=True, help=argparse.SUPPRESS)

    content_parser = subparsers.add_parser("content", help=argparse.SUPPRESS)
    content_subparsers = content_parser.add_subparsers(dest="content_command", required=True)
    linkedin_parser = content_subparsers.add_parser("linkedin", help=argparse.SUPPRESS)
    linkedin_parser.add_argument("--topic", required=True, help=argparse.SUPPRESS)
    linkedin_parser.add_argument(
        "--style", choices=["story", "tactical", "insight"], help=argparse.SUPPRESS
    )
    linkedin_parser.add_argument(
        "--format", choices=["full", "short"], default="full", help=argparse.SUPPRESS
    )
    linkedin_parser.add_argument("--save", action="store_true", help=argparse.SUPPRESS)
    mode_group = linkedin_parser.add_mutually_exclusive_group()
    mode_group.add_argument("--short", action="store_true", help=argparse.SUPPRESS)
    mode_group.add_argument("--detailed", action="store_true", help=argparse.SUPPRESS)

    script_parser = subparsers.add_parser("script", help=argparse.SUPPRESS)
    script_subparsers = script_parser.add_subparsers(dest="script_command", required=True)
    short_video_parser = script_subparsers.add_parser("short-video", help=argparse.SUPPRESS)
    short_video_parser.add_argument("--topic", required=True, help=argparse.SUPPRESS)
    short_video_parser.add_argument(
        "--style", choices=["story", "tactical", "insight"], help=argparse.SUPPRESS
    )

    demo_parser = subparsers.add_parser("demo", help=argparse.SUPPRESS)
    demo_subparsers = demo_parser.add_subparsers(dest="demo_command", required=True)
    terminal_parser = demo_subparsers.add_parser("terminal", help=argparse.SUPPRESS)
    terminal_parser.add_argument(
        "--command", dest="shell_command", required=True, help=argparse.SUPPRESS
    )
    terminal_parser.add_argument("--save-name", help=argparse.SUPPRESS)
    record_parser = demo_subparsers.add_parser("record", help=argparse.SUPPRESS)
    record_parser.add_argument(
        "--command", dest="shell_command", required=True, help=argparse.SUPPRESS
    )
    record_parser.add_argument("--save-name", help=argparse.SUPPRESS)
    record_parser.add_argument("--pre-delay", type=float, default=1.0, help=argparse.SUPPRESS)
    record_parser.add_argument("--post-delay", type=float, default=2.0, help=argparse.SUPPRESS)

    video_parser = subparsers.add_parser("video", help=argparse.SUPPRESS)
    video_subparsers = video_parser.add_subparsers(dest="video_command", required=True)
    video_build_parser = video_subparsers.add_parser("build", help=argparse.SUPPRESS)
    video_build_parser.add_argument(
        "--command", dest="shell_command", required=True, help=argparse.SUPPRESS
    )
    video_build_parser.add_argument("--save-name", help=argparse.SUPPRESS)
    video_build_parser.add_argument("--pre-delay", type=float, default=1.0, help=argparse.SUPPRESS)
    video_build_parser.add_argument("--post-delay", type=float, default=2.0, help=argparse.SUPPRESS)

    clip_parser = subparsers.add_parser("clip", help=argparse.SUPPRESS)
    clip_subparsers = clip_parser.add_subparsers(dest="clip_command", required=True)
    clip_build_parser = clip_subparsers.add_parser("build", help=argparse.SUPPRESS)
    clip_build_parser.add_argument("--video", required=True, help=argparse.SUPPRESS)
    clip_build_parser.add_argument("--save-name", help=argparse.SUPPRESS)
    clip_build_parser.add_argument(
        "--mode", choices=["default", "proof"], default="default", help=argparse.SUPPRESS
    )
    clip_build_parser.add_argument("--trim-start", type=float, default=0.5, help=argparse.SUPPRESS)
    clip_build_parser.add_argument("--trim-end", type=float, default=0.5, help=argparse.SUPPRESS)

    frame_parser = subparsers.add_parser("frame", help=argparse.SUPPRESS)
    frame_subparsers = frame_parser.add_subparsers(dest="frame_command", required=True)
    frame_build_parser = frame_subparsers.add_parser("build", help=argparse.SUPPRESS)
    frame_build_parser.add_argument("--video", required=True, help=argparse.SUPPRESS)
    frame_build_parser.add_argument("--save-name", help=argparse.SUPPRESS)
    frame_build_parser.add_argument(
        "--mode",
        choices=["center", "terminal", "vertical"],
        default="terminal",
        help=argparse.SUPPRESS,
    )
    frame_build_parser.add_argument(
        "--anchor",
        choices=["auto", "frontmost", "terminal", "browser"],
        default="auto",
        help=argparse.SUPPRESS,
    )
    frame_build_parser.add_argument("--window-title", help=argparse.SUPPRESS)
    frame_build_parser.add_argument("--padding", type=int, default=40, help=argparse.SUPPRESS)
    frame_build_parser.add_argument("--width", type=int, default=800, help=argparse.SUPPRESS)
    frame_build_parser.add_argument("--height", type=int, default=600, help=argparse.SUPPRESS)

    storyboard_parser = subparsers.add_parser("storyboard", help=argparse.SUPPRESS)
    storyboard_subparsers = storyboard_parser.add_subparsers(
        dest="storyboard_command", required=True
    )
    short_video_storyboard_parser = storyboard_subparsers.add_parser(
        "short-video", help=argparse.SUPPRESS
    )
    short_video_storyboard_parser.add_argument("--topic", required=True, help=argparse.SUPPRESS)
    short_video_storyboard_parser.add_argument(
        "--style", choices=["story", "tactical", "insight"], help=argparse.SUPPRESS
    )
    short_video_storyboard_parser.add_argument("--demo-file", help=argparse.SUPPRESS)
    short_video_storyboard_parser.add_argument(
        "--save", action="store_true", help=argparse.SUPPRESS
    )

    record_plan_parser = subparsers.add_parser("record", help=argparse.SUPPRESS)
    record_plan_subparsers = record_plan_parser.add_subparsers(dest="record_command", required=True)
    record_plan = record_plan_subparsers.add_parser("plan", help=argparse.SUPPRESS)
    record_plan.add_argument("--topic", required=True, help=argparse.SUPPRESS)
    record_plan.add_argument(
        "--style", choices=["story", "tactical", "insight"], help=argparse.SUPPRESS
    )
    record_plan.add_argument("--demo-file", help=argparse.SUPPRESS)
    record_plan.add_argument("--save", action="store_true", help=argparse.SUPPRESS)

    session_parser = subparsers.add_parser("session", help=argparse.SUPPRESS)
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)
    session_build_parser = session_subparsers.add_parser("build", help=argparse.SUPPRESS)
    session_build_parser.add_argument("--limit", type=int, default=5, help=argparse.SUPPRESS)
    session_build_parser.add_argument("--save-name", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ari",
        description="ARI parent command surface for module and suit workflows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_networking_parsers(subparsers)
    _add_docs_parsers(subparsers)
    _add_api_parsers(subparsers)
    _add_runtime_parsers(subparsers)
    _add_legacy_alias_parsers(subparsers)
    return parser


def main(argv: list[str] | None = None, db_path: Path = DB_PATH) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if _is_local_help_request(args):
        print(_local_help_text(args))
        return 0

    natural_language_result = _maybe_handle_natural_language(
        argv if argv is not None else sys.argv[1:], db_path=db_path
    )
    if natural_language_result is not None:
        return natural_language_result

    parser = build_parser()
    normalized_argv = _normalize_legacy_argv(argv if argv is not None else sys.argv[1:])
    args = parser.parse_args(normalized_argv)

    if args.command == "networking":
        if args.networking_command == "today":
            return handle_today(db_path=db_path)
        if args.networking_command == "status":
            return handle_status(db_path=db_path)
        if args.networking_command == "init-db":
            return handle_init_db(db_path=db_path)
        if args.networking_command == "contacts" and args.contacts_command == "list":
            return handle_list_contacts(db_path=db_path)
        if args.networking_command == "contacts" and args.contacts_command == "show":
            return handle_show_contact(args, db_path=db_path)
        if args.networking_command == "contacts" and args.contacts_command == "add":
            return handle_add_contact(args, db_path=db_path)
        if args.networking_command == "contacts" and args.contacts_command == "add-note":
            return handle_add_note(args, db_path=db_path)
        if args.networking_command == "followups" and args.followups_command == "list":
            return handle_list_followups(db_path=db_path)
        if args.networking_command == "followups" and args.followups_command == "due":
            return handle_due(db_path=db_path)
        if args.networking_command == "followups" and args.followups_command == "add":
            return handle_add_followup(args, db_path=db_path)
        if args.networking_command == "followups" and args.followups_command == "complete":
            return handle_complete_followup(args, db_path=db_path)

    if args.command == "docs":
        if args.docs_command == "content" and args.content_command == "linkedin":
            return handle_content_linkedin(args, db_path=db_path)
        if args.docs_command == "script" and args.script_command == "short-video":
            return handle_script_short_video(args, db_path=db_path)
        if args.docs_command == "demo" and args.demo_command == "terminal":
            return handle_demo_terminal(args, db_path=db_path)
        if args.docs_command == "demo" and args.demo_command == "record":
            return handle_demo_record(args, db_path=db_path)
        if args.docs_command == "video" and args.video_command == "build":
            return handle_video_build(args, db_path=db_path)
        if args.docs_command == "clip" and args.clip_command == "build":
            return handle_clip_build(args, db_path=db_path)
        if args.docs_command == "frame" and args.frame_command == "build":
            return handle_frame_build(args, db_path=db_path)
        if args.docs_command == "storyboard" and args.storyboard_command == "short-video":
            return handle_storyboard_short_video(args, db_path=db_path)
        if args.docs_command == "record" and args.record_command == "plan":
            return handle_record_plan(args, db_path=db_path)
        if args.docs_command == "session" and args.session_command == "build":
            return handle_session_build(args, db_path=db_path)

    if args.command == "api":
        if args.api_command == "overview" and args.api_overview_command == "show":
            return _handle_api_overview_show(args)
        if (
            args.api_command == "self-doc"
            and args.api_self_doc_command == "seed"
            and args.api_self_doc_seed_command == "from-commits"
        ):
            return _handle_api_self_doc_seed_from_commits(args)
        if (
            args.api_command == "self-doc"
            and args.api_self_doc_command == "package"
            and args.api_self_doc_package_command == "from-seed-json"
        ):
            return _handle_api_self_doc_package_from_seed_json(args)
        if args.api_command == "skills" and args.api_skills_command == "list":
            return _handle_api_skills_list(args)
        if args.api_command == "skills" and args.api_skills_command == "show":
            return _handle_api_skills_show(args)
        if args.api_command == "skills" and args.api_skills_command == "readiness":
            return _handle_api_skills_readiness(args)
        if args.api_command == "skills" and args.api_skills_command == "route":
            return _handle_api_skills_route(args)
        if args.api_command == "skills" and args.api_skills_command == "propose":
            return _handle_api_skills_propose(args)
        if args.api_command == "memory" and args.api_memory_command == "remember":
            return handle_api_memory_remember(args, db_path=db_path)
        if args.api_command == "memory" and args.api_memory_command == "list":
            return handle_api_memory_list(args, db_path=db_path)
        if args.api_command == "memory" and args.api_memory_command == "search":
            return handle_api_memory_search(args, db_path=db_path)
        if args.api_command == "memory" and args.api_memory_command == "get":
            return handle_api_memory_get(args, db_path=db_path)
        if args.api_command == "memory" and args.api_memory_command == "context":
            return handle_api_memory_context(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "blocks"
            and args.api_memory_blocks_command == "create"
        ):
            return handle_api_memory_block_create(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "blocks"
            and args.api_memory_blocks_command == "list"
        ):
            return handle_api_memory_block_list(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "blocks"
            and args.api_memory_blocks_command == "search"
        ):
            return handle_api_memory_block_search(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "blocks"
            and args.api_memory_blocks_command == "get"
        ):
            return handle_api_memory_block_get(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "capture"
            and args.api_memory_capture_command == "execution"
        ):
            return handle_api_memory_capture_execution(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "capture"
            and args.api_memory_capture_command == "retry-approval"
        ):
            return handle_api_memory_capture_retry_approval(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "capture"
            and args.api_memory_capture_command == "coding-loop-chain"
        ):
            return handle_api_memory_capture_coding_loop_chain(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "explain"
            and args.api_memory_explain_command == "execution"
        ):
            return handle_api_memory_explain_execution(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "explain"
            and args.api_memory_explain_command == "retry-approval"
        ):
            return handle_api_memory_explain_retry_approval(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "explain"
            and args.api_memory_explain_command == "coding-loop-chain"
        ):
            return handle_api_memory_explain_coding_loop_chain(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "self-model"
            and args.api_memory_self_model_command == "ensure"
        ):
            return handle_api_memory_self_model_ensure(args, db_path=db_path)
        if (
            args.api_command == "memory"
            and args.api_memory_command == "self-model"
            and args.api_memory_self_model_command == "show"
        ):
            return handle_api_memory_self_model_show(args, db_path=db_path)
        if args.api_command == "coordination" and args.api_coordination_command == "put":
            return handle_api_coordination_put(args, db_path=db_path)
        if args.api_command == "coordination" and args.api_coordination_command == "get":
            return handle_api_coordination_get(args, db_path=db_path)
        if args.api_command == "coordination" and args.api_coordination_command == "list":
            return handle_api_coordination_list(args, db_path=db_path)
        if (
            args.api_command == "policy"
            and args.api_policy_command == "awareness"
            and args.api_policy_awareness_command == "derive"
        ):
            return handle_api_policy_awareness_derive(args, db_path=db_path)
        if (
            args.api_command == "policy"
            and args.api_policy_command == "awareness"
            and args.api_policy_awareness_command == "store"
        ):
            return handle_api_policy_awareness_store(args, db_path=db_path)
        if (
            args.api_command == "policy"
            and args.api_policy_command == "awareness"
            and args.api_policy_awareness_command == "latest"
        ):
            return handle_api_policy_awareness_latest(args, db_path=db_path)
        if args.api_command == "policy" and args.api_policy_command == "orchestration-classify":
            return handle_api_policy_orchestration_classify(args, db_path=db_path)
        if (
            args.api_command == "policy"
            and args.api_policy_command == "improvements"
            and args.api_policy_improvement_command == "detect"
        ):
            return handle_api_policy_improvement_detect(args, db_path=db_path)
        if (
            args.api_command == "policy"
            and args.api_policy_command == "improvements"
            and args.api_policy_improvement_command == "focus"
        ):
            return handle_api_policy_improvement_focus(args, db_path=db_path)
        if (
            args.api_command == "policy"
            and args.api_policy_command == "project"
            and args.api_policy_project_command == "draft"
        ):
            return handle_api_policy_project_draft(args, db_path=db_path)
        if (
            args.api_command == "policy"
            and args.api_policy_command == "project"
            and args.api_policy_project_command == "focus"
        ):
            return handle_api_policy_project_focus(args, db_path=db_path)
        if args.api_command == "notes" and args.api_notes_command == "save":
            return handle_api_notes_save(args, db_path=db_path)
        if args.api_command == "notes" and args.api_notes_command == "search":
            return handle_api_notes_search(args, db_path=db_path)
        if args.api_command == "tasks" and args.api_tasks_command == "create":
            return handle_api_tasks_create(args, db_path=db_path)
        if args.api_command == "tasks" and args.api_tasks_command == "list":
            return handle_api_tasks_list(args, db_path=db_path)
        if args.api_command == "tasks" and args.api_tasks_command == "get":
            return handle_api_tasks_get(args, db_path=db_path)
        if args.api_command == "tasks" and args.api_tasks_command == "search":
            return handle_api_tasks_search(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "command":
            return handle_api_execution_command(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "read-file":
            return handle_api_execution_read_file(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "write-file":
            return handle_api_execution_write_file(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "patch-file":
            return handle_api_execution_patch_file(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "goal":
            return handle_api_execution_goal(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "plan":
            return handle_api_execution_plan(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "coding-loop":
            return handle_api_execution_coding_loop(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "coding-loops"
            and args.api_execution_coding_loops_command == "list"
        ):
            return handle_api_execution_coding_loops_list(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "coding-loops"
            and args.api_execution_coding_loops_command == "show"
        ):
            return handle_api_execution_coding_loops_show(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "coding-loops"
            and args.api_execution_coding_loops_command == "chain"
        ):
            return handle_api_execution_coding_loops_chain(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "coding-loops"
            and args.api_execution_coding_loops_command == "advance"
        ):
            return handle_api_execution_coding_loops_advance(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "coding-loops"
            and args.api_execution_coding_loops_command == "approve-latest"
        ):
            return handle_api_execution_coding_loops_approve_latest(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "coding-loops"
            and args.api_execution_coding_loops_command == "reject-latest"
        ):
            return handle_api_execution_coding_loops_reject_latest(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "coding-loops"
            and args.api_execution_coding_loops_command == "propose-next"
        ):
            return handle_api_execution_coding_loops_propose_next(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "plans"
            and args.api_execution_plans_command == "list"
        ):
            return handle_api_execution_plans_list(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "plans"
            and args.api_execution_plans_command == "show"
        ):
            return handle_api_execution_plans_show(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "tools":
            return handle_api_execution_tools(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "context":
            return handle_api_execution_context(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "runs"
            and args.api_execution_runs_command == "list"
        ):
            return handle_api_execution_runs_list(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "runs"
            and args.api_execution_runs_command == "show"
        ):
            return handle_api_execution_runs_show(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "retry-approvals"
            and args.api_execution_retry_approvals_command == "list"
        ):
            return handle_api_execution_retry_approvals_list(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "retry-approvals"
            and args.api_execution_retry_approvals_command == "show"
        ):
            return handle_api_execution_retry_approvals_show(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "retry-approvals"
            and args.api_execution_retry_approvals_command == "approve"
        ):
            return handle_api_execution_retry_approvals_approve(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "retry-approvals"
            and args.api_execution_retry_approvals_command == "reject"
        ):
            return handle_api_execution_retry_approvals_reject(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "retry-approvals"
            and args.api_execution_retry_approvals_command == "execute"
        ):
            return handle_api_execution_retry_approvals_execute(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "retry-approvals"
            and args.api_execution_retry_approvals_command == "review"
        ):
            return handle_api_execution_retry_approvals_review(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "retry-approvals"
            and args.api_execution_retry_approvals_command == "propose-next"
        ):
            return handle_api_execution_retry_approvals_propose_next(args, db_path=db_path)
        if args.api_command == "execution" and args.api_execution_command == "snapshot":
            return handle_api_execution_snapshot(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "actions"
            and args.api_execution_action_command == "create"
        ):
            return handle_api_execution_action_create(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "actions"
            and args.api_execution_action_command == "get"
        ):
            return handle_api_execution_action_get(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "actions"
            and args.api_execution_action_command == "list"
        ):
            return handle_api_execution_action_list(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "actions"
            and args.api_execution_action_command == "approve"
        ):
            return handle_api_execution_action_approve(args, db_path=db_path)
        if (
            args.api_command == "execution"
            and args.api_execution_command == "actions"
            and args.api_execution_action_command == "run"
        ):
            return handle_api_execution_action_run(args, db_path=db_path)

    if args.command == "runtime":
        if args.runtime_command == "codex-loop":
            return handle_runtime_codex_loop(args, db_path=db_path)
        if args.runtime_command == "self-improve":
            return handle_runtime_self_improve(args, db_path=db_path)
        if args.runtime_command == "smoke-test":
            return handle_runtime_smoke_test(args)
        if args.runtime_command == "playground-run":
            return handle_runtime_playground_run(args)

    parser.error("Unknown ARI command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
