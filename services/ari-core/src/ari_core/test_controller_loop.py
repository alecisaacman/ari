from __future__ import annotations

from datetime import UTC, datetime

from ari_core import build_controller_decision, run_controller_cycle
from ari_core.decision_translate import translate_worker_decision
from ari_core.worker_client import AriWorkerClient


def main() -> None:
    client = AriWorkerClient()

    goal = "Fix a failing authentication test with a small reversible change."
    try:
        decision = client.decide(goal)
    except ValueError as exc:
        print("=== CONTRACT ERROR ===")
        print(exc)
        raise SystemExit(1) from exc

    controller_decision = build_controller_decision(decision)
    trajectory = run_controller_cycle(
        controller_decision,
        executed_at=datetime.now(tz=UTC),
    )
    intents = translate_worker_decision(decision)

    print("=== GOAL ===")
    print(goal)

    print("\n=== DECISION ===")
    print(f"id={controller_decision.id}")
    print(f"summary={controller_decision.decision_summary}")
    print(f"confidence={controller_decision.confidence}")
    print(f"type={controller_decision.decision_type}")
    print(f"requires_approval={controller_decision.requires_approval}")

    print("\n=== AUTHORITY ===")
    print(f"outcome={trajectory.authority_result.outcome}")
    print(f"may_execute={trajectory.authority_result.may_execute}")
    print(f"reason={trajectory.authority_result.reason}")

    print("\n=== INTENTS ===")
    for intent in intents:
        print(intent)
        print("-" * 80)

    print("\n=== OUTCOME ===")
    print(trajectory.controller_outcome)

    if trajectory.worker_run is not None:
        print("\n=== OBSERVATIONS ===")
        for obs in trajectory.worker_run.observations:
            print(obs)
            print("-" * 80)


if __name__ == "__main__":
    main()
