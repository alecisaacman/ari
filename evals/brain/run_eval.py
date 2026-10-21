"""Compare ARI's routed brain (Haiku first, Sonnet on escalation) with Sonnet alone.

Each case is a realistic message from Alec, answered against its own freshly seeded,
temporary ARI state, so tools really run and return what they would in use, and
nothing real changes. Workspace proposals are recorded but never executed. Each answer is
checked against the case's expectations (which tools ran, whether the turn went to
the deeper model, what the reply says), and its cost and latency are recorded.
The replies are written out for Alec to read: the checks catch wrong behavior,
not tone.

This calls the real API and costs money; --max-usd stops the run at a ceiling.

    python evals/brain/run_eval.py --max-usd 2
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ari_core.brain import DEEP_MODEL, make_client, make_tool_dispatcher, respond_to_message
from ari_core.brain_usage import ModelCall
from ari_core.state import (
    CreateOpenLoopInput,
    DailyStateUpdate,
    WeeklyPlanningUpdate,
    create_open_loop,
    update_daily_state,
    update_weekly_plan,
)
from ari_memory import create_engine, create_session_factory
from ari_state import OpenLoopKind, OpenLoopPriority
from sqlalchemy.orm import Session, sessionmaker

HERE = Path(__file__).resolve().parent
CONFIGS = ("routed", "sonnet")


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class CaseResult:
    case_id: str
    category: str
    config: str
    message: str
    reply: str | None
    tools: list[dict[str, Any]]
    models: list[str]
    deep_served: bool
    cost_usd: float
    cold_cost_usd: float
    seconds: float
    checks: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(check["passed"] for check in self.checks)


def seed_state(session_factory: sessionmaker[Session], today: date) -> None:
    now = datetime.now(tz=UTC)
    loops = [
        ("Finish FOMC paper draft", OpenLoopKind.TASK, OpenLoopPriority.HIGH, None),
        ("Buy printer ink", OpenLoopKind.TASK, OpenLoopPriority.LOW, None),
        ("Stripe data analyst application", OpenLoopKind.JOB_APPLICATION, OpenLoopPriority.HIGH, "Stripe"),
        ("Ramp data analyst application", OpenLoopKind.JOB_APPLICATION, OpenLoopPriority.MEDIUM, "Ramp"),
        ("Econ 537 paper due Friday", OpenLoopKind.COMMITMENT, OpenLoopPriority.CRITICAL, None),
        ("Follow up with Sam about the internship", OpenLoopKind.FOLLOW_UP, OpenLoopPriority.MEDIUM, None),
    ]
    with session_factory() as session:
        for index, (title, kind, priority, company) in enumerate(loops):
            create_open_loop(
                session,
                loop=CreateOpenLoopInput(
                    title=title, source="eval.seed", kind=kind, priority=priority, company=company
                ),
                opened_at=now - timedelta(days=index + 1),
            )
        update_daily_state(
            session,
            day=today,
            update=DailyStateUpdate(
                priorities=["Outline econ paper section 3", "Submit the Ramp application"],
                win_condition="Finish the econ paper outline",
                stress=3,
                next_action="Write the section 3 outline",
            ),
            checked_at=now,
        )
        update_weekly_plan(
            session,
            state_date=today,
            update=WeeklyPlanningUpdate(
                outcomes=["Submit the econ 537 paper", "Two job applications in"],
                cannot_drift=["Econ paper"],
            ),
            reviewed_at=now,
        )
        session.commit()


def run_case(
    case: dict[str, Any],
    config: str,
    *,
    client: Any,
    workdir: Path,
    on_cost: Callable[[float], None],
) -> CaseResult:
    tools: list[dict[str, Any]] = []
    calls: list[tuple[ModelCall, bool]] = []
    # Each answer gets its own seeded state, so tool results look exactly as they
    # would in use and no case sees another's changes.
    session_factory = create_session_factory(
        create_engine(f"sqlite+pysqlite:///{workdir / f'{case['id']}-{config}.db'}")
    )
    seed_state(session_factory, datetime.now().date())
    dispatch = make_tool_dispatcher(
        session_factory,
        save_for_later=lambda link, note: None,
        propose_action=lambda tool_input: {
            "proposal_id": "proposal-1",
            "summary": tool_input.get("summary"),
            "status": "awaiting Alec's approval",
        },
    )

    def recording_dispatch(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        tools.append({"name": name, "input": tool_input})
        return dispatch(name, tool_input)

    def record(call: ModelCall, deep: bool) -> None:
        calls.append((call, deep))
        on_cost(call.cost_usd)

    started = time.monotonic()
    result = CaseResult(
        case_id=case["id"], category=case["category"], config=config, message=case["message"],
        reply=None, tools=tools, models=[], deep_served=False, cost_usd=0.0, cold_cost_usd=0.0, seconds=0.0,
    )
    try:
        response = respond_to_message(
            text=case["message"],
            history=[],
            dispatch_tool=recording_dispatch,
            model=DEEP_MODEL if config == "sonnet" else None,
            record_call=record,
            client=client,
        )
        result.reply = response.reply
    except BudgetExceeded:
        raise
    except Exception as error:  # noqa: BLE001 - one failing case is a result, not a crash
        result.error = f"{type(error).__name__}: {error}"
    result.seconds = round(time.monotonic() - started, 2)
    result.models = [call.model for call, _ in calls]
    result.deep_served = bool(calls) and calls[-1][1]
    result.cost_usd = round(sum(call.cost_usd for call, _ in calls), 6)
    result.cold_cost_usd = round(sum(call.cold_cost_usd for call, _ in calls), 6)
    result.checks = grade(case, result, routed=config == "routed")
    return result


def grade(case: dict[str, Any], result: CaseResult, *, routed: bool) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    names = [tool["name"] for tool in result.tools]

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": passed, "detail": detail})

    for tool in case.get("expect_tools", []):
        check(f"calls {tool}", tool in names, ", ".join(names) or "no tools")
    if "expect_any_tool" in case:
        check("reads state", any(tool in names for tool in case["expect_any_tool"]), ", ".join(names) or "no tools")
    for tool in case.get("forbid_tools", []):
        check(f"does not call {tool}", tool not in names, ", ".join(names) or "no tools")
    for tool, count in case.get("expect_tool_count", {}).items():
        check(f"calls {tool} {count}x", names.count(tool) == count, f"{names.count(tool)} calls")
    for tool, expected in case.get("expect_tool_input", {}).items():
        inputs = [call["input"] for call in result.tools if call["name"] == tool]
        matched = any(
            all(str(value).lower() == str(inp.get(key, "")).lower() for key, value in expected.items())
            for inp in inputs
        )
        check(f"{tool} with {expected}", matched, json.dumps(inputs)[:200])
    if case.get("expect_no_reply"):
        check("stays silent", result.reply is None, repr(result.reply))
    for fragment in case.get("reply_mentions", []):
        check(f"reply mentions {fragment!r}", fragment.lower() in (result.reply or "").lower(), result.reply or "")
    if "max_reply_chars" in case:
        length = len(result.reply or "")
        check(f"reply under {case['max_reply_chars']} chars", length <= case["max_reply_chars"], f"{length} chars")
    if routed and "escalate" in case:
        expected = case["escalate"]
        check(
            "goes to deeper model" if expected else "stays on fast model",
            result.deep_served == expected,
            " -> ".join(result.models),
        )
    return checks


def summarize(results: list[CaseResult]) -> str:
    lines = ["# ARI brain eval", ""]
    lines.append(
        "| Config | Passed | Cost | Avg cost/msg | Avg cold-cache cost/msg | Avg seconds | Deeper model used |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for config in CONFIGS:
        rows = [result for result in results if result.config == config]
        if not rows:
            continue
        passed = sum(result.passed for result in rows)
        cost = sum(result.cost_usd for result in rows)
        cold = sum(result.cold_cost_usd for result in rows)
        seconds = sum(result.seconds for result in rows) / len(rows)
        deep = sum(result.deep_served for result in rows)
        lines.append(
            f"| {config} | {passed}/{len(rows)} | ${cost:.4f} | ${cost / len(rows):.5f} | "
            f"${cold / len(rows):.5f} | {seconds:.1f} | {deep}/{len(rows)} |"
        )
    lines += ["", "## Cases", ""]
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        lines.append(f"### {mark} `{result.case_id}` ({result.config}, {result.category})")
        lines.append(f"> {result.message}")
        lines.append("")
        lines.append(f"Reply: {result.reply if result.reply is not None else '(no reply)'}")
        lines.append("")
        lines.append(
            f"Models: {' -> '.join(result.models) or 'none'} | tools: "
            f"{', '.join(tool['name'] for tool in result.tools) or 'none'} | ${result.cost_usd:.5f} | {result.seconds}s"
        )
        if result.error:
            lines.append(f"Error: {result.error}")
        for item in result.checks:
            lines.append(f"- {'ok' if item['passed'] else 'MISS'} {item['check']}" + (f" ({item['detail']})" if not item["passed"] else ""))
        lines.append("")
    return "\n".join(lines)


def run_eval(
    cases: list[dict[str, Any]],
    *,
    client: Any,
    configs: tuple[str, ...] = CONFIGS,
    max_usd: float = 2.0,
    out_dir: Path | None = None,
) -> list[CaseResult]:
    spent = 0.0

    def on_cost(amount: float) -> None:
        nonlocal spent
        spent += amount
        if spent > max_usd:
            raise BudgetExceeded(f"Stopped at ${spent:.2f}, over the ${max_usd:.2f} ceiling.")

    results: list[CaseResult] = []
    with tempfile.TemporaryDirectory(prefix="ari-brain-eval-") as workdir:
        try:
            # One full pass per setup, so neither reads a cache the other just wrote.
            for config in configs:
                for case in cases:
                    results.append(run_case(case, config, client=client, workdir=Path(workdir), on_cost=on_cost))
        except BudgetExceeded as error:
            print(error)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(
            json.dumps([{**asdict(result), "passed": result.passed} for result in results], indent=2),
            encoding="utf-8",
        )
        (out_dir / "report.md").write_text(summarize(results), encoding="utf-8")
    return results


def main() -> int:
    from ari_imessage_gateway.config import ari_home, load_local_env

    # The same private settings file the iMessage surface reads (ARI_HOME/ari.env).
    load_local_env(ari_home() / "ari.env")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-usd", type=float, default=2.0, help="Stop once spend passes this.")
    parser.add_argument("--configs", default=",".join(CONFIGS), help="routed, sonnet, or both.")
    parser.add_argument("--cases", default="", help="Comma-separated case ids; default all.")
    args = parser.parse_args()

    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [case for case in cases if case["id"] in wanted]
    out_dir = HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    results = run_eval(
        cases,
        client=make_client(),
        configs=tuple(args.configs.split(",")),
        max_usd=args.max_usd,
        out_dir=out_dir,
    )
    print(summarize(results).split("## Cases")[0])
    print(f"Full report: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
