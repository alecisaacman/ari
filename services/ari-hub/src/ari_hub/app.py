from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any, Protocol, cast
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import FastAPI, Query
from fastapi import Request as FastAPIRequest
from fastapi.responses import HTMLResponse, RedirectResponse, Response

JSONDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class HubAPIError(Exception):
    status_code: int
    detail: str


class HubAPIClient(Protocol):
    def get_latest_run(self, *, state_date: date) -> JSONDict: ...

    def compare_latest_two_runs(self, *, state_date: date) -> JSONDict: ...

    def get_current_daily_state(self, *, state_date: date) -> JSONDict: ...

    def get_current_weekly_state(self, *, state_date: date) -> JSONDict: ...

    def get_active_open_loops(self) -> JSONDict: ...

    def get_signal_detail(self, *, signal_id: UUID) -> JSONDict: ...

    def get_alert_detail(self, *, alert_id: UUID) -> JSONDict: ...

    def update_daily_state(self, *, state_date: date, payload: JSONDict) -> JSONDict: ...

    def update_weekly_plan(self, *, state_date: date, payload: JSONDict) -> JSONDict: ...

    def update_weekly_reflection(
        self,
        *,
        state_date: date,
        payload: JSONDict,
    ) -> JSONDict: ...

    def add_open_loop(self, *, payload: JSONDict) -> JSONDict: ...

    def resolve_open_loop(self, *, loop_id: UUID, payload: JSONDict) -> JSONDict: ...


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

    def get_signal_detail(self, *, signal_id: UUID) -> JSONDict:
        return self._fetch(f"/signals/{signal_id}")

    def get_alert_detail(self, *, alert_id: UUID) -> JSONDict:
        return self._fetch(f"/alerts/{alert_id}")

    def update_daily_state(self, *, state_date: date, payload: JSONDict) -> JSONDict:
        return self._send_json(
            "/daily-states/current",
            method="PUT",
            payload=payload,
            state_date=state_date,
        )

    def update_weekly_plan(self, *, state_date: date, payload: JSONDict) -> JSONDict:
        return self._send_json(
            "/weekly-states/plan",
            method="PUT",
            payload=payload,
            state_date=state_date,
        )

    def update_weekly_reflection(self, *, state_date: date, payload: JSONDict) -> JSONDict:
        return self._send_json(
            "/weekly-states/reflection",
            method="PUT",
            payload=payload,
            state_date=state_date,
        )

    def add_open_loop(self, *, payload: JSONDict) -> JSONDict:
        return self._send_json("/open-loops", method="POST", payload=payload)

    def resolve_open_loop(self, *, loop_id: UUID, payload: JSONDict) -> JSONDict:
        return self._send_json(
            f"/open-loops/{loop_id}/resolve",
            method="POST",
            payload=payload,
        )

    def _fetch(self, path: str, *, state_date: date | None = None) -> JSONDict:
        return self._request(path, state_date=state_date)

    def _send_json(
        self,
        path: str,
        *,
        method: str,
        payload: JSONDict,
        state_date: date | None = None,
    ) -> JSONDict:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self._build_url(path, state_date=state_date),
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        return self._request(path, request=request, state_date=state_date)

    def _request(
        self,
        path: str,
        *,
        request: Request | None = None,
        state_date: date | None = None,
    ) -> JSONDict:
        resolved_request: str | Request = request or self._build_url(
            path,
            state_date=state_date,
        )
        try:
            with urlopen(resolved_request) as response:
                return cast(JSONDict, json.load(response))
        except HTTPError as error:
            detail = _extract_error_detail(error)
            raise HubAPIError(status_code=error.code, detail=detail) from error

    def _build_url(self, path: str, *, state_date: date | None = None) -> str:
        url = f"{self._base_url}{path}"
        if state_date is not None:
            query = urlencode({"state_date": state_date.isoformat()})
            url = f"{url}?{query}"
        return url


