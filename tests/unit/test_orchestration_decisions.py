from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from uuid import uuid4


def _install_fake_orchestration_dependencies() -> None:
    if "ari_state" in sys.modules:
        return

    ari_state = ModuleType("ari_state")

    class AlertChannel(StrEnum):
        HUB = "hub"

    @dataclass(frozen=True)
    class EvidenceItem:
        kind: str
        summary: str

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {"kind": self.kind, "summary": self.summary}

    @dataclass(frozen=True)
    class Signal:
        id: str
        kind: str
        severity: str
        summary: str
        reason: str
        detected_at: datetime
        state_date: date | None = None
        fingerprint: str = ""
        evidence: list[EvidenceItem] | None = None
        related_entity_type: str | None = None
        related_entity_id: str | None = None

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "id": self.id,
                "kind": self.kind,
                "severity": self.severity,
                "summary": self.summary,
                "reason": self.reason,
                "state_date": None if self.state_date is None else self.state_date.isoformat(),
                "fingerprint": self.fingerprint,
            }

        def model_copy(self, update: dict[str, object]):
            return replace(self, **update)

    @dataclass(frozen=True)
    class Alert:
        id: str
        channel: AlertChannel
        escalation_level: str
        title: str
        message: str
        reason: str
        created_at: datetime
        state_date: date | None = None
        fingerprint: str = ""
        source_signal_ids: list[str] | None = None

        def model_copy(self, update: dict[str, object]):
            return replace(self, **update)

    @dataclass(frozen=True)
    class OrchestrationRun:
        state_date: date
        state_fingerprint: str
        executed_at: datetime
        signal_ids: list[str]
        alert_ids: list[str]
        id: str = field(default_factory=lambda: f"run-{uuid4()}")

    @dataclass(frozen=True)
    class DailyState:
        date: date

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {"date": self.date.isoformat()}

    @dataclass(frozen=True)
    class WeeklyState:
        week_start: date

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {"week_start": self.week_start.isoformat()}

    @dataclass(frozen=True)
    class OpenLoop:
        id: str
        title: str
        opened_at: datetime

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {"id": self.id, "title": self.title}

    ari_state.Alert = Alert
    ari_state.AlertChannel = AlertChannel
    ari_state.DailyState = DailyState
    ari_state.EvidenceItem = EvidenceItem
    ari_state.OpenLoop = OpenLoop
    ari_state.OrchestrationRun = OrchestrationRun
    ari_state.Signal = Signal
    ari_state.WeeklyState = WeeklyState
    sys.modules["ari_state"] = ari_state

    ari_memory = ModuleType("ari_memory")
    for name in (
        "AlertRepository",
        "DailyStateRepository",
        "OpenLoopRepository",
        "OrchestrationRunRepository",
        "SignalRepository",
        "WeeklyStateRepository",
    ):
        setattr(ari_memory, name, type(name, (), {}))
    sys.modules["ari_memory"] = ari_memory

    ari_signals = ModuleType("ari_signals")
    ari_signals.generate_signals = lambda **kwargs: []
    ari_signals.generate_alerts = lambda *args, **kwargs: []
    sys.modules["ari_signals"] = ari_signals

    sqlalchemy = ModuleType("sqlalchemy")
    sqlalchemy_orm = ModuleType("sqlalchemy.orm")
    sqlalchemy_orm.Session = object
    sqlalchemy.orm = sqlalchemy_orm
    sys.modules["sqlalchemy"] = sqlalchemy
    sys.modules["sqlalchemy.orm"] = sqlalchemy_orm


_install_fake_orchestration_dependencies()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
service_src = str(PROJECT_ROOT / "services/ari-core/src")
if service_src not in sys.path:
    sys.path.insert(0, service_src)

orchestration_module = importlib.import_module("ari_core.orchestration")
from ari_core.decision.controller import DecisionController
from ari_core.modules.decision.dispatch import DispatchResult
from ari_core.modules.decision.persistence import PersistedDecisionTrail
from ari_state import Alert, AlertChannel, EvidenceItem, OrchestrationRun, Signal


class _FakeDailyStateRepository:
    def __init__(self, session) -> None:
        del session

    def get(self, state_date):
        del state_date
        return None


class _FakeWeeklyStateRepository:
    def __init__(self, session) -> None:
        del session

    def get(self, week_start):
        del week_start
        return None


class _FakeOpenLoopRepository:
    def __init__(self, session) -> None:
        del session

    def list_open(self):
        return []


