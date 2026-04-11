from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

JSONDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class HubAPIError(Exception):
    status_code: int
    detail: str


class OrchestrationHistoryClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def get_latest_run(self, *, state_date: date) -> JSONDict:
        return self._fetch("/orchestration-runs/latest", state_date=state_date)

    def compare_latest_two_runs(self, *, state_date: date) -> JSONDict:
        return self._fetch("/orchestration-runs/compare-latest-two", state_date=state_date)

    def get_current_daily_state(self, *, state_date: date) -> JSONDict:
        return self._fetch("/daily-states/current", state_date=state_date)

    def get_current_weekly_state(self, *, state_date: date) -> JSONDict:
        return self._fetch("/weekly-states/current", state_date=state_date)

    def get_active_open_loops(self) -> JSONDict:
        return self._fetch("/open-loops/active")

    def _fetch(self, path: str, *, state_date: date | None = None) -> JSONDict:
        url = f"{self._base_url}{path}"
        if state_date is not None:
            query = urlencode({"state_date": state_date.isoformat()})
            url = f"{url}?{query}"
        try:
            with urlopen(url) as response:
                return json.load(response)
        except HTTPError as error:
            detail = _extract_error_detail(error)
            raise HubAPIError(status_code=error.code, detail=detail) from error


def create_app(api_client: OrchestrationHistoryClient | None = None) -> FastAPI:
    resolved_client = api_client or OrchestrationHistoryClient(_api_base_url())
    app = FastAPI(title="ARI Hub", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def hub_home(
        state_date: date | None = Query(default=None),  # noqa: B008
    ) -> HTMLResponse:
        resolved_state_date = state_date or date.today()
        try:
            latest_run = resolved_client.get_latest_run(state_date=resolved_state_date)
        except HubAPIError as error:
            return HTMLResponse(
                content=render_hub_page(
                    state_date=resolved_state_date,
                    latest_run=None,
                    comparison=None,
                    daily_state=None,
                    weekly_state=None,
                    active_open_loops=None,
                    latest_error=error.detail,
                    comparison_error=None,
                    daily_state_error=None,
                    weekly_state_error=None,
                    active_open_loops_error=None,
                ),
                status_code=error.status_code,
            )

        comparison: JSONDict | None = None
        daily_state: JSONDict | None = None
        weekly_state: JSONDict | None = None
        active_open_loops: JSONDict | None = None
        comparison_error: str | None = None
        daily_state_error: str | None = None
        weekly_state_error: str | None = None
        active_open_loops_error: str | None = None
        try:
            comparison = resolved_client.compare_latest_two_runs(state_date=resolved_state_date)
        except HubAPIError as error:
            comparison_error = error.detail
        try:
            daily_state = resolved_client.get_current_daily_state(
                state_date=resolved_state_date
            )
        except HubAPIError as error:
            daily_state_error = error.detail
        try:
            weekly_state = resolved_client.get_current_weekly_state(
                state_date=resolved_state_date
            )
        except HubAPIError as error:
            weekly_state_error = error.detail
        try:
            active_open_loops = resolved_client.get_active_open_loops()
        except HubAPIError as error:
            active_open_loops_error = error.detail

        return HTMLResponse(
            content=render_hub_page(
                state_date=resolved_state_date,
                latest_run=latest_run,
                comparison=comparison,
                daily_state=daily_state,
                weekly_state=weekly_state,
                active_open_loops=active_open_loops,
                latest_error=None,
                comparison_error=comparison_error,
                daily_state_error=daily_state_error,
                weekly_state_error=weekly_state_error,
                active_open_loops_error=active_open_loops_error,
            )
        )

    return app


def render_hub_page(
    *,
    state_date: date,
    latest_run: JSONDict | None,
    comparison: JSONDict | None,
    daily_state: JSONDict | None,
    weekly_state: JSONDict | None,
    active_open_loops: JSONDict | None,
    latest_error: str | None,
    comparison_error: str | None,
    daily_state_error: str | None,
    weekly_state_error: str | None,
    active_open_loops_error: str | None,
) -> str:
    sections = [
        _render_latest_section(latest_run=latest_run, latest_error=latest_error),
        _render_comparison_section(
            comparison=comparison,
            comparison_error=comparison_error,
        ),
        _render_daily_state_section(
            daily_state=daily_state,
            daily_state_error=daily_state_error,
        ),
        _render_weekly_state_section(
            weekly_state=weekly_state,
            weekly_state_error=weekly_state_error,
        ),
        _render_open_loops_section(
            active_open_loops=active_open_loops,
            active_open_loops_error=active_open_loops_error,
        ),
        _render_signals_section(comparison=comparison, latest_run=latest_run),
        _render_alerts_section(comparison=comparison, latest_run=latest_run),
    ]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ARI Hub</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Georgia, "Times New Roman", serif;
      --bg: #f5f3ef;
      --card: #fbfaf8;
      --line: #d8d0c5;
      --text: #1f1d1a;
      --muted: #6c655d;
      --accent: #264653;
      --soft: #e8e2d8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    header {{
      margin-bottom: 24px;
    }}
    h1, h2, h3 {{
      margin: 0 0 12px;
      font-weight: 600;
    }}
    h1 {{
      font-size: 2rem;
    }}
    h2 {{
      font-size: 1.15rem;
      color: var(--accent);
    }}
    p, li, dt, dd, label, input {{
      font-size: 0.98rem;
      line-height: 1.45;
    }}
    form {{
      display: flex;
      gap: 12px;
      align-items: end;
      flex-wrap: wrap;
      margin-top: 16px;
    }}
    input {{
      border: 1px solid var(--line);
      background: white;
      padding: 10px 12px;
    }}
    button {{
      border: 1px solid var(--accent);
      background: var(--accent);
      color: white;
      padding: 10px 14px;
      cursor: pointer;
    }}
    section {{
      background: var(--card);
      border: 1px solid var(--line);
      padding: 18px;
      margin-top: 16px;
    }}
    .grid {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }}
    dl {{
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 8px 12px;
      margin: 0;
    }}
    dt {{
      color: var(--muted);
    }}
    dd {{
      margin: 0;
      word-break: break-word;
    }}
    ul {{
      margin: 8px 0 0;
      padding-left: 18px;
    }}
    .muted {{
      color: var(--muted);
    }}
    .pill {{
      display: inline-block;
      padding: 2px 8px;
      border: 1px solid var(--line);
      background: var(--soft);
      margin-right: 6px;
      margin-bottom: 6px;
      font-size: 0.9rem;
    }}
    .empty {{
      color: var(--muted);
      font-style: italic;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <p class="muted">Read-only hub view over the orchestration history API.</p>
      <h1>ARI Hub</h1>
      <form method="get">
        <label>
          State date
          <br>
          <input type="date" name="state_date" value="{escape(state_date.isoformat())}">
        </label>
        <button type="submit">Load</button>
      </form>
    </header>
    {''.join(sections)}
  </main>
</body>
</html>"""


def _render_latest_section(*, latest_run: JSONDict | None, latest_error: str | None) -> str:
    if latest_run is None:
        return _render_section(
            "Latest Run",
            f'<p class="empty">{escape(latest_error or "No orchestration run found.")}</p>',
        )

    run = latest_run["run"]
    return _render_section(
        "Latest Run",
        _render_run_summary(run, prefix="Latest")
        + _render_id_list("Linked signal ids", run["signal_ids"])
        + _render_id_list("Linked alert ids", run["alert_ids"]),
    )


def _render_comparison_section(
    *,
    comparison: JSONDict | None,
    comparison_error: str | None,
) -> str:
    if comparison is None:
        message = comparison_error or "No comparison available for this state date."
        return _render_section(
            "Latest vs Previous",
            f'<p class="empty">{escape(message)}</p>',
        )

    return _render_section(
        "Latest vs Previous",
        '<div class="grid">'
        f"{_render_run_summary(comparison['latest_run'], prefix='Latest')}"
        f"{_render_run_summary(comparison['previous_run'], prefix='Previous')}"
        "</div>"
        "<div style=\"margin-top: 16px;\">"
        + _render_bool("State fingerprint changed", comparison["state_fingerprint_changed"])
        + _render_id_list("Reused signal ids", comparison["reused_signal_ids"])
        + _render_id_list("New signal ids", comparison["new_signal_ids"])
        + _render_id_list("Reused alert ids", comparison["reused_alert_ids"])
        + _render_id_list("New alert ids", comparison["new_alert_ids"])
        + "</div>",
    )


def _render_signals_section(
    *,
    comparison: JSONDict | None,
    latest_run: JSONDict | None,
) -> str:
    signals = comparison["signals"] if comparison is not None else _list_from(latest_run, "signals")
    classification = _classification_map(
        reused_ids=_list_from(comparison, "reused_signal_ids"),
        new_ids=_list_from(comparison, "new_signal_ids"),
    )
    return _render_section(
        "Linked Signals",
        _render_entity_list(
            entities=signals,
            classification=classification,
            title_key="summary",
            subtitle_builder=lambda signal: (
                f"{signal['kind']} | severity {signal['severity']} | {signal['id']}"
            ),
            body_builder=lambda signal: (
                f"<p>{escape(signal['reason'])}</p>"
                f"{_render_evidence_list(signal['evidence'])}"
            ),
        ),
    )


def _render_daily_state_section(
    *,
    daily_state: JSONDict | None,
    daily_state_error: str | None,
) -> str:
    if daily_state is None:
        return _render_section(
            "Current Operational State",
            f'<p class="empty">{escape(daily_state_error or "No daily state found.")}</p>',
        )

    movement = daily_state["movement"]
    if movement is True:
        movement_label = "recorded"
    elif movement is False:
        movement_label = "not recorded"
    else:
        movement_label = "unknown"
    stress_label = "unknown" if daily_state["stress"] is None else str(daily_state["stress"])
    win_condition = escape(daily_state["win_condition"])
    next_action = escape(daily_state["next_action"])
    return _render_section(
        "Current Operational State",
        "<dl>"
        f"<dt>State date</dt><dd>{escape(daily_state['date'])}</dd>"
        f"<dt>Top priorities</dt><dd>{_render_inline_list(daily_state['priorities'])}</dd>"
        f"<dt>Win condition</dt><dd>{win_condition or _empty_inline('None set.')}</dd>"
        f"<dt>Movement</dt><dd>{escape(movement_label)}</dd>"
        f"<dt>Stress</dt><dd>{escape(stress_label)}</dd>"
        f"<dt>Next action</dt><dd>{next_action or _empty_inline('None set.')}</dd>"
        f"<dt>Last check</dt><dd>{escape(daily_state['last_check_at'] or 'unknown')}</dd>"
        "</dl>",
    )


def _render_weekly_state_section(
    *,
    weekly_state: JSONDict | None,
    weekly_state_error: str | None,
) -> str:
    if weekly_state is None:
        return _render_section(
            "Weekly Trajectory",
            f'<p class="empty">{escape(weekly_state_error or "No weekly state found.")}</p>',
        )

    lesson = escape(weekly_state["lesson"])
    return _render_section(
        "Weekly Trajectory",
        "<dl>"
        f"<dt>Week start</dt><dd>{escape(weekly_state['week_start'])}</dd>"
        f"<dt>Outcomes</dt><dd>{_render_inline_list(weekly_state['outcomes'])}</dd>"
        f"<dt>Cannot drift</dt><dd>{_render_inline_list(weekly_state['cannot_drift'])}</dd>"
        f"<dt>Blockers</dt><dd>{_render_inline_list(weekly_state['blockers'])}</dd>"
        f"<dt>Lesson</dt><dd>{lesson or _empty_inline('None captured.')}</dd>"
        f"<dt>Last review</dt><dd>{escape(weekly_state['last_review_at'] or 'unknown')}</dd>"
        "</dl>",
    )


def _render_open_loops_section(
    *,
    active_open_loops: JSONDict | None,
    active_open_loops_error: str | None,
) -> str:
    if active_open_loops is None:
        return _render_section(
            "Active Open Loops",
            f'<p class="empty">{escape(active_open_loops_error or "No open loops available.")}</p>',
        )

    loops = _list_from(active_open_loops, "loops")
    if not loops:
        return _render_section(
            "Active Open Loops",
            '<p class="empty">No active open loops.</p>',
        )

    items = []
    for loop in loops:
        due_at = loop["due_at"] or "none"
        last_touched = loop["last_touched_at"] or "unknown"
        notes = escape(loop["notes"]) if loop["notes"] else _empty_inline("No notes.")
        subtitle = (
            f'{escape(loop["priority"])} | '
            f'{escape(loop["kind"])} | '
            f'{escape(loop["status"])}'
        )
        items.append(
            "<article>"
            f"<h3>{escape(loop['title'])}</h3>"
            f'<p class="muted">{subtitle}</p>'
            "<dl>"
            f"<dt>Source</dt><dd>{escape(loop['source'])}</dd>"
            f"<dt>Opened</dt><dd>{escape(loop['opened_at'])}</dd>"
            f"<dt>Due</dt><dd>{escape(due_at)}</dd>"
            f"<dt>Last touched</dt><dd>{escape(last_touched)}</dd>"
            f"<dt>Project id</dt><dd>{escape(loop['project_id'] or 'none')}</dd>"
            f"<dt>Notes</dt><dd>{notes}</dd>"
            "</dl>"
            "</article>"
        )
    return _render_section("Active Open Loops", "".join(items))


def _render_alerts_section(
    *,
    comparison: JSONDict | None,
    latest_run: JSONDict | None,
) -> str:
    alerts = comparison["alerts"] if comparison is not None else _list_from(latest_run, "alerts")
    classification = _classification_map(
        reused_ids=_list_from(comparison, "reused_alert_ids"),
        new_ids=_list_from(comparison, "new_alert_ids"),
    )
    return _render_section(
        "Linked Alerts",
        _render_entity_list(
            entities=alerts,
            classification=classification,
            title_key="title",
            subtitle_builder=lambda alert: (
                f"{alert['status']} | {alert['channel']} | {alert['id']}"
            ),
            body_builder=lambda alert: (
                f"<p>{escape(alert['message'])}</p>"
                f"<p class=\"muted\">Reason: {escape(alert['reason'])}</p>"
                f"{_render_id_list('Source signal ids', alert['source_signal_ids'])}"
            ),
        ),
    )


def _render_run_summary(run: JSONDict, *, prefix: str) -> str:
    return (
        "<section>"
        f"<h3>{escape(prefix)} Summary</h3>"
        "<dl>"
        f"<dt>Run id</dt><dd>{escape(run['run_id'])}</dd>"
        f"<dt>Executed at</dt><dd>{escape(run['executed_at'])}</dd>"
        f"<dt>State date</dt><dd>{escape(run['state_date'])}</dd>"
        f"<dt>State fingerprint</dt><dd>{escape(run['state_fingerprint'])}</dd>"
        f"<dt>Signal count</dt><dd>{len(run['signal_ids'])}</dd>"
        f"<dt>Alert count</dt><dd>{len(run['alert_ids'])}</dd>"
        "</dl>"
        "</section>"
    )


def _render_entity_list(
    *,
    entities: list[JSONDict],
    classification: dict[str, str],
    title_key: str,
    subtitle_builder: Callable[[JSONDict], str],
    body_builder: Callable[[JSONDict], str],
) -> str:
    if not entities:
        return '<p class="empty">None linked.</p>'

    items = []
    for entity in entities:
        entity_id = entity["id"]
        status = classification.get(entity_id, "latest")
        items.append(
            "<article>"
            f"<h3>{escape(entity[title_key])}</h3>"
            f'<p class="muted">{escape(subtitle_builder(entity))}</p>'
            f'<p><span class="pill">{escape(status)}</span></p>'
            f"{body_builder(entity)}"
            "</article>"
        )
    return "".join(items)


def _render_evidence_list(evidence: list[JSONDict]) -> str:
    if not evidence:
        return '<p class="empty">No evidence attached.</p>'
    items = "".join(
        f"<li>{escape(item['kind'])}: {escape(item['summary'])}</li>" for item in evidence
    )
    return f"<p class=\"muted\">Evidence</p><ul>{items}</ul>"


def _render_section(title: str, body: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


def _render_bool(label: str, value: bool) -> str:
    status = "yes" if value else "no"
    return f"<p><strong>{escape(label)}:</strong> {status}</p>"


def _render_id_list(label: str, ids: list[str]) -> str:
    if not ids:
        return f"<p><strong>{escape(label)}:</strong> none</p>"
    pills = "".join(f'<span class="pill">{escape(item)}</span>' for item in ids)
    return f"<p><strong>{escape(label)}:</strong></p><div>{pills}</div>"


def _render_inline_list(items: list[str]) -> str:
    if not items:
        return _empty_inline("None.")
    return "".join(f'<span class="pill">{escape(item)}</span>' for item in items)


def _classification_map(*, reused_ids: list[str], new_ids: list[str]) -> dict[str, str]:
    classification = {entity_id: "reused" for entity_id in reused_ids}
    classification.update({entity_id: "new" for entity_id in new_ids})
    return classification


def _list_from(payload: JSONDict | None, key: str) -> list[Any]:
    if payload is None:
        return []
    value = payload.get(key, [])
    return value if isinstance(value, list) else []


def _extract_error_detail(error: HTTPError) -> str:
    try:
        payload = json.load(error)
    except json.JSONDecodeError:
        return f"Hub API request failed with status {error.code}."
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail
    return f"Hub API request failed with status {error.code}."


def _api_base_url() -> str:
    return os.environ.get("ARI_API_BASE_URL", "http://localhost:8000")


def _empty_inline(message: str) -> str:
    return f'<span class="empty">{escape(message)}</span>'
