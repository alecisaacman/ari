"""OpenAI Responses API adapter for ARI execution planning.

This module intentionally exposes a narrow completion function compatible with
ModelPlanner. It returns a strict JSON string and does not execute actions.
"""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


def build_openai_completion_fn(
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> Any:
    """Build a completion_fn(payload) callable for ModelPlanner.

    The returned callable sends ARI's planner payload to OpenAI and expects the
    model to return only strict JSON matching the WorkerPlan schema described in
    the payload.
    """
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for planner_mode=openai.")

    resolved_model = model or os.getenv("ARI_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL

    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "The openai package is required for planner_mode=openai. "
            "Install it in the active environment before using this backend."
        ) from error

    client = OpenAI(api_key=resolved_api_key)

    def complete(payload: dict[str, object]) -> str:
        response = client.responses.create(
            model=resolved_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are ARI's constrained execution planner. "
                        "Return only strict JSON. Do not include markdown. "
                        "Do not execute actions. Do not invent files outside allowed_files."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            text={
                "format": {
                    "type": "json_object",
                }
            },
        )

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        raise RuntimeError("OpenAI Responses API returned no output_text.")

    return complete
