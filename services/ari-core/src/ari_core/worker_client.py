from __future__ import annotations

from typing import Any

import requests

from ari_core.execution_types import WorkerDecision, parse_worker_decision


class AriWorkerClient:
    def __init__(self, base_url: str = "http://localhost:4010", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def decide(self, goal: str) -> WorkerDecision:
        response = requests.post(
            f"{self.base_url}/decision",
            json={"goal": goal},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._parse_decision_payload(response.json())

    def _parse_decision_payload(self, payload: object) -> WorkerDecision:
        if not isinstance(payload, dict):
            raise ValueError("Worker decision response must be a JSON object.")
        try:
            return parse_worker_decision(payload)
        except ValueError as exc:
            raise ValueError(
                "Worker decision response does not match the typed action_intents contract: "
                f"{exc}. Received keys: {sorted(payload)}."
            ) from exc