def create_app(api_client: HubAPIClient | None = None) -> FastAPI:
    resolved_client = api_client or OrchestrationHistoryClient(_api_base_url())
    app = FastAPI(title="ARI Hub", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def hub_home(
        state_date: date | None = Query(default=None),  # noqa: B008
        signal_id: UUID | None = Query(default=None),  # noqa: B008
        alert_id: UUID | None = Query(default=None),  # noqa: B008
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
                selected_signal=None,
                signal_detail_error=None,
                selected_alert=None,
                source_signals=[],
                alert_detail_error=None,
            ),
            status_code=error.status_code,
        )

        comparison: JSONDict | None = None
        daily_state: JSONDict | None = None
        weekly_state: JSONDict | None = None
        active_open_loops: JSONDict | None = None
        selected_signal: JSONDict | None = None
        selected_alert: JSONDict | None = None
        source_signals: list[JSONDict] = []
        comparison_error: str | None = None
        daily_state_error: str | None = None
        weekly_state_error: str | None = None
        active_open_loops_error: str | None = None
        signal_detail_error: str | None = None
        alert_detail_error: str | None = None
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
        if signal_id is not None:
            try:
                selected_signal = resolved_client.get_signal_detail(signal_id=signal_id)
            except HubAPIError as error:
                signal_detail_error = error.detail
        if alert_id is not None:
            try:
                selected_alert = resolved_client.get_alert_detail(alert_id=alert_id)
            except HubAPIError as error:
                alert_detail_error = error.detail
            else:
                for source_signal_id in _list_from(selected_alert, "source_signal_ids"):
                    try:
                        source_signals.append(
                            resolved_client.get_signal_detail(
                                signal_id=UUID(str(source_signal_id))
                            )
                        )
                    except (HubAPIError, ValueError):
                        continue

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
                selected_signal=selected_signal,
                signal_detail_error=signal_detail_error,
                selected_alert=selected_alert,
                source_signals=source_signals,
                alert_detail_error=alert_detail_error,
            )
        )

    @app.post("/actions/daily-state")
    async def write_daily_state_action(request: FastAPIRequest) -> Response:
        form = await _parse_form_body(request)
        state_date = date.fromisoformat(_required_str(form, "state_date"))
        try:
            resolved_client.update_daily_state(
                state_date=state_date,
                payload={
                    "priorities": _split_lines(form.get("priorities")),
                    "win_condition": _optional_str(form.get("win_condition")),
                    "movement": _parse_bool(form.get("movement")),
                    "stress": _parse_int(form.get("stress")),
                    "next_action": _optional_str(form.get("next_action")),
                },
            )
        except (HubAPIError, ValueError) as error:
            return _render_action_error(error, title="Daily state update failed")
        return _redirect_home(state_date=state_date)

    @app.post("/actions/weekly-plan")
    async def write_weekly_plan_action(request: FastAPIRequest) -> Response:
        form = await _parse_form_body(request)
        state_date = date.fromisoformat(_required_str(form, "state_date"))
        try:
            resolved_client.update_weekly_plan(
                state_date=state_date,
                payload={
                    "outcomes": _split_lines(form.get("outcomes")),
                    "cannot_drift": _split_lines(form.get("cannot_drift")),
                    "blockers": _split_lines(form.get("blockers")),
                },
            )
        except (HubAPIError, ValueError) as error:
            return _render_action_error(error, title="Weekly plan update failed")
        return _redirect_home(state_date=state_date)

    @app.post("/actions/weekly-reflection")
    async def write_weekly_reflection_action(
        request: FastAPIRequest,
    ) -> Response:
        form = await _parse_form_body(request)
        state_date = date.fromisoformat(_required_str(form, "state_date"))
        try:
            resolved_client.update_weekly_reflection(
                state_date=state_date,
                payload={
                    "lesson": _required_str(form, "lesson"),
                    "blockers": _split_lines(form.get("blockers")),
                },
            )
        except (HubAPIError, ValueError) as error:
            return _render_action_error(error, title="Weekly reflection update failed")
        return _redirect_home(state_date=state_date)

    @app.post("/actions/open-loops")
    async def add_open_loop_action(request: FastAPIRequest) -> Response:
        form = await _parse_form_body(request)
        state_date = date.fromisoformat(_required_str(form, "state_date"))
        try:
            resolved_client.add_open_loop(
                payload={
                    "title": _required_str(form, "title"),
                    "source": _required_str(form, "source"),
                    "priority": _required_str(form, "priority"),
                    "notes": _optional_str(form.get("notes")) or "",
                }
            )
        except (HubAPIError, ValueError) as error:
            return _render_action_error(error, title="Open loop add failed")
        return _redirect_home(state_date=state_date)

    @app.post("/actions/open-loops/{loop_id}/resolve")
    async def resolve_open_loop_action(
        loop_id: UUID,
        request: FastAPIRequest,
    ) -> Response:
        form = await _parse_form_body(request)
        state_date = date.fromisoformat(_required_str(form, "state_date"))
        try:
            resolved_client.resolve_open_loop(loop_id=loop_id, payload={})
        except (HubAPIError, ValueError) as error:
            return _render_action_error(error, title="Open loop resolve failed")
        return _redirect_home(state_date=state_date)

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
    selected_signal: JSONDict | None,
    signal_detail_error: str | None,
    selected_alert: JSONDict | None,
    source_signals: list[JSONDict],
    alert_detail_error: str | None,
) -> str:
    sections = [
        _render_latest_section(latest_run=latest_run, latest_error=latest_error),
        _render_comparison_section(
            comparison=comparison,
            comparison_error=comparison_error,
        ),
        _render_daily_state_section(
            state_date=state_date,
            daily_state=daily_state,
            daily_state_error=daily_state_error,
        ),
        _render_weekly_state_section(
            state_date=state_date,
            weekly_state=weekly_state,
            weekly_state_error=weekly_state_error,
        ),
        _render_open_loops_section(
            state_date=state_date,
            active_open_loops=active_open_loops,
            active_open_loops_error=active_open_loops_error,
        ),
        _render_signals_section(
            comparison=comparison,
            latest_run=latest_run,
            state_date=state_date,
        ),
        _render_alerts_section(
            comparison=comparison,
            latest_run=latest_run,
            state_date=state_date,
        ),
        _render_signal_detail_section(
            state_date=state_date,
            selected_signal=selected_signal,
            signal_detail_error=signal_detail_error,
        ),
        _render_alert_detail_section(
            state_date=state_date,
            selected_alert=selected_alert,
            source_signals=source_signals,
            alert_detail_error=alert_detail_error,
        ),
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
    p, li, dt, dd, label, input, textarea, select {{
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
    input, textarea, select {{
      border: 1px solid var(--line);
      background: white;
      padding: 10px 12px;
    }}
    textarea {{
      min-width: 240px;
      min-height: 88px;
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
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .evidence-list {{
      list-style: none;
      padding-left: 0;
      margin-top: 12px;
    }}
    .evidence-list li {{
      border-left: 2px solid var(--line);
      padding: 10px 0 10px 12px;
      margin-bottom: 10px;
    }}
    .detail-actions {{
      margin-top: 12px;
    }}
    .inline-form {{
      display: inline-flex;
      margin-top: 12px;
    }}
    .action-block {{
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <p class="muted">API-backed hub view over the canonical orchestration and state API.</p>
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
        + _render_id_list("Linked alert ids", run["alert_ids"])
        + _render_controller_trajectory(run.get("controller_trajectory")),
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
    state_date: date,
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
                f"{_render_related_entity_row(signal)}"
                f"{_render_evidence_list(signal['evidence'])}"
                '<p class="detail-actions">'
                f'<a href="{escape(_detail_href(state_date=state_date, signal_id=signal["id"]))}">'
                "Inspect signal detail</a></p>"
            ),
        ),
    )


def _render_daily_state_section(
    *,
    state_date: date,
    daily_state: JSONDict | None,
    daily_state_error: str | None,
) -> str:
    if daily_state is None:
        return _render_section(
            "Current Operational State",
            f'<p class="empty">{escape(daily_state_error or "No daily state found.")}</p>'
            f"{_render_daily_state_form(state_date=state_date, daily_state=None)}",
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
        "</dl>"
        + _render_daily_state_form(state_date=state_date, daily_state=daily_state),
    )


def _render_weekly_state_section(
    *,
    state_date: date,
    weekly_state: JSONDict | None,
    weekly_state_error: str | None,
) -> str:
    if weekly_state is None:
        return _render_section(
            "Weekly Trajectory",
            f'<p class="empty">{escape(weekly_state_error or "No weekly state found.")}</p>'
            f"{_render_weekly_forms(state_date=state_date, weekly_state=None)}",
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
        "</dl>" + _render_weekly_forms(state_date=state_date, weekly_state=weekly_state),
    )


def _render_open_loops_section(
    *,
    state_date: date,
    active_open_loops: JSONDict | None,
    active_open_loops_error: str | None,
) -> str:
    if active_open_loops is None:
        message = active_open_loops_error or "No open loops available."
        return _render_section(
            "Active Open Loops",
            _render_open_loop_add_form(state_date=state_date)
            + f'<p class="empty">{escape(message)}</p>',
        )

    loops = _list_from(active_open_loops, "loops")
    if not loops:
        return _render_section(
            "Active Open Loops",
            _render_open_loop_add_form(state_date=state_date)
            + '<p class="empty">No active open loops.</p>',
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
            f'{_render_open_loop_resolve_form(state_date=state_date, loop_id=loop["id"])}'
            "</article>"
        )
    return _render_section(
        "Active Open Loops",
        _render_open_loop_add_form(state_date=state_date) + "".join(items),
    )


def _render_alerts_section(
    *,
    comparison: JSONDict | None,
    latest_run: JSONDict | None,
    state_date: date,
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
                f"{_render_signal_link_list(
                    state_date,
                    'Source signal ids',
                    alert['source_signal_ids'],
                )}"
                '<p class="detail-actions">'
                f'<a href="{escape(_detail_href(state_date=state_date, alert_id=alert["id"]))}">'
                "Inspect alert detail</a></p>"
            ),
        ),
    )


