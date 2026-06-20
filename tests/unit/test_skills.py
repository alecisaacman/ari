from datetime import UTC, datetime
from pathlib import Path

from ari_core import skills
from ari_memory import Base, SkillInvocationRepository, SkillRegistrationRepository
from ari_state import SkillKind
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session(tmp_path: Path) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_register_skill_encrypts_token_and_round_trips(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ARI_SKILL_TOKEN_KEY", Fernet.generate_key().decode())
    session = _session(tmp_path)

    registration = skills.register_skill(
        session,
        name="example-mcp",
        mcp_url="https://example-server.modelcontextprotocol.io/sse",
        token="plaintext-oauth-token",
    )

    assert registration.encrypted_token != "plaintext-oauth-token"
    assert skills.decrypt_token(registration.encrypted_token) == "plaintext-oauth-token"

    stored = SkillRegistrationRepository(session).get_by_name("example-mcp")
    assert stored is not None
    assert stored.encrypted_token == registration.encrypted_token


def test_register_skill_preserves_token_when_not_passed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ARI_SKILL_TOKEN_KEY", Fernet.generate_key().decode())
    session = _session(tmp_path)

    skills.register_skill(
        session, name="example-mcp", mcp_url="https://example.com/sse", token="secret"
    )
    updated = skills.register_skill(
        session, name="example-mcp", mcp_url="https://example.com/sse", enabled=False
    )

    assert updated.enabled is False
    assert skills.decrypt_token(updated.encrypted_token) == "secret"


def test_build_mcp_request_args_reflects_enabled_registrations(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ARI_SKILL_TOKEN_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(skills, "PAUSED_FILE", tmp_path / "PAUSED")
    session = _session(tmp_path)

    assert skills.build_mcp_request_args(session) == ([], [])

    skills.register_skill(
        session,
        name="example-mcp",
        mcp_url="https://example-server.modelcontextprotocol.io/sse",
        token="tok",
    )
    mcp_servers, tools = skills.build_mcp_request_args(session)
    assert mcp_servers == [
        {
            "type": "url",
            "url": "https://example-server.modelcontextprotocol.io/sse",
            "name": "example-mcp",
            "authorization_token": "tok",
        }
    ]
    assert tools == [{"type": "mcp_toolset", "mcp_server_name": "example-mcp"}]

    skills.register_skill(
        session,
        name="example-mcp",
        mcp_url="https://example-server.modelcontextprotocol.io/sse",
        enabled=False,
    )
    assert skills.build_mcp_request_args(session) == ([], [])


def test_build_mcp_request_args_returns_nothing_when_paused(monkeypatch, tmp_path) -> None:
    """The kill switch test: this is the *only* enforcement point for
    MCP-sourced calls (see build_mcp_request_args' docstring) -- it can
    only withhold servers from a request that hasn't started yet."""
    monkeypatch.setenv("ARI_SKILL_TOKEN_KEY", Fernet.generate_key().decode())
    paused_file = tmp_path / "PAUSED"
    monkeypatch.setattr(skills, "PAUSED_FILE", paused_file)
    session = _session(tmp_path)

    skills.register_skill(
        session, name="example-mcp", mcp_url="https://example.com/sse", token="tok"
    )
    assert skills.build_mcp_request_args(session) != ([], [])

    paused_file.parent.mkdir(parents=True, exist_ok=True)
    paused_file.write_text("paused_at: now\n")
    assert skills.build_mcp_request_args(session) == ([], [])


def test_record_skill_invocation_persists_a_row(tmp_path) -> None:
    session = _session(tmp_path)

    invocation = skills.record_skill_invocation(
        session,
        channel="imessage",
        skill_kind=SkillKind.MCP,
        skill_name="example-mcp",
        tool_name="echo",
        summary="mcp:example-mcp.echo",
        payload={"input": {"text": "hi"}, "result": "hi"},
        occurred_at=datetime(2026, 6, 19, tzinfo=UTC),
    )

    rows = SkillInvocationRepository(session).list_recent()
    assert len(rows) == 1
    assert rows[0].id == invocation.id
    assert rows[0].skill_kind == SkillKind.MCP
    assert rows[0].is_error is False


def test_extract_resolved_skill_invocations_pairs_web_search_blocks() -> None:
    content = [
        {"type": "text", "text": "let me check"},
        {
            "type": "server_tool_use",
            "id": "srvtoolu_1",
            "name": "web_search",
            "input": {"query": "today's weather"},
        },
        {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_1",
            "content": [{"type": "web_search_result", "title": "Weather", "url": "https://x"}],
        },
    ]

    invocations = skills.extract_resolved_skill_invocations(content)

    assert len(invocations) == 1
    assert invocations[0]["skill_kind"] == SkillKind.WEB_SEARCH
    assert invocations[0]["tool_name"] == "web_search"
    assert invocations[0]["is_error"] is False


def test_extract_resolved_skill_invocations_flags_web_search_error() -> None:
    content = [
        {
            "type": "server_tool_use",
            "id": "srvtoolu_2",
            "name": "web_search",
            "input": {"query": "x"},
        },
        {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_2",
            "content": {"type": "web_search_tool_result_error", "error_code": "rate_limited"},
        },
    ]

    invocations = skills.extract_resolved_skill_invocations(content)

    assert invocations[0]["is_error"] is True


def test_extract_resolved_skill_invocations_pairs_mcp_blocks() -> None:
    content = [
        {
            "type": "mcp_tool_use",
            "id": "mcptoolu_1",
            "name": "echo",
            "server_name": "example-mcp",
            "input": {"text": "hi"},
        },
        {
            "type": "mcp_tool_result",
            "tool_use_id": "mcptoolu_1",
            "is_error": False,
            "content": "hi",
        },
    ]

    invocations = skills.extract_resolved_skill_invocations(content)

    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation["skill_kind"] == SkillKind.MCP
    assert invocation["skill_name"] == "example-mcp"
    assert invocation["tool_name"] == "echo"
    assert invocation["is_error"] is False
    assert invocation["payload"] == {"input": {"text": "hi"}, "result": "hi"}


def test_extract_resolved_skill_invocations_flags_mcp_error() -> None:
    content = [
        {
            "type": "mcp_tool_use",
            "id": "mcptoolu_2",
            "name": "echo",
            "server_name": "example-mcp",
            "input": {},
        },
        {
            "type": "mcp_tool_result",
            "tool_use_id": "mcptoolu_2",
            "is_error": True,
            "content": "boom",
        },
    ]

    invocations = skills.extract_resolved_skill_invocations(content)

    assert invocations[0]["is_error"] is True


def test_extract_resolved_skill_invocations_ignores_custom_tool_use() -> None:
    content = [
        {"type": "tool_use", "id": "toolu_1", "name": "get_open_loops", "input": {}},
    ]

    assert skills.extract_resolved_skill_invocations(content) == []
