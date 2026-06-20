"""Generic skill registry for ARI's brain: registering a new MCP-backed
skill (e.g. Google Calendar) becomes a Postgres row plus an OAuth token,
not a code change. This module is also the only place skill invocations
get audited, regardless of whether the call went through dispatch_tool
(custom tools) or was resolved server-side by Anthropic (web_search, MCP).

Read build_mcp_request_args and record_skill_invocation's docstrings
before assuming either does more than it actually does. Both have a real,
narrow limit that comes from how MCP and web_search execute -- not a gap
to be quietly fixed later.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ari_memory import SkillInvocationRepository, SkillRegistrationRepository
from ari_state import SkillInvocation, SkillKind, SkillRegistration, SkillRegistrationKind
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

MCP_BETA_HEADER = "mcp-client-2025-11-20"

# services/ never imports from scripts/ in this codebase (see executor.py's
# own REPO_ROOT) -- this duplicates the constant rather than importing
# scripts/_ari_common.py, but points at the exact same file
# scripts/ari-killswitch.sh writes.
REPO_ROOT = Path(__file__).resolve().parents[4]
PAUSED_FILE = REPO_ROOT / "state" / "PAUSED"


def _fernet() -> Fernet:
    key = os.environ.get("ARI_SKILL_TOKEN_KEY")
    if not key:
        raise RuntimeError(
            "ARI_SKILL_TOKEN_KEY is not set -- required to encrypt/decrypt skill "
            "OAuth tokens. Generate one with: python -c \"from cryptography.fernet "
            "import Fernet; print(Fernet.generate_key().decode())\" and put it in .env."
        )
    return Fernet(key.encode())


def encrypt_token(plaintext_token: str) -> str:
    return _fernet().encrypt(plaintext_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    return _fernet().decrypt(encrypted_token.encode()).decode()


def register_skill(
    session: Session,
    *,
    name: str,
    mcp_url: str,
    token: str | None = None,
    enabled: bool = True,
) -> SkillRegistration:
    """Register or update an MCP-backed skill. `token`, if given, is a
    plaintext OAuth bearer token -- it is encrypted before it is ever held
    on a SkillRegistration model or written to Postgres. Passing token=None
    leaves an existing encrypted token untouched (e.g. when just flipping
    `enabled`)."""
    repository = SkillRegistrationRepository(session)
    existing = repository.get_by_name(name)
    now = datetime.now(tz=UTC)
    registration = SkillRegistration(
        id=existing.id if existing else uuid4(),
        name=name,
        kind=SkillRegistrationKind.MCP,
        mcp_url=mcp_url,
        enabled=enabled,
        encrypted_token=(
            encrypt_token(token)
            if token is not None
            else (existing.encrypted_token if existing else None)
        ),
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    result = repository.upsert(registration)
    session.commit()
    return result


def build_mcp_request_args(
    session: Session,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the (mcp_servers, tools) arguments for an Anthropic Messages
    API call from every enabled skill registration. Returns ([], []) if
    there are none, in which case the caller should fall back to the plain
    (non-beta) Messages API call unchanged -- see brain.respond_to_message.

    KILL SWITCH NOTE -- read before assuming this is per-call enforcement:
    once an MCP server is attached to a request, Anthropic resolves any
    tool call against it server-side, inside that same API call. ARI's
    process never gets a "the model wants to call X, allow it?" moment for
    an MCP tool the way dispatch_tool gets one for a custom tool. So the
    only lever ARI has is whether to attach the server to the *next*
    request at all -- this function checks the same state/PAUSED file
    scripts/ari-killswitch.sh writes and returns nothing if paused. That
    stops a future request from offering any MCP tool. It cannot abort a
    call already in flight inside a request that started before the
    pause -- no design can, given how MCP resolves. This is a coarser
    guarantee than dispatch_tool's per-call gating, not an equivalent one.
    """
    if PAUSED_FILE.exists():
        return [], []

    registrations = SkillRegistrationRepository(session).list_enabled()
    mcp_servers: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    for registration in registrations:
        server: dict[str, Any] = {
            "type": "url",
            "url": registration.mcp_url,
            "name": registration.name,
        }
        if registration.encrypted_token:
            server["authorization_token"] = decrypt_token(registration.encrypted_token)
        mcp_servers.append(server)
        tools.append({"type": "mcp_toolset", "mcp_server_name": registration.name})
    return mcp_servers, tools


