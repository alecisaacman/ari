"""Standalone web-search skill: research a company's recent layoffs, hiring
freezes, funding news, and interview-process signals. Unlike the web_search
tool inside brain.py (invoked at Claude's discretion mid-conversation), this
is a direct callable so the job_application enrichment trigger in
ari_core.state can fire it outside of any chat turn."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import anthropic

RESEARCH_MODEL = os.environ.get("ARI_BRAIN_MODEL", "claude-sonnet-4-6")

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 4,
}

RESEARCH_SYSTEM_PROMPT = """You research companies for someone evaluating a job \
application. Use web search to find recent, dated information — prioritize the \
last 3-6 months. Look specifically for: layoffs, hiring freezes, funding rounds \
or financial distress, and Glassdoor/interview-process signals.

Respond with ONLY a single JSON object, no markdown fences, no commentary, \
matching this shape:
{
  "summary": "one or two sentence rollup of what you found",
  "findings": [
    {
      "category": "layoffs" | "hiring_freeze" | "funding" | "interview_process" | "other",
      "summary": "what you found, specific and dated",
      "source_url": "the URL you found it at, or null",
      "published_at": "ISO date if known, or null"
    }
  ]
}
If you find nothing notable for a category, omit it rather than inventing a \
finding. If search turns up nothing at all, return an empty findings list and \
say so plainly in the summary — do not guess."""


@dataclass(frozen=True, slots=True)
class CompanyResearchFinding:
    category: str
    summary: str
    source_url: str | None = None
    published_at: str | None = None


@dataclass(frozen=True, slots=True)
class CompanyResearchResult:
    company: str
    summary: str
    findings: list[CompanyResearchFinding] = field(default_factory=list)
    raw_response_text: str = ""


def research_company(company: str, *, model: str = RESEARCH_MODEL) -> CompanyResearchResult:
    """Run one web-search research pass on a company. Raises on API/network
    failure — the caller decides how to record that as a failed skill
    invocation rather than this function swallowing it silently."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system=RESEARCH_SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[
            {
                "role": "user",
                "content": f"Research {company} for someone considering a job application there.",
            }
        ],
    )
    final_text = "".join(block.text for block in response.content if block.type == "text").strip()
    return _parse_research_response(company=company, raw_text=final_text)


def _parse_research_response(*, company: str, raw_text: str) -> CompanyResearchResult:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return CompanyResearchResult(
            company=company,
            summary=raw_text[:500],
            findings=[],
            raw_response_text=raw_text,
        )

    findings = [
        CompanyResearchFinding(
            category=item.get("category", "other"),
            summary=item.get("summary", ""),
            source_url=item.get("source_url"),
            published_at=item.get("published_at"),
        )
        for item in data.get("findings", [])
        if isinstance(item, dict)
    ]
    return CompanyResearchResult(
        company=company,
        summary=data.get("summary", ""),
        findings=findings,
        raw_response_text=raw_text,
    )
