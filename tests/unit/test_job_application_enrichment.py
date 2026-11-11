from __future__ import annotations

from datetime import UTC, datetime

import ari_core.state as state_module
import pytest
from ari_core.company_research import CompanyResearchFinding, CompanyResearchResult
from ari_core.state import CreateOpenLoopInput, create_open_loop
from ari_memory import Base, OpenLoopEnrichmentRepository, SkillInvocationRepository
from ari_state import OpenLoopKind
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_job_application_loop_triggers_enrichment_and_logs_skill_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARI_JOB_APPLICATION_ENRICHMENT_ENABLED", "true")  # the suite turns it off
    monkeypatch.setattr(
        state_module,
        "research_company",
        lambda company, **_: CompanyResearchResult(
            company=company,
            summary="No layoffs found; raised a Series B in March.",
            findings=[
                CompanyResearchFinding(
                    category="funding",
                    summary="Raised a $40M Series B in March 2026.",
                    source_url="https://example.com/funding",
                    published_at="2026-03-01",
                )
            ],
        ),
    )

    with _make_session() as session:
        result = create_open_loop(
            session,
            loop=CreateOpenLoopInput(
                title="Applied to Acme Corp",
                source="ari.brain",
                kind=OpenLoopKind.JOB_APPLICATION,
                company="Acme Corp",
            ),
            opened_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
        )

        assert result.state.company == "Acme Corp"

        enrichments = OpenLoopEnrichmentRepository(session).list_for_loop(result.state.id)
        assert len(enrichments) == 1
        assert enrichments[0].company == "Acme Corp"
        assert enrichments[0].findings[0]["category"] == "funding"

        invocations = SkillInvocationRepository(session).list_recent()
        assert len(invocations) == 1
        assert invocations[0].is_error is False
        assert invocations[0].skill_kind == "web_search"
        assert invocations[0].payload["company"] == "Acme Corp"
        assert invocations[0].payload["enrichment_id"] == str(enrichments[0].id)


def test_job_application_enrichment_failure_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARI_JOB_APPLICATION_ENRICHMENT_ENABLED", "true")  # the suite turns it off
    def _boom(company: str, **_: object) -> CompanyResearchResult:
        raise RuntimeError("search API unavailable")

    monkeypatch.setattr(state_module, "research_company", _boom)

    with _make_session() as session:
        result = create_open_loop(
            session,
            loop=CreateOpenLoopInput(
                title="Applied to Acme Corp",
                source="ari.brain",
                kind=OpenLoopKind.JOB_APPLICATION,
                company="Acme Corp",
            ),
            opened_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
        )

        assert OpenLoopEnrichmentRepository(session).list_for_loop(result.state.id) == []

        invocations = SkillInvocationRepository(session).list_recent()
        assert len(invocations) == 1
        assert invocations[0].is_error is True
        assert "search API unavailable" in invocations[0].payload["error"]


def test_job_application_enrichment_skipped_when_disabled_via_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARI_JOB_APPLICATION_ENRICHMENT_ENABLED", "false")

    def _fail_if_called(company: str, **_: object) -> CompanyResearchResult:
        raise AssertionError("research_company should not be called when disabled")

    monkeypatch.setattr(state_module, "research_company", _fail_if_called)

    with _make_session() as session:
        result = create_open_loop(
            session,
            loop=CreateOpenLoopInput(
                title="Applied to Acme Corp",
                source="ari.brain",
                kind=OpenLoopKind.JOB_APPLICATION,
                company="Acme Corp",
            ),
            opened_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
        )

        assert OpenLoopEnrichmentRepository(session).list_for_loop(result.state.id) == []
        assert SkillInvocationRepository(session).list_recent() == []


def test_non_job_application_loop_never_triggers_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_if_called(company: str, **_: object) -> CompanyResearchResult:
        raise AssertionError("research_company should not be called for kind=task")

    monkeypatch.setattr(state_module, "research_company", _fail_if_called)

    with _make_session() as session:
        result = create_open_loop(
            session,
            loop=CreateOpenLoopInput(
                title="Follow up with Acme Corp",
                source="ari.brain",
                kind=OpenLoopKind.TASK,
                company="Acme Corp",
            ),
            opened_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
        )

        assert OpenLoopEnrichmentRepository(session).list_for_loop(result.state.id) == []
        assert SkillInvocationRepository(session).list_recent() == []


def test_company_research_is_costed_in_aris_ledger_on_aris_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from ari_core import company_research

    seen: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            seen.update(kwargs)
            usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0,
                                    cache_read_input_tokens=0, server_tool_use=SimpleNamespace(web_search_requests=2))
            return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"summary": "ok", "findings": []}')],
                                   usage=usage, model=kwargs["model"])

    monkeypatch.setattr(company_research.anthropic, "Anthropic", lambda: SimpleNamespace(messages=FakeMessages()))
    result = company_research.research_company("Stripe")
    assert seen["model"] == "claude-sonnet-5-5" and seen["tools"][0]["type"] == "web_search_20260209"
    assert result.call is not None and result.call.web_searches == 2 and result.call.cost_usd > 0