def _render_signal_detail_section(
    *,
    state_date: date,
    selected_signal: JSONDict | None,
    signal_detail_error: str | None,
) -> str:
    if selected_signal is None:
        if signal_detail_error is None:
            return ""
        return _render_section(
            "Signal Detail",
            f'<p class="empty">{escape(signal_detail_error)}</p>',
        )

    return _render_section(
        "Signal Detail",
        f"<h3>{escape(selected_signal['summary'])}</h3>"
        f'<p class="muted">{escape(selected_signal["kind"])} | severity '
        f'{escape(selected_signal["severity"])} | {escape(selected_signal["id"])}</p>'
        "<dl>"
        f"<dt>State date</dt><dd>{escape(selected_signal['state_date'] or 'none')}</dd>"
        f"<dt>Detected at</dt><dd>{escape(selected_signal['detected_at'])}</dd>"
        f"<dt>Fingerprint</dt><dd>{escape(selected_signal['fingerprint'])}</dd>"
        f"<dt>Reason</dt><dd>{escape(selected_signal['reason'])}</dd>"
        f"{_render_related_entity_detail_rows(selected_signal)}"
        "</dl>"
        f"{_render_evidence_list(selected_signal['evidence'])}"
        '<p class="detail-actions">'
        f'<a href="{escape(_detail_href(state_date=state_date))}">Clear detail</a></p>',
    )


