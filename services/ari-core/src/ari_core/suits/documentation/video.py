import argparse
from pathlib import Path

from .demo import _format_execution_summary, execute_recorded_command
from ...core.paths import DB_PATH


def handle_video_build(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    del db_path
    try:
        result = execute_recorded_command(
            args.shell_command,
            save_name=getattr(args, "save_name", None),
            pre_delay=getattr(args, "pre_delay", 1.0),
            post_delay=getattr(args, "post_delay", 2.0),
        )
    except Exception as exc:
        print("VIDEO BUILD")
        print(f"Command: {args.shell_command}")
        print("Status: FAILED")
        print("Video: [unavailable]")
        print("Metadata: [unavailable]")
        print(f"Notes: {exc}")
        return 1

    print("VIDEO BUILD")
    print(
        _format_execution_summary(
            command=args.shell_command,
            status=result["status"],
            video_path=result["video_path"],
            metadata_path=result["metadata_path"],
        ).split("\n", 1)[1]
    )
    if result["status"] == "FAILED":
        print(f"Notes: {result['notes']}")
    return int(result["exit_code"])