class _FakeSignalRepository:
    def __init__(self, session) -> None:
        del session

    def get_by_fingerprint(self, *, state_date, fingerprint):
        del state_date, fingerprint
        return None

    def create(self, signal):
        return signal

    def list_recent(self, limit=100):
        del limit
        return [
            Signal(
                id="signal-previous",
                kind="open_loop_accumulation",
                severity="warning",
                summary="Older open loops existed before today.",
                reason="The workspace had accumulated unresolved loops before this run.",
                detected_at=datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            )
        ]


class _FakeAlertRepository:
    def __init__(self, session) -> None:
        del session

    def get_by_fingerprint(self, *, state_date, fingerprint):
        del state_date, fingerprint
        return None

    def create(self, alert):
        return alert


class _FakeRunRepository:
    def __init__(self, session) -> None:
        del session

    def create(self, run):
        return run


class _FakeSession:
    def commit(self) -> None:
        return None


def test_run_signal_orchestration_emits_decisions_before_alerts(monkeypatch) -> None:
    order: list[str] = []

    monkeypatch.setattr(orchestration_module, "DailyStateRepository", _FakeDailyStateRepository)
    monkeypatch.setattr(orchestration_module, "WeeklyStateRepository", _FakeWeeklyStateRepository)
    monkeypatch.setattr(orchestration_module, "OpenLoopRepository", _FakeOpenLoopRepository)
    monkeypatch.setattr(orchestration_module, "SignalRepository", _FakeSignalRepository)
    monkeypatch.setattr(orchestration_module, "AlertRepository", _FakeAlertRepository)
    monkeypatch.setattr(orchestration_module, "OrchestrationRunRepository", _FakeRunRepository)

    def fake_generate_signals(*, detected_at, daily_state, weekly_state, open_loops):
        del daily_state, weekly_state, open_loops
        order.append("signals")
        return [
            Signal(
                id="signal-current",
                kind="open_loop_accumulation",
                severity="critical",
                summary="Open loops are critically high.",
                reason="The workspace surface is overloaded.",
                evidence=[EvidenceItem(kind="count", summary="12 open loops")],
                detected_at=detected_at,
            )
        ]

    def fake_generate_alerts(signals, *, created_at, channel):
        del signals
        order.append("alerts")
        return [
            Alert(
                id="alert-current",
                channel=channel,
                escalation_level="interruptive",
                title="Open loops need attention",
                message="The workspace is overloaded.",
                reason="Critical open loop accumulation detected.",
                created_at=created_at,
                source_signal_ids=["signal-current"],
            )
        ]

    real_controller = DecisionController()

    def fake_decide(*, signals, alerts=(), state, run_context=None):
        order.append("decisions")
        return real_controller.decide(signals=signals, alerts=alerts, state=state, run_context=run_context)

    def fake_dispatch(decision):
        return DispatchResult(
            decision_reference=f"{decision.intent}:{decision.action.get('type', 'unknown')}:signal",
            status="executed",
            reason="The bounded action is safe for orchestration dispatch tests.",
            action=decision.action,
            execution_result={"success": True},
        )

    def fake_persist(**kwargs):
        return PersistedDecisionTrail(
            decisions=[decision.to_dict() for decision in kwargs["decisions"]],
            dispatches=[result.to_dict() for result in kwargs["dispatch_results"]],
            evaluations=[result.to_dict() for result in kwargs["evaluation_results"]],
            cycle={"status": kwargs["loop_control"].status},
        )

    monkeypatch.setattr(orchestration_module, "generate_signals", fake_generate_signals)
    monkeypatch.setattr(orchestration_module, "generate_alerts", fake_generate_alerts)
    monkeypatch.setattr(orchestration_module.decision_controller, "decide", fake_decide)
    monkeypatch.setattr(orchestration_module, "dispatch_decision", fake_dispatch)
    monkeypatch.setattr(orchestration_module, "persist_decision_trail", fake_persist)

    result = orchestration_module.run_signal_orchestration(
        session=_FakeSession(),
        orchestration_input=orchestration_module.RunSignalOrchestrationInput(
            state_date=date(2026, 4, 22),
            detected_at=datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc),
            alert_channel=AlertChannel.HUB,
        ),
    )

    assert order == ["signals", "decisions", "alerts"]
    assert isinstance(result.run, OrchestrationRun)
    assert len(result.signals) == 1
    assert len(result.decisions) == 1
    assert result.decisions[0].decision_type == "act"
    assert result.decisions[0].reasoning
    assert len(result.alerts) == 1
    assert result.persisted_trail is not None