def _render_alert_detail_section(
    *,
    state_date: date,
    selected_alert: JSONDict | None,
    source_signals: list[JSONDict],
    alert_detail_error: str | None,
) -> str:
    if selected_alert is None:
        if alert_detail_error is None:
            return ""
        return _render_section(
            "Alert Detail",
            f'<p class="empty">{escape(alert_detail_error)}</p>',
        )

    source_signal_chain = (
        _render_entity_list(
            entities=source_signals,
            classification={},
            title_key="summary",
            subtitle_builder=lambda signal: (
                f"{signal['kind']} | severity {signal['severity']} | {signal['id']}"
            ),
            body_builder=lambda signal: (
                f"<p>{escape(signal['reason'])}</p>"
                f"{_render_related_entity_row(signal)}"
                f"{_render_evidence_list(signal['evidence'])}"
            ),
        )
        if source_signals
        else '<p class="empty">No source signal details available.</p>'
    )
    return _render_section(
        "Alert Detail",
        f"<h3>{escape(selected_alert['title'])}</h3>"
        f'<p class="muted">{escape(selected_alert["status"])} | '
        f'{escape(selected_alert["channel"])} | {escape(selected_alert["id"])}</p>'
        "<dl>"
        f"<dt>State date</dt><dd>{escape(selected_alert['state_date'] or 'none')}</dd>"
        f"<dt>Created at</dt><dd>{escape(selected_alert['created_at'])}</dd>"
        f"<dt>Escalation</dt><dd>{escape(selected_alert['escalation_level'])}</dd>"
        f"<dt>Fingerprint</dt><dd>{escape(selected_alert['fingerprint'])}</dd>"
        f"<dt>Reason</dt><dd>{escape(selected_alert['reason'])}</dd>"
        f"<dt>Message</dt><dd>{escape(selected_alert['message'])}</dd>"
        f"<dt>Sent at</dt><dd>{escape(selected_alert['sent_at'] or 'not sent')}</dd>"
        "</dl>"
        f"{_render_signal_link_list(
            state_date,
            'Source signal ids',
            selected_alert['source_signal_ids'],
        )}"
        "<h3>Source Signal Chain</h3>"
        f"{source_signal_chain}"
        '<p class="detail-actions">'
        f'<a href="{escape(_detail_href(state_date=state_date))}">Clear detail</a></p>',
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


