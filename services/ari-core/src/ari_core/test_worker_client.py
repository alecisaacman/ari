from __future__ import annotations

from ari_core.worker_client import AriWorkerClient


def main() -> None:
    client = AriWorkerClient()

    print("=== HEALTH ===")
    print(client.health())

    print("\n=== DECISION ===")
    try:
        result = client.decide("Fix a failing authentication test with a small reversible change.")
    except ValueError as exc:
        print("=== CONTRACT ERROR ===")
        print(exc)
        raise SystemExit(1) from exc

    print(f"summary={result.decision_summary}")
    print(f"confidence={result.confidence}")

    print("\n=== ACTION INTENTS ===")
    for intent in result.action_intents:
        print(intent)


if __name__ == "__main__":
    main()
