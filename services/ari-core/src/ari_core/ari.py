# ruff: noqa: E501
import argparse
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
    handle_api_execution_command,
    handle_api_execution_context,
    handle_api_execution_goal,
    handle_api_execution_patch_file,
    handle_api_execution_read_file,
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
    handle_api_memory_capture_execution,
    handle_api_memory_context,
    handle_api_memory_explain_execution,
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

    runs_parser = execution_subparsers.add_parser("runs", help="Inspect execution runs.")
    runs_subparsers = runs_parser.add_subparsers(
        dest="api_execution_runs_command",
        required=True,
    )
    runs_list_parser = runs_subparsers.add_parser("list", help="List recent execution runs.")
    runs_list_parser.add_argument("--limit", type=int, default=10, help="Maximum runs to return.")
    runs_show_parser = runs_subparsers.add_parser("show", help="Show an execution run.")
    runs_show_parser.add_argument("--id", required=True, help="Execution run id.")

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
            and args.api_memory_command == "explain"
            and args.api_memory_explain_command == "execution"
        ):
            return handle_api_memory_explain_execution(args, db_path=db_path)
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
