"""What ARI's brain costs, request by request, and the monthly budget it stays under.

Every model request is recorded with its token counts and its cost, computed from
the usage the API reports. The month-to-date total decides whether the brain may
think again; when the budget is used up, surfaces answer without calling a model.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ari_memory.tables import BrainUsageRow
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .core import paths as core_paths

# Measured: about $9 a month at 20 messages a day (evals/brain, 2026-10-21).
DEFAULT_MONTHLY_BUDGET_USD = 10.0
WEB_SEARCH_USD = 0.01
HAIKU_LONG_PROMPT_TOKENS = 100_000


@dataclass(frozen=True, slots=True)
class Rates:
    """USD per million tokens. Cache writes are 1.25x input, cache reads 0.1x."""

    input: float
    output: float


# Claude API list prices (shared/models table, cached 2026-10-06).
RATES: dict[str, Rates] = {
    "claude-haiku-5-5": Rates(0.10, 0.50),
    "claude-sonnet-5-5": Rates(2.00, 10.00),
    "claude-sonnet-5": Rates(2.00, 10.00),
    "claude-opus-5-5": Rates(4.00, 20.00),
}
HAIKU_LONG_PROMPT_RATES = Rates(0.50, 2.50)
# A model ARI doesn't know (for example a refusal fallback) is costed at the
# highest rate it might be, so the budget errs toward stopping early.
UNKNOWN_MODEL_RATES = Rates(4.00, 20.00)


@dataclass(frozen=True, slots=True)
class ModelCall:
    model: str
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    web_searches: int

    @classmethod
    def from_response(cls, response: Any) -> ModelCall:
        usage = getattr(response, "usage", None)
        server_tools = getattr(usage, "server_tool_use", None)
        return cls(
            model=str(getattr(response, "model", "") or "unknown"),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_write_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            web_searches=int(getattr(server_tools, "web_search_requests", 0) or 0),
        )

    @property
    def cost_usd(self) -> float:
        rates = RATES.get(self.model, UNKNOWN_MODEL_RATES)
        prompt = self.input_tokens + self.cache_write_tokens + self.cache_read_tokens
        if self.model == "claude-haiku-5-5" and prompt > HAIKU_LONG_PROMPT_TOKENS:
            rates = HAIKU_LONG_PROMPT_RATES
        tokens = (
            self.input_tokens * rates.input
            + self.cache_write_tokens * rates.input * 1.25
            + self.cache_read_tokens * rates.input * 0.1
            + self.output_tokens * rates.output
        )
        return tokens / 1_000_000 + self.web_searches * WEB_SEARCH_USD

    @property
    def cold_cost_usd(self) -> float:
        """The cost if nothing had been cached yet: every cached token billed as a cache write."""
        cold = ModelCall(
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_write_tokens=self.cache_write_tokens + self.cache_read_tokens,
            cache_read_tokens=0,
            web_searches=self.web_searches,
        )
        return cold.cost_usd


def record_model_call(session: Session, call: ModelCall, *, channel: str, escalated: bool) -> None:
    session.add(
        BrainUsageRow(
            id=uuid4(),
            occurred_at=datetime.now(tz=UTC),
            channel=channel,
            model=call.model,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            cache_write_tokens=call.cache_write_tokens,
            cache_read_tokens=call.cache_read_tokens,
            web_searches=call.web_searches,
            cost_microusd=round(call.cost_usd * 1_000_000),
            escalated=escalated,
        )
    )
    session.commit()


@dataclass(frozen=True, slots=True)
class MonthSpend:
    spent_usd: float
    requests: int
    escalated_requests: int
    budget_usd: float

    @property
    def exhausted(self) -> bool:
        return self.spent_usd >= self.budget_usd

    def describe(self) -> str:
        return (
            f"${self.spent_usd:.2f} of ${self.budget_usd:.2f} this month, over {self.requests} "
            f"model requests ({self.escalated_requests} on the deeper model)."
        )


def month_spend(session: Session, *, now: datetime | None = None) -> MonthSpend:
    """Spend since the start of the current local calendar month."""
    current = now or datetime.now(tz=UTC)
    start = current.astimezone().replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    bind = session.get_bind()
    # SQLite keeps these timestamps as naive UTC; Postgres compares aware values.
    since = start.replace(tzinfo=None) if bind.dialect.name == "sqlite" else start
    in_month = BrainUsageRow.occurred_at >= since
    spent, requests = session.execute(
        select(func.coalesce(func.sum(BrainUsageRow.cost_microusd), 0), func.count(BrainUsageRow.id)).where(in_month)
    ).one()
    escalated = session.scalar(
        select(func.count(BrainUsageRow.id)).where(in_month, BrainUsageRow.escalated.is_(True))
    )
    return MonthSpend(
        spent_usd=int(spent) / 1_000_000,
        requests=int(requests),
        escalated_requests=int(escalated or 0),
        budget_usd=monthly_budget_usd(),
    )


def _budget_file() -> Path:
    return core_paths.ARI_ROOT / "state" / "brain-budget.json"


def monthly_budget_usd() -> float:
    """Alec's override from "ARI budget N", else ARI_BRAIN_MONTHLY_BUDGET_USD, else $10."""
    try:
        return float(json.loads(_budget_file().read_text(encoding="utf-8"))["monthly_usd"])
    except (OSError, ValueError, KeyError, TypeError):
        return float(os.environ.get("ARI_BRAIN_MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD))


def set_monthly_budget_usd(amount: float) -> None:
    if amount < 0:
        raise ValueError("The budget can't be negative.")
    path = _budget_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"monthly_usd": amount}), encoding="utf-8")