def _render_controller_trajectory(trajectory: JSONDict | None) -> str:
    if trajectory is None:
        return "<p><strong>Controller trajectory:</strong> none</p>"
    decision = trajectory["decision"]
    authority = trajectory["authority_result"]
    return (
        "<div class=\"action-block\">"
        "<h3>Controller Trajectory</h3>"
        "<dl>"
        f"<dt>Outcome</dt><dd>{escape(trajectory['controller_outcome'])}</dd>"
        f"<dt>Decision</dt><dd>{escape(decision['decision_summary'])}</dd>"
        f"<dt>Authority</dt><dd>{escape(authority['outcome'])}</dd>"
        f"<dt>Authority reason</dt><dd>{escape(authority['reason'])}</dd>"
        "</dl>"
        "</div>"
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
        "<li>"
        f"<strong>{escape(item['summary'])}</strong>"
        f'<p class="muted">{escape(item["kind"])}</p>'
        f"{_render_entity_reference(item['entity_type'], item['entity_id'])}"
        f"{_render_payload(item['payload'])}"
        "</li>"
        for item in evidence
    )
    return f"<p class=\"muted\">Evidence chain</p><ul class=\"evidence-list\">{items}</ul>"


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


def _render_signal_link_list(state_date: date, label: str, ids: list[str]) -> str:
    if not ids:
        return f"<p><strong>{escape(label)}:</strong> none</p>"
    pills = "".join(
        '<a class="pill" href="'
        f"{escape(_detail_href(state_date=state_date, signal_id=item))}"
        f'">{escape(item)}</a>'
        for item in ids
    )
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


def _render_payload(payload: JSONDict) -> str:
    if not payload:
        return ""
    return (
        "<p><strong>Payload</strong></p>"
        f"<pre>{escape(json.dumps(payload, indent=2, sort_keys=True))}</pre>"
    )