def record_skill_invocation(
    session: Session,
    *,
    channel: str,
    skill_kind: SkillKind,
    skill_name: str,
    tool_name: str,
    summary: str,
    payload: dict[str, Any],
    is_error: bool = False,
    occurred_at: datetime | None = None,
) -> SkillInvocation:
    """Write one audit row for a single skill call.

    AUDIT NOTE -- this is detective, not preventive: by the time this is
    called, the call already happened. For SkillKind.CUSTOM_TOOL it runs
    right after dispatch_tool returns, in brain.respond_to_message -- a
    one-function-call trail behind execution. For SkillKind.WEB_SEARCH and
    SkillKind.MCP, Anthropic resolved the call server-side before the
    response ever reached ARI's process; there was never a point at which
    this function, or anything else in ARI, could have said no. "Audited"
    here means ARI has a durable record that the call happened, not that
    ARI approved it before it happened. Whatever authorization exists for
    those two kinds is entirely in what's offered to the model in the
    first place (build_mcp_request_args, WEB_SEARCH_TOOL) -- not at
    call time.
    """
    invocation = SkillInvocation(
        occurred_at=occurred_at or datetime.now(tz=UTC),
        channel=channel,
        skill_kind=skill_kind,
        skill_name=skill_name,
        tool_name=tool_name,
        summary=summary,
        payload=payload,
        is_error=is_error,
    )
    result = SkillInvocationRepository(session).create(invocation)
    session.commit()
    return result


def extract_resolved_skill_invocations(
    content_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pure function (no DB, no network): scan one assistant turn's content
    blocks for invocations Anthropic already resolved server-side --
    web search (`server_tool_use` name="web_search" / `web_search_tool_result`)
    and MCP (`mcp_tool_use` / `mcp_tool_result`) -- and pair each call with
    its result by id. Returns plain dicts shaped as kwargs for
    record_skill_invocation (minus `session`/`channel`).

    Deliberately excludes `tool_use` blocks for custom tools: those are
    logged inline in brain.respond_to_message right after dispatch_tool
    returns, where the result is already known locally and there's nothing
    to pair by id here.
    """
    results_by_id: dict[str, dict[str, Any]] = {}
    for block in content_blocks:
        if block.get("type") in ("web_search_tool_result", "mcp_tool_result"):
            tool_use_id = block.get("tool_use_id")
            if tool_use_id is not None:
                results_by_id[tool_use_id] = block

    invocations: list[dict[str, Any]] = []
    for block in content_blocks:
        block_type = block.get("type")

        if block_type == "server_tool_use" and block.get("name") == "web_search":
            result = results_by_id.get(block.get("id", ""), {})
            content = result.get("content")
            is_error = isinstance(content, dict) and content.get("type") == (
                "web_search_tool_result_error"
            )
            invocations.append(
                {
                    "skill_kind": SkillKind.WEB_SEARCH,
                    "skill_name": "web_search",
                    "tool_name": "web_search",
                    "summary": f"web_search: {block.get('input', {}).get('query', '')}",
                    "payload": {"input": block.get("input"), "result": content},
                    "is_error": is_error,
                }
            )

        elif block_type == "mcp_tool_use":
            server_name = block.get("server_name", "unknown-mcp-server")
            tool_name = block.get("name", "unknown-tool")
            result = results_by_id.get(block.get("id", ""), {})
            invocations.append(
                {
                    "skill_kind": SkillKind.MCP,
                    "skill_name": server_name,
                    "tool_name": tool_name,
                    "summary": f"mcp:{server_name}.{tool_name}",
                    "payload": {"input": block.get("input"), "result": result.get("content")},
                    "is_error": bool(result.get("is_error", False)),
                }
            )

    return invocations