def _render_entity_reference(entity_type: str | None, entity_id: str | None) -> str:
    if entity_type is None and entity_id is None:
        return ""
    return (
        "<p class=\"muted\">Entity reference: "
        f"{escape(entity_type or 'unknown')} / {escape(entity_id or 'unknown')}</p>"
    )


def _render_related_entity_row(signal: JSONDict) -> str:
    entity_type = signal.get("related_entity_type")
    entity_id = signal.get("related_entity_id")
    if entity_type is None and entity_id is None:
        return ""
    return (
        "<p class=\"muted\">Related entity: "
        f"{escape(entity_type or 'unknown')} / {escape(entity_id or 'unknown')}</p>"
    )


def _render_related_entity_detail_rows(signal: JSONDict) -> str:
    entity_type = signal.get("related_entity_type")
    entity_id = signal.get("related_entity_id")
    return (
        f"<dt>Related entity type</dt><dd>{escape(entity_type or 'none')}</dd>"
        f"<dt>Related entity id</dt><dd>{escape(entity_id or 'none')}</dd>"
    )


def _detail_href(
    *,
    state_date: date,
    signal_id: str | None = None,
    alert_id: str | None = None,
) -> str:
    query: dict[str, str] = {"state_date": state_date.isoformat()}
    if signal_id is not None:
        query["signal_id"] = str(signal_id)
    if alert_id is not None:
        query["alert_id"] = str(alert_id)
    return f"/?{urlencode(query)}"


def _redirect_home(*, state_date: date) -> RedirectResponse:
    return RedirectResponse(url=_detail_href(state_date=state_date), status_code=303)


def _render_action_error(error: Exception, *, title: str) -> HTMLResponse:
    detail = str(error)
    status_code = 400
    if isinstance(error, HubAPIError):
        detail = error.detail
        status_code = error.status_code
    return HTMLResponse(
        content=f"<h1>{escape(title)}</h1><p>{escape(detail)}</p>",
        status_code=status_code,
    )


def _render_daily_state_form(*, state_date: date, daily_state: JSONDict | None) -> str:
    priorities = _join_lines(_list_from(daily_state, "priorities"))
    win_condition = _string_from(daily_state, "win_condition")
    movement = daily_state["movement"] if daily_state is not None else None
    stress = (
        ""
        if daily_state is None or daily_state["stress"] is None
        else str(daily_state["stress"])
    )
    next_action = _string_from(daily_state, "next_action")
    return (
        '<div class="action-block">'
        '<h3>Update Current Operational State</h3>'
        '<form method="post" action="/actions/daily-state">'
        f'<input type="hidden" name="state_date" value="{escape(state_date.isoformat())}">'
        "<label>Top priorities<br>"
        f'<textarea name="priorities">{escape(priorities)}</textarea>'
        "</label>"
        "<label>Win condition<br>"
        f'<input type="text" name="win_condition" value="{escape(win_condition)}">'
        "</label>"
        "<label>Movement<br>"
        '<select name="movement">'
        f'{_render_option(value="", label="unknown", selected=movement is None)}'
        f'{_render_option(value="true", label="recorded", selected=movement is True)}'
        f'{_render_option(value="false", label="not recorded", selected=movement is False)}'
        "</select>"
        "</label>"
        "<label>Stress<br>"
        f'<input type="number" min="1" max="10" name="stress" value="{escape(stress)}">'
        "</label>"
        "<label>Next action<br>"
        f'<input type="text" name="next_action" value="{escape(next_action)}">'
        "</label>"
        "<button type=\"submit\">Save daily state</button>"
        "</form>"
        "</div>"
    )


def _render_weekly_forms(*, state_date: date, weekly_state: JSONDict | None) -> str:
    outcomes = _join_lines(_list_from(weekly_state, "outcomes"))
    cannot_drift = _join_lines(_list_from(weekly_state, "cannot_drift"))
    blockers = _join_lines(_list_from(weekly_state, "blockers"))
    lesson = _string_from(weekly_state, "lesson")
    return (
        '<div class="action-block">'
        '<h3>Update Weekly Plan</h3>'
        '<form method="post" action="/actions/weekly-plan">'
        f'<input type="hidden" name="state_date" value="{escape(state_date.isoformat())}">'
        "<label>Outcomes<br>"
        f'<textarea name="outcomes">{escape(outcomes)}</textarea>'
        "</label>"
        "<label>Cannot drift<br>"
        f'<textarea name="cannot_drift">{escape(cannot_drift)}</textarea>'
        "</label>"
        "<label>Blockers<br>"
        f'<textarea name="blockers">{escape(blockers)}</textarea>'
        "</label>"
        "<button type=\"submit\">Save weekly plan</button>"
        "</form>"
        "</div>"
        '<div class="action-block">'
        '<h3>Update Weekly Reflection</h3>'
        '<form method="post" action="/actions/weekly-reflection">'
        f'<input type="hidden" name="state_date" value="{escape(state_date.isoformat())}">'
        "<label>Lesson<br>"
        f'<input type="text" name="lesson" value="{escape(lesson)}">'
        "</label>"
        "<label>Blockers<br>"
        f'<textarea name="blockers">{escape(blockers)}</textarea>'
        "</label>"
        "<button type=\"submit\">Save weekly reflection</button>"
        "</form>"
        "</div>"
    )


def _render_open_loop_add_form(*, state_date: date) -> str:
    return (
        '<div class="action-block">'
        '<h3>Add Open Loop</h3>'
        '<form method="post" action="/actions/open-loops">'
        f'<input type="hidden" name="state_date" value="{escape(state_date.isoformat())}">'
        "<label>Title<br>"
        '<input type="text" name="title" value="">'
        "</label>"
        "<label>Source<br>"
        '<input type="text" name="source" value="hub">'
        "</label>"
        "<label>Priority<br>"
        '<select name="priority">'
        f'{_render_option(value="low", label="low", selected=False)}'
        f'{_render_option(value="medium", label="medium", selected=True)}'
        f'{_render_option(value="high", label="high", selected=False)}'
        "</select>"
        "</label>"
        "<label>Notes<br>"
        '<input type="text" name="notes" value="">'
        "</label>"
        "<button type=\"submit\">Add open loop</button>"
        "</form>"
        "</div>"
    )


def _render_open_loop_resolve_form(*, state_date: date, loop_id: str) -> str:
    return (
        '<form class="inline-form" method="post" action="'
        f'/actions/open-loops/{escape(loop_id)}/resolve">'
        f'<input type="hidden" name="state_date" value="{escape(state_date.isoformat())}">'
        "<button type=\"submit\">Resolve open loop</button>"
        "</form>"
    )


def _render_option(*, value: str, label: str, selected: bool) -> str:
    selected_attr = " selected" if selected else ""
    return f'<option value="{escape(value)}"{selected_attr}>{escape(label)}</option>'


async def _parse_form_body(request: FastAPIRequest) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _join_lines(values: list[str]) -> str:
    return "\n".join(values)


def _string_from(payload: JSONDict | None, key: str) -> str:
    if payload is None:
        return ""
    value = payload.get(key)
    return str(value) if isinstance(value, str) else ""


def _split_lines(value: Any) -> list[str] | None:
    text = _optional_str(value)
    if text is None:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_str(form: Any, field_name: str) -> str:
    value = _optional_str(form.get(field_name))
    if value is None:
        raise ValueError(f"Missing required field: {field_name}.")
    return value


def _parse_bool(value: Any) -> bool | None:
    text = _optional_str(value)
    if text is None:
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"Invalid boolean value: {text}.")


def _parse_int(value: Any) -> int | None:
    text = _optional_str(value)
    if text is None:
        return None
    return int(text)
