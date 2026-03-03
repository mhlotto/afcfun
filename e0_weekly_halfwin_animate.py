#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from e0_season_utils import parse_season_filter
from e0_weekly_halfwin_plot import (
    build_team_series,
    build_team_series_from_db,
    parse_teams,
)


_SERIES_COLORS = [
    "#0b6dfa",
    "#e65100",
    "#2e7d32",
    "#8e24aa",
    "#c62828",
    "#00838f",
    "#6d4c41",
    "#5d4037",
    "#3949ab",
    "#7cb342",
]

_SERIES_COLORS_CINEMATIC = [
    "#245c9f",
    "#c4681c",
    "#2a8559",
    "#b0432d",
    "#4556a8",
    "#19808f",
    "#7f5139",
    "#6e7d23",
    "#6f4f97",
    "#5a7ea2",
]


def _resolve_style(style: str) -> str:
    key = style.strip().lower()
    if key not in {"classic", "cinematic"}:
        raise ValueError("style must be 'classic' or 'cinematic'")
    return key


def _theme_vars(style: str) -> dict[str, str]:
    if style == "cinematic":
        return {
            "bg_a": "#f7f0e2",
            "bg_b": "#e6f0f7",
            "ink": "#13293d",
            "muted": "#4d6175",
            "panel": "#fffdf7df",
            "panel_border": "#d4e0ec",
            "accent": "#114f88",
            "accent_2": "#b2671d",
            "chart_bg": "linear-gradient(180deg, #fffeff 0%, #f9fbff 100%)",
            "frame_shadow": "0 24px 54px rgba(12, 37, 61, 0.16)",
            "panel_blur": "6px",
            "font_main": "'Trebuchet MS', 'Avenir Next', sans-serif",
            "font_display": "'Arial Narrow', 'Trebuchet MS', sans-serif",
        }
    return {
        "bg_a": "#f4f8ff",
        "bg_b": "#eef7f2",
        "ink": "#13293d",
        "muted": "#4f6478",
        "panel": "#ffffffd6",
        "panel_border": "#d8e3ef",
        "accent": "#1a5fb4",
        "accent_2": "#0f8a5f",
        "chart_bg": "linear-gradient(180deg, #ffffff 0%, #fbfdff 100%)",
        "frame_shadow": "0 18px 40px rgba(8, 34, 64, 0.12)",
        "panel_blur": "4px",
        "font_main": "'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
        "font_display": "'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
    }


def _style_options(style: str) -> dict[str, object]:
    if style == "cinematic":
        return {
            "line_ease": "easeInOutCubic",
            "line_fade": True,
            "line_fade_floor": 0.3,
            "head_pulse": True,
            "callouts": True,
            "line_width": 3.2,
            "historical_width": 2.2,
        }
    return {
        "line_ease": "linear",
        "line_fade": False,
        "line_fade_floor": 1.0,
        "head_pulse": False,
        "callouts": False,
        "line_width": 2.5,
        "historical_width": 2.5,
    }


def _points_ticks(max_points: float) -> list[float]:
    if max_points <= 0:
        return [0.0]
    step = max(1, int(math.ceil(max_points / 10.0)))
    upper = int(math.ceil(max_points / step) * step)
    return [float(value) for value in range(0, upper + 1, step)]


def _to_str_map(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = str(value)
    return out


def _point_summary(point: Any) -> dict[str, object]:
    return {
        "date": point.date,
        "opponent": point.opponent,
        "venue": point.venue,
        "result": point.result,
        "goals_for": point.goals_for,
        "goals_against": point.goals_against,
        "goal_diff": point.goal_diff,
        "shots": point.shots,
        "shots_on_target": point.shots_on_target,
        "corners": point.corners,
        "fouls": point.fouls,
        "yellow_cards": point.yellow_cards,
        "red_cards": point.red_cards,
        "opponent_shots": point.opponent_shots,
        "opponent_shots_on_target": point.opponent_shots_on_target,
        "opponent_corners": point.opponent_corners,
        "opponent_fouls": point.opponent_fouls,
        "opponent_yellow_cards": point.opponent_yellow_cards,
        "opponent_red_cards": point.opponent_red_cards,
    }


def _load_media_config(path: str | None) -> dict[tuple[str, int], dict[str, str]]:
    if not path:
        return {}
    raw = Path(path).read_text(encoding="utf-8")
    loaded = json.loads(raw)
    out: dict[tuple[str, int], dict[str, str]] = {}

    def add_entry(team: Any, week: Any, payload: Any) -> None:
        if not isinstance(team, str) or not team.strip():
            raise ValueError("Media config entry requires a non-empty string team.")
        try:
            week_int = int(week)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Media config week must be a positive integer, got {week!r}."
            ) from exc
        if week_int <= 0:
            raise ValueError("Media config week must be a positive integer.")
        if not isinstance(payload, dict):
            raise ValueError("Media config entry payload must be an object.")
        out[(team.strip().lower(), week_int)] = _to_str_map(payload)

    if isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
        for entry in loaded["entries"]:
            if not isinstance(entry, dict):
                raise ValueError("Each media config entry must be an object.")
            team = entry.get("team")
            week = entry.get("week")
            payload = dict(entry)
            payload.pop("team", None)
            payload.pop("week", None)
            add_entry(team, week, payload)
        return out

    if isinstance(loaded, list):
        for entry in loaded:
            if not isinstance(entry, dict):
                raise ValueError("Each media config entry must be an object.")
            team = entry.get("team")
            week = entry.get("week")
            payload = dict(entry)
            payload.pop("team", None)
            payload.pop("week", None)
            add_entry(team, week, payload)
        return out

    if isinstance(loaded, dict):
        for team, by_week in loaded.items():
            if not isinstance(by_week, dict):
                continue
            for week, payload in by_week.items():
                add_entry(team, week, payload)
        return out

    raise ValueError(
        "Media config must be either a list of entries, an object with "
        "'entries', or a team->week->payload mapping."
    )


def _build_payload_from_series(
    series_by_team: dict[str, list[Any]],
    teams: list[str],
    media_map: dict[tuple[str, int], dict[str, str]],
    *,
    style: str,
) -> dict[str, object]:
    max_week = max(len(points) for points in series_by_team.values())
    max_points = max(
        point.running_league_points
        for points in series_by_team.values()
        for point in points
    )
    payload_teams: list[dict[str, object]] = []
    palette = (
        _SERIES_COLORS_CINEMATIC if style == "cinematic" else _SERIES_COLORS
    )
    for index, team in enumerate(teams):
        color = palette[index % len(palette)]
        points = series_by_team[team]
        payload_teams.append(
            {
                "name": team,
                "color": color,
                "points": [
                    {
                        "week": point.week,
                        "average": point.average,
                        "running_points": point.running_league_points,
                        "summary": _point_summary(point),
                        "media": media_map.get((team.strip().lower(), point.week)),
                    }
                    for point in points
                ],
            }
        )
    return {
        "teams": payload_teams,
        "max_week": max_week,
        "max_points": max_points,
        "y_ticks_top": [0.0, 0.05]
        + [tick / 100.0 for tick in range(15, 100, 10)]
        + [1.0],
        "y_ticks_bottom": _points_ticks(max_points),
    }


def _build_payload(
    csv_path: str,
    teams: list[str],
    side: str,
    media_map: dict[tuple[str, int], dict[str, str]],
    *,
    style: str,
) -> dict[str, object]:
    series_by_team = build_team_series(csv_path=csv_path, teams=teams, side=side)
    return _build_payload_from_series(
        series_by_team,
        teams,
        media_map,
        style=style,
    )


def write_animation_html(
    *,
    out_path: Path,
    payload: dict[str, object],
    interval_ms: int,
    title: str,
    trail_glow: bool,
    style: str,
) -> None:
    data_json = json.dumps(payload, separators=(",", ":"))
    style_cfg = _style_options(style)
    style_json = json.dumps(style_cfg, separators=(",", ":"))
    theme = _theme_vars(style)
    subtitle = (
        "Cinematic mode: eased motion, narrative callouts, and richer visual styling."
        if style == "cinematic"
        else "Animated reveal of weekly progression across two panels."
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape_html(title)}</title>
  <style>
    :root {{
      --bg-a: {theme["bg_a"]};
      --bg-b: {theme["bg_b"]};
      --ink: {theme["ink"]};
      --muted: {theme["muted"]};
      --panel: {theme["panel"]};
      --panel-border: {theme["panel_border"]};
      --accent: {theme["accent"]};
      --accent-2: {theme["accent_2"]};
      --chart-bg: {theme["chart_bg"]};
      --frame-shadow: {theme["frame_shadow"]};
      --panel-blur: {theme["panel_blur"]};
      --font-main: {theme["font_main"]};
      --font-display: {theme["font_display"]};
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      padding: 20px;
      color: var(--ink);
      background:
        radial-gradient(1200px 600px at -8% -12%, #dff0ff 0%, transparent 60%),
        radial-gradient(1200px 650px at 110% 112%, #e5f8e8 0%, transparent 62%),
        linear-gradient(180deg, var(--bg-a), var(--bg-b));
      font-family: var(--font-main);
    }}
    .frame {{
      max-width: 1160px;
      margin: 0 auto;
      padding: 18px 18px 16px 18px;
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      background: var(--panel);
      backdrop-filter: blur(var(--panel-blur));
      box-shadow: var(--frame-shadow);
    }}
    .title {{
      margin: 0 0 8px 0;
      font-size: 25px;
      line-height: 1.25;
      letter-spacing: 0.2px;
      font-weight: 800;
      font-family: var(--font-display);
    }}
    .subtitle {{
      margin: 0 0 12px 0;
      color: var(--muted);
      font-size: 13px;
      letter-spacing: 0.1px;
    }}
    .controls {{
      display: flex;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    button {{
      border: 1px solid #b7c8db;
      background: #f8fbff;
      color: #12324f;
      border-radius: 9px;
      padding: 7px 12px;
      font-weight: 600;
      letter-spacing: 0.1px;
      cursor: pointer;
      transition: background 160ms ease, transform 100ms ease, border-color 160ms ease;
    }}
    button:hover {{
      background: #eef5ff;
      border-color: #9db8d8;
    }}
    button:active {{
      transform: translateY(1px);
    }}
    .field {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      padding: 6px 10px;
      border-radius: 9px;
      border: 1px solid #d9e5f1;
      background: #f9fcff;
    }}
    input[type="number"] {{
      border: 1px solid #b8cade;
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      padding: 5px 8px;
      font-family: var(--font-main);
      font-size: 13px;
    }}
    .meta {{
      color: #305171;
      font-size: 13px;
      font-weight: 600;
      padding: 6px 10px;
      border-radius: 999px;
      background: #edf5ff;
      border: 1px solid #cddff3;
    }}
    #chart {{
      border: 1px solid #cfdeec;
      border-radius: 12px;
      max-width: 100%;
      height: auto;
      background: var(--chart-bg);
      cursor: default;
    }}
    .modal {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(8, 20, 38, 0.42);
      padding: 16px;
      z-index: 40;
    }}
    .modal.open {{
      display: flex;
    }}
    .modal-card {{
      width: min(780px, 100%);
      max-height: min(88vh, 920px);
      overflow: auto;
      border-radius: 14px;
      border: 1px solid #d4e1ef;
      background: #fff;
      box-shadow: 0 20px 44px rgba(8, 24, 44, 0.26);
      padding: 16px 16px 14px 16px;
      position: relative;
    }}
    .modal-close {{
      position: absolute;
      top: 10px;
      right: 10px;
      border: 1px solid #ccd8e5;
      background: #f8fbff;
      color: #1b3045;
      border-radius: 8px;
      width: 32px;
      height: 32px;
      font-size: 19px;
      line-height: 1;
      cursor: pointer;
    }}
    .modal-title {{
      margin: 0 34px 8px 0;
      font-size: 19px;
      color: #13293d;
    }}
    .modal-section-title {{
      margin: 10px 0 7px 0;
      font-size: 14px;
      color: #3b5674;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 16px;
      margin-bottom: 10px;
    }}
    .stats-row {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      padding: 6px 8px;
      border-radius: 8px;
      background: #f7fbff;
      border: 1px solid #e1ecf7;
      font-size: 13px;
    }}
    .stats-row .label {{
      color: #4b6580;
      font-weight: 600;
    }}
    .stats-row .value {{
      color: #1f3a56;
      font-weight: 700;
    }}
    .media-text {{
      margin: 0 0 8px 0;
      color: #24415f;
      line-height: 1.45;
      white-space: pre-wrap;
      font-size: 14px;
    }}
    .media-image {{
      width: 100%;
      max-height: 420px;
      object-fit: contain;
      border: 1px solid #d8e4f0;
      border-radius: 10px;
      background: #fcfdff;
    }}
    .media-video {{
      width: 100%;
      border-radius: 10px;
      border: 1px solid #d6e3f0;
      background: #000;
    }}
    .media-link {{
      color: #0f5db4;
      font-weight: 700;
      text-decoration: none;
    }}
    .media-link:hover {{
      text-decoration: underline;
    }}
    .hover-tooltip {{
      position: fixed;
      z-index: 35;
      min-width: 220px;
      max-width: 320px;
      padding: 10px 11px;
      border-radius: 10px;
      border: 1px solid #cad9ea;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 12px 24px rgba(10, 32, 57, 0.18);
      color: #17314b;
      font-size: 12px;
      line-height: 1.35;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 120ms ease, transform 120ms ease;
      pointer-events: none;
      display: none;
    }}
    .hover-tooltip.open {{
      display: block;
      opacity: 1;
      transform: translateY(0);
    }}
    .hover-title {{
      margin: 0 0 4px 0;
      font-size: 13px;
      font-weight: 800;
      color: #0f2a45;
    }}
    .hover-line {{
      margin: 0;
      color: #31506c;
    }}
    .hover-line + .hover-line {{
      margin-top: 2px;
    }}
  </style>
</head>
<body>
  <div class="frame">
  <h2 class="title">{_escape_html(title)}</h2>
  <p class="subtitle">{_escape_html(subtitle)}</p>
  <div class="controls">
    <button id="playPause">Pause</button>
    <button id="reset">Reset</button>
    <label class="field">Interval (ms):
      <input id="interval" type="number" min="50" step="50" value="{interval_ms}" style="width:90px;" />
    </label>
    <label class="field">
      <input id="trailGlow" type="checkbox" {"checked" if trail_glow else ""} />
      Trail glow
    </label>
    <span class="meta">Week: <span id="weekLabel">0</span></span>
  </div>
  <canvas id="chart" width="1100" height="820"></canvas>
  </div>
  <div id="detailModal" class="modal" aria-hidden="true">
    <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
      <button id="modalClose" class="modal-close" aria-label="Close">×</button>
      <h3 id="modalTitle" class="modal-title"></h3>
      <div id="modalBody"></div>
    </div>
  </div>
  <div id="hoverTooltip" class="hover-tooltip" aria-hidden="true">
    <p id="hoverTitle" class="hover-title"></p>
    <p id="hoverLineMeta" class="hover-line"></p>
    <p id="hoverLineStats" class="hover-line"></p>
    <p id="hoverLineHint" class="hover-line"></p>
  </div>
  <script>
    const data = {data_json};
    const styleCfg = {style_json};
    const canvas = document.getElementById("chart");
    const ctx = canvas.getContext("2d");
    const playPauseBtn = document.getElementById("playPause");
    const resetBtn = document.getElementById("reset");
    const weekLabel = document.getElementById("weekLabel");
    const intervalInput = document.getElementById("interval");
    const trailGlowInput = document.getElementById("trailGlow");
    const detailModal = document.getElementById("detailModal");
    const modalCloseBtn = document.getElementById("modalClose");
    const modalTitle = document.getElementById("modalTitle");
    const modalBody = document.getElementById("modalBody");
    const hoverTooltip = document.getElementById("hoverTooltip");
    const hoverTitle = document.getElementById("hoverTitle");
    const hoverLineMeta = document.getElementById("hoverLineMeta");
    const hoverLineStats = document.getElementById("hoverLineStats");
    const hoverLineHint = document.getElementById("hoverLineHint");

    const layout = {{
      width: canvas.width,
      height: canvas.height,
      padLeft: 90,
      padRight: 90,
      headerTop: 28,
      topChartTop: 160,
      panelHeight: 260,
      panelGap: 115
    }};
    layout.bottomChartTop = layout.topChartTop + layout.panelHeight + layout.panelGap;
    layout.chartW = layout.width - layout.padLeft - layout.padRight;
    layout.chartRight = layout.padLeft + layout.chartW;
    layout.topChartBottom = layout.topChartTop + layout.panelHeight;
    layout.bottomChartBottom = layout.bottomChartTop + layout.panelHeight;

    let progress = 0;
    let playing = true;
    let lastTimestamp = null;
    const flashes = [];
    let clickTargets = [];
    const FLASH_MS = 360;

    function xFor(week) {{
      if (data.max_week <= 1) return layout.padLeft + layout.chartW / 2;
      return layout.padLeft + (week - 1) * layout.chartW / (data.max_week - 1);
    }}

    function yTop(value) {{
      const v = Math.max(0, Math.min(1, value));
      return layout.topChartTop + (1 - v) * layout.panelHeight;
    }}

    function yBottom(value) {{
      if (data.max_points <= 0) return layout.bottomChartBottom;
      const v = Math.max(0, Math.min(data.max_points, value));
      return layout.bottomChartTop + (1 - v / data.max_points) * layout.panelHeight;
    }}

    function clamp(value, min, max) {{
      return Math.max(min, Math.min(max, value));
    }}

    function easeInOutCubic(t) {{
      if (t < 0.5) return 4 * t * t * t;
      return 1 - Math.pow(-2 * t + 2, 3) / 2;
    }}

    function easedFrac(t) {{
      if (styleCfg.line_ease === "easeInOutCubic") return easeInOutCubic(t);
      return t;
    }}

    function colorWithAlpha(hexColor, alpha) {{
      if (!hexColor || typeof hexColor !== "string" || !hexColor.startsWith("#")) {{
        return hexColor;
      }}
      const raw = hexColor.slice(1);
      const value = raw.length === 3
        ? raw.split("").map((ch) => ch + ch).join("")
        : raw;
      if (value.length !== 6) return hexColor;
      const r = parseInt(value.slice(0, 2), 16);
      const g = parseInt(value.slice(2, 4), 16);
      const b = parseInt(value.slice(4, 6), 16);
      const a = clamp(alpha, 0, 1);
      return `rgba(${{r}}, ${{g}}, ${{b}}, ${{a}})`;
    }}

    function currentIntervalMs() {{
      return Math.max(50, Number(intervalInput.value) || {interval_ms});
    }}

    function xTicks(maxWeek) {{
      if (maxWeek <= 10) {{
        return Array.from({{length: maxWeek}}, (_, i) => i + 1);
      }}
      const step = Math.max(1, Math.floor(maxWeek / 10));
      const ticks = [];
      for (let week = 1; week <= maxWeek; week += step) ticks.push(week);
      if (ticks[ticks.length - 1] !== maxWeek) ticks.push(maxWeek);
      return ticks;
    }}

    function drawText(text, x, y, opts = {{}}) {{
      ctx.save();
      ctx.font = opts.font || "12px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif";
      ctx.fillStyle = opts.color || "#223448";
      ctx.textAlign = opts.align || "left";
      ctx.textBaseline = opts.baseline || "alphabetic";
      ctx.fillText(text, x, y);
      ctx.restore();
    }}

    function drawLine(x1, y1, x2, y2, opts = {{}}) {{
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.lineWidth = opts.width || 1;
      ctx.strokeStyle = opts.color || "#ccd7e4";
      if (opts.dashed) ctx.setLineDash(opts.dashed);
      ctx.lineCap = opts.cap || "round";
      ctx.lineJoin = opts.join || "round";
      ctx.stroke();
      ctx.restore();
    }}

    function drawCircle(x, y, r, color) {{
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.restore();
    }}

    function clearNode(node) {{
      while (node.firstChild) node.removeChild(node.firstChild);
    }}

    function hideTooltip() {{
      hoverTooltip.classList.remove("open");
      hoverTooltip.setAttribute("aria-hidden", "true");
    }}

    function showTooltip(target, clientX, clientY) {{
      const point = target.point;
      const summary = point.summary || {{}};
      const hasMedia = point.media && Object.keys(point.media).length > 0;
      const venue = summary.venue ? String(summary.venue) : "n/a";
      const opponent = summary.opponent ? String(summary.opponent) : "n/a";
      const date = summary.date ? String(summary.date) : "n/a";
      const result = summary.result ? String(summary.result) : "n/a";
      hoverTitle.textContent = `${{target.teamName}} - Week ${{point.week}}`;
      hoverLineMeta.textContent = `${{date}} | ${{venue}} vs ${{opponent}}`;
      hoverLineStats.textContent = `Result: ${{result}} | Avg: ${{point.average.toFixed(3)}} | Pts: ${{point.running_points.toFixed(0)}}`;
      hoverLineHint.textContent = hasMedia
        ? "Click for full stats + attached media"
        : "Click for full week stats";

      hoverTooltip.classList.add("open");
      hoverTooltip.setAttribute("aria-hidden", "false");

      const margin = 12;
      const rect = hoverTooltip.getBoundingClientRect();
      let left = clientX + 14;
      let top = clientY + 14;
      if (left + rect.width + margin > window.innerWidth) {{
        left = Math.max(margin, clientX - rect.width - 14);
      }}
      if (top + rect.height + margin > window.innerHeight) {{
        top = Math.max(margin, clientY - rect.height - 14);
      }}
      hoverTooltip.style.left = `${{left}}px`;
      hoverTooltip.style.top = `${{top}}px`;
    }}

    function makeStatRow(label, value) {{
      const row = document.createElement("div");
      row.className = "stats-row";
      const labelNode = document.createElement("span");
      labelNode.className = "label";
      labelNode.textContent = label;
      const valueNode = document.createElement("span");
      valueNode.className = "value";
      valueNode.textContent = String(value);
      row.appendChild(labelNode);
      row.appendChild(valueNode);
      return row;
    }}

    function addSectionTitle(text) {{
      const node = document.createElement("div");
      node.className = "modal-section-title";
      node.textContent = text;
      modalBody.appendChild(node);
    }}

    function showPointDetails(teamName, point) {{
      modalTitle.textContent = `${{teamName}} - Week ${{point.week}}`;
      clearNode(modalBody);

      const summary = point.summary || {{}};
      addSectionTitle("Match Summary");
      const grid = document.createElement("div");
      grid.className = "stats-grid";
      const summaryRows = [
        ["Date", summary.date],
        ["Venue", summary.venue],
        ["Opponent", summary.opponent],
        ["Result", summary.result],
        ["Goals (For-Against)", summary.goals_for != null && summary.goals_against != null ? `${{summary.goals_for}}-${{summary.goals_against}}` : null],
        ["Goal Diff", summary.goal_diff],
        ["Shots", summary.shots != null && summary.opponent_shots != null ? `${{summary.shots}}-${{summary.opponent_shots}}` : null],
        ["Shots on Target", summary.shots_on_target != null && summary.opponent_shots_on_target != null ? `${{summary.shots_on_target}}-${{summary.opponent_shots_on_target}}` : null],
        ["Corners", summary.corners != null && summary.opponent_corners != null ? `${{summary.corners}}-${{summary.opponent_corners}}` : null],
        ["Fouls", summary.fouls != null && summary.opponent_fouls != null ? `${{summary.fouls}}-${{summary.opponent_fouls}}` : null],
        ["Yellow Cards", summary.yellow_cards != null && summary.opponent_yellow_cards != null ? `${{summary.yellow_cards}}-${{summary.opponent_yellow_cards}}` : null],
        ["Red Cards", summary.red_cards != null && summary.opponent_red_cards != null ? `${{summary.red_cards}}-${{summary.opponent_red_cards}}` : null]
      ];
      for (const [label, value] of summaryRows) {{
        if (value == null || value === "") continue;
        grid.appendChild(makeStatRow(label, value));
      }}
      if (!grid.childNodes.length) {{
        const empty = document.createElement("p");
        empty.className = "media-text";
        empty.textContent = "No summary stats are available for this week.";
        modalBody.appendChild(empty);
      }} else {{
        modalBody.appendChild(grid);
      }}

      const media = point.media || null;
      if (media && Object.keys(media).length > 0) {{
        addSectionTitle("Attached Media");
        if (media.title) {{
          const t = document.createElement("p");
          t.className = "media-text";
          t.style.fontWeight = "700";
          t.style.marginBottom = "4px";
          t.textContent = media.title;
          modalBody.appendChild(t);
        }}
        if (media.text) {{
          const p = document.createElement("p");
          p.className = "media-text";
          p.textContent = media.text;
          modalBody.appendChild(p);
        }}
        if (media.image) {{
          const img = document.createElement("img");
          img.className = "media-image";
          img.src = media.image;
          img.alt = media.title || `Week ${{point.week}} media image`;
          modalBody.appendChild(img);
        }}
        if (media.video) {{
          const video = document.createElement("video");
          video.className = "media-video";
          video.controls = true;
          video.preload = "metadata";
          video.src = media.video;
          modalBody.appendChild(video);
        }}
        if (media.link_url) {{
          const a = document.createElement("a");
          a.className = "media-link";
          a.href = media.link_url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = media.link_label || "Open related link";
          modalBody.appendChild(a);
        }}
      }} else {{
        addSectionTitle("No Attached Media");
        const p = document.createElement("p");
        p.className = "media-text";
        p.textContent = "No extra media configured. Showing default team stats summary for this week.";
        modalBody.appendChild(p);
      }}

      detailModal.classList.add("open");
      detailModal.setAttribute("aria-hidden", "false");
    }}

    function closePointDetails() {{
      detailModal.classList.remove("open");
      detailModal.setAttribute("aria-hidden", "true");
    }}

    function registerClickTarget(x, y, teamName, point) {{
      clickTargets.push({{ x, y, r: 8, teamName, point }});
    }}

    function pickTarget(mx, my) {{
      for (let i = clickTargets.length - 1; i >= 0; i -= 1) {{
        const item = clickTargets[i];
        const dx = mx - item.x;
        const dy = my - item.y;
        if ((dx * dx + dy * dy) <= (item.r * item.r)) return item;
      }}
      return null;
    }}

    function drawGlowDot(x, y, color, radius) {{
      ctx.save();
      ctx.globalAlpha = 0.22;
      ctx.beginPath();
      ctx.arc(x, y, radius * 2.8, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.globalAlpha = 0.42;
      ctx.beginPath();
      ctx.arc(x, y, radius * 1.7, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.restore();
    }}

    function drawAxesAndGrid() {{
      const topTicks = data.y_ticks_top;
      const bottomTicks = data.y_ticks_bottom;

      ctx.save();
      ctx.fillStyle = "#f8fbff";
      ctx.fillRect(layout.padLeft, layout.topChartTop, layout.chartW, layout.panelHeight);
      ctx.fillStyle = "#f9fcfa";
      ctx.fillRect(layout.padLeft, layout.bottomChartTop, layout.chartW, layout.panelHeight);
      ctx.restore();

      for (const tick of topTicks) {{
        const y = yTop(tick);
        drawLine(layout.padLeft, y, layout.chartRight, y, {{ color: "#dfe9f5", width: 1 }});
        drawText(tick.toFixed(2), layout.padLeft - 14, y + 4, {{ align: "right", color: "#3f5f80" }});
        drawText(tick.toFixed(2), layout.chartRight + 14, y + 4, {{ align: "left", color: "#3f5f80" }});
      }}

      for (const tick of bottomTicks) {{
        const y = yBottom(tick);
        drawLine(layout.padLeft, y, layout.chartRight, y, {{ color: "#e3ece2", width: 1 }});
        drawText(tick.toFixed(0), layout.padLeft - 14, y + 4, {{ align: "right", color: "#3f5f80" }});
        drawText(tick.toFixed(0), layout.chartRight + 14, y + 4, {{ align: "left", color: "#3f5f80" }});
      }}

      for (const week of xTicks(data.max_week)) {{
        const x = xFor(week);
        drawLine(x, layout.topChartTop, x, layout.bottomChartBottom, {{ color: "#ebeff4", width: 1 }});
        drawText(`W${{week}}`, x, layout.bottomChartBottom + 26, {{ align: "center", color: "#446180" }});
      }}

      drawLine(layout.padLeft, layout.topChartTop, layout.padLeft, layout.topChartBottom, {{ color: "#21374f", width: 1.3 }});
      drawLine(layout.chartRight, layout.topChartTop, layout.chartRight, layout.topChartBottom, {{ color: "#21374f", width: 1.3 }});
      drawLine(layout.padLeft, layout.topChartBottom, layout.chartRight, layout.topChartBottom, {{ color: "#21374f", width: 1.3 }});

      drawLine(layout.padLeft, layout.bottomChartTop, layout.padLeft, layout.bottomChartBottom, {{ color: "#21374f", width: 1.3 }});
      drawLine(layout.chartRight, layout.bottomChartTop, layout.chartRight, layout.bottomChartBottom, {{ color: "#21374f", width: 1.3 }});
      drawLine(layout.padLeft, layout.bottomChartBottom, layout.chartRight, layout.bottomChartBottom, {{ color: "#21374f", width: 1.3 }});

      drawText("Half-win running average (0..1)", layout.padLeft, layout.topChartTop - 12, {{ font: "13px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif", color: "#2f4b68" }});
      drawText("Cumulative points (3/1/0)", layout.padLeft, layout.bottomChartTop - 12, {{ font: "13px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif", color: "#2f4b68" }});
    }}

    function drawLegend(progressWeek) {{
      const completedWeek = Math.floor(progressWeek);
      let y = 90;
      for (const team of data.teams) {{
        const idx = Math.max(0, Math.min(completedWeek, team.points.length) - 1);
        const p = idx >= 0 ? team.points[idx] : null;
        drawLine(layout.padLeft, y, layout.padLeft + 18, y, {{ color: team.color, width: 3 }});
        const label = p
          ? `${{team.name}}: avg=${{p.average.toFixed(3)}}, pts=${{p.running_points.toFixed(0)}}`
          : `${{team.name}}: avg=0.000, pts=0`;
        drawText(label, layout.padLeft + 24, y + 4, {{ font: "12px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif", color: "#2c4661" }});
        y += 18;
      }}
    }}

    function buildCinematicCallouts() {{
      if (!styleCfg.callouts || !data.teams.length) return [];
      const team = data.teams[0];
      const points = team.points || [];
      if (!points.length) return [];

      let peak = points[0];
      let trough = points[0];
      let dip = null;
      for (let i = 0; i < points.length; i += 1) {{
        const current = points[i];
        if (current.average > peak.average) peak = current;
        if (current.average < trough.average) trough = current;
        if (i > 0) {{
          const delta = current.average - points[i - 1].average;
          if (dip === null || delta < dip.delta) {{
            dip = {{ point: current, delta }};
          }}
        }}
      }}

      const callouts = [
        {{
          week: peak.week,
          y: peak.average,
          color: team.color,
          label: `${{team.name}} peak form`,
        }},
        {{
          week: trough.week,
          y: trough.average,
          color: team.color,
          label: `${{team.name}} low point`,
        }},
      ];
      if (dip && dip.delta < 0) {{
        callouts.push({{
          week: dip.point.week,
          y: dip.point.average,
          color: team.color,
          label: `${{team.name}} biggest dip`,
        }});
      }}

      const unique = new Map();
      for (const item of callouts) {{
        unique.set(`${{item.week}}-${{item.label}}`, item);
      }}
      return Array.from(unique.values()).sort((a, b) => a.week - b.week);
    }}

    const cinematicCallouts = buildCinematicCallouts();

    function drawCinematicCallouts(progressWeek) {{
      if (!styleCfg.callouts || !cinematicCallouts.length) return;
      const doneWeek = Math.floor(progressWeek);
      let stack = 0;
      for (const item of cinematicCallouts) {{
        if (item.week > doneWeek) continue;
        const px = xFor(item.week);
        const py = yTop(item.y);
        const text = item.label;
        const offsetY = 18 + (stack % 3) * 17;
        const labelY = Math.max(layout.topChartTop + 14, py - offsetY);
        const textW = Math.min(220, Math.max(92, text.length * 7.1));
        const boxX = clamp(px - textW / 2, layout.padLeft + 6, layout.chartRight - textW - 6);

        drawLine(px, py, px, labelY + 4, {{
          color: colorWithAlpha(item.color, 0.5),
          width: 1.3,
        }});
        ctx.save();
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        ctx.strokeStyle = colorWithAlpha(item.color, 0.5);
        ctx.lineWidth = 1;
        ctx.beginPath();
        const boxY = labelY - 18;
        const boxH = 18;
        const r = 7;
        ctx.moveTo(boxX + r, boxY);
        ctx.lineTo(boxX + textW - r, boxY);
        ctx.quadraticCurveTo(boxX + textW, boxY, boxX + textW, boxY + r);
        ctx.lineTo(boxX + textW, boxY + boxH - r);
        ctx.quadraticCurveTo(boxX + textW, boxY + boxH, boxX + textW - r, boxY + boxH);
        ctx.lineTo(boxX + r, boxY + boxH);
        ctx.quadraticCurveTo(boxX, boxY + boxH, boxX, boxY + boxH - r);
        ctx.lineTo(boxX, boxY + r);
        ctx.quadraticCurveTo(boxX, boxY, boxX + r, boxY);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.restore();
        drawText(text, boxX + textW / 2, labelY - 5, {{
          align: "center",
          color: "#2d4a66",
          font: "11px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif"
        }});
        stack += 1;
      }}
    }}

    function drawInterpolatedSeries(points, progressWeek, valueKey, yMapper, color, baseRadius, headRadius, teamName, timestamp) {{
      const total = points.length;
      if (total === 0) return;
      const completed = Math.min(Math.floor(progressWeek), total);
      const frac = easedFrac(progressWeek - Math.floor(progressWeek));

      if (completed <= 0) return;

      let headX = xFor(points[completed - 1].week);
      let headY = yMapper(points[completed - 1][valueKey]);
      let segmentStartX = headX;
      let segmentStartY = headY;
      let hasInFlightSegment = false;
      if (completed < total && frac > 0) {{
        const a = points[completed - 1];
        const b = points[completed];
        const ax = xFor(a.week);
        const ay = yMapper(a[valueKey]);
        const bx = xFor(b.week);
        const by = yMapper(b[valueKey]);
        segmentStartX = ax;
        segmentStartY = ay;
        headX = ax + (bx - ax) * frac;
        headY = ay + (by - ay) * frac;
        hasInFlightSegment = true;
      }}

      if (styleCfg.line_fade) {{
        for (let i = 1; i < completed; i += 1) {{
          const x1 = xFor(points[i - 1].week);
          const y1 = yMapper(points[i - 1][valueKey]);
          const x2 = xFor(points[i].week);
          const y2 = yMapper(points[i][valueKey]);
          const age = completed - i;
          const t = completed <= 1 ? 1 : 1 - (age / (completed - 1));
          const alpha = styleCfg.line_fade_floor + (1 - styleCfg.line_fade_floor) * t;
          drawLine(x1, y1, x2, y2, {{
            color: colorWithAlpha(color, alpha),
            width: styleCfg.historical_width,
            cap: "round",
            join: "round"
          }});
        }}
      }} else {{
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(xFor(points[0].week), yMapper(points[0][valueKey]));
        for (let i = 1; i < completed; i += 1) {{
          ctx.lineTo(xFor(points[i].week), yMapper(points[i][valueKey]));
        }}
        if (hasInFlightSegment) {{
          ctx.lineTo(headX, headY);
        }}
        ctx.strokeStyle = color;
        ctx.lineWidth = styleCfg.line_width;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.stroke();
        ctx.restore();
      }}

      if (hasInFlightSegment && styleCfg.line_fade) {{
        drawLine(segmentStartX, segmentStartY, headX, headY, {{
          color: color,
          width: styleCfg.line_width + 0.4,
          cap: "round",
          join: "round"
        }});
      }}

      if (trailGlowInput.checked && hasInFlightSegment) {{
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(segmentStartX, segmentStartY);
        ctx.lineTo(headX, headY);
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.42;
        ctx.lineWidth = 8;
        ctx.lineCap = "round";
        ctx.shadowColor = color;
        ctx.shadowBlur = 12;
        ctx.stroke();
        ctx.restore();

        drawGlowDot(headX, headY, color, headRadius + 1);
      }}

      for (let i = 0; i < completed; i += 1) {{
        const cx = xFor(points[i].week);
        const cy = yMapper(points[i][valueKey]);
        drawCircle(cx, cy, baseRadius, color);
        registerClickTarget(cx, cy, teamName, points[i]);
      }}

      if (completed < total && frac > 0) {{
        drawCircle(headX, headY, headRadius, color);
        if (styleCfg.head_pulse) {{
          const pulse = 0.4 + 0.6 * ((Math.sin((timestamp || 0) / 190) + 1) / 2);
          drawGlowDot(headX, headY, color, headRadius + pulse * 2.4);
        }}
      }}
    }}

    function pushFlash(x, y, color, ts) {{
      flashes.push({{ x, y, color, start: ts }});
    }}

    function registerWeekCrossings(previous, current, ts) {{
      const startWeek = Math.floor(previous) + 1;
      const endWeek = Math.floor(current);
      if (endWeek < startWeek) return;
      for (let week = startWeek; week <= endWeek; week += 1) {{
        for (const team of data.teams) {{
          if (week > team.points.length) continue;
          const point = team.points[week - 1];
          pushFlash(xFor(point.week), yTop(point.average), team.color, ts);
          pushFlash(xFor(point.week), yBottom(point.running_points), team.color, ts);
        }}
      }}
    }}

    function drawFlashes(nowTs) {{
      for (let i = flashes.length - 1; i >= 0; i -= 1) {{
        const flash = flashes[i];
        const age = nowTs - flash.start;
        if (age >= FLASH_MS) {{
          flashes.splice(i, 1);
          continue;
        }}
        const t = age / FLASH_MS;
        const alpha = 0.9 * (1 - t);
        const radius = 4 + 12 * t;
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.arc(flash.x, flash.y, radius, 0, Math.PI * 2);
        ctx.strokeStyle = flash.color;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
      }}
    }}

    function drawSeries(progressWeek, timestamp) {{
      for (const team of data.teams) {{
        drawInterpolatedSeries(
          team.points,
          progressWeek,
          "average",
          yTop,
          team.color,
          2.2,
          3.0,
          team.name,
          timestamp
        );
        drawInterpolatedSeries(
          team.points,
          progressWeek,
          "running_points",
          yBottom,
          team.color,
          2.0,
          2.8,
          team.name,
          timestamp
        );
      }}
    }}

    function render(progressWeek, timestamp) {{
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      drawText("Weekly Half-Win Average + Cumulative Points (Animated)", layout.padLeft, layout.headerTop, {{
        font: "22px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
        color: "#13293d"
      }});
      drawText("Each segment draws smoothly; points pulse when a week is reached.", layout.padLeft, 48, {{
        font: "13px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
        color: "#496987"
      }});
      clickTargets = [];
      drawLegend(progressWeek);
      drawAxesAndGrid();
      drawSeries(progressWeek, timestamp);
      drawCinematicCallouts(progressWeek);
      drawFlashes(timestamp);
      weekLabel.textContent = `${{Math.floor(progressWeek)}} / ${{data.max_week}}`;
    }}

    function animate(timestamp) {{
      if (lastTimestamp === null) lastTimestamp = timestamp;
      const delta = timestamp - lastTimestamp;
      lastTimestamp = timestamp;

      if (playing) {{
        const previous = progress;
        progress = clamp(progress + (delta / currentIntervalMs()), 0, data.max_week);
        registerWeekCrossings(previous, progress, timestamp);
        if (progress >= data.max_week) {{
          playing = false;
          playPauseBtn.textContent = "Play";
        }}
      }}
      render(progress, timestamp);
      window.requestAnimationFrame(animate);
    }}

    playPauseBtn.addEventListener("click", () => {{
      playing = !playing;
      playPauseBtn.textContent = playing ? "Pause" : "Play";
      if (playing && progress >= data.max_week) {{
        progress = 0;
        flashes.length = 0;
      }}
      lastTimestamp = null;
    }});

    resetBtn.addEventListener("click", () => {{
      progress = 0;
      flashes.length = 0;
      playing = true;
      playPauseBtn.textContent = "Pause";
      lastTimestamp = null;
    }});

    intervalInput.addEventListener("change", () => {{
      lastTimestamp = null;
    }});

    canvas.addEventListener("mousemove", (event) => {{
      const rect = canvas.getBoundingClientRect();
      const mx = (event.clientX - rect.left) * (canvas.width / rect.width);
      const my = (event.clientY - rect.top) * (canvas.height / rect.height);
      const target = pickTarget(mx, my);
      if (target) {{
        canvas.style.cursor = "pointer";
        showTooltip(target, event.clientX, event.clientY);
      }} else {{
        canvas.style.cursor = "default";
        hideTooltip();
      }}
    }});

    canvas.addEventListener("mouseleave", () => {{
      canvas.style.cursor = "default";
      hideTooltip();
    }});

    canvas.addEventListener("click", (event) => {{
      const rect = canvas.getBoundingClientRect();
      const mx = (event.clientX - rect.left) * (canvas.width / rect.width);
      const my = (event.clientY - rect.top) * (canvas.height / rect.height);
      const target = pickTarget(mx, my);
      if (!target) return;
      hideTooltip();
      showPointDetails(target.teamName, target.point);
    }});

    modalCloseBtn.addEventListener("click", closePointDetails);
    detailModal.addEventListener("click", (event) => {{
      if (event.target === detailModal) closePointDetails();
    }});
    window.addEventListener("keydown", (event) => {{
      if (event.key === "Escape" && detailModal.classList.contains("open")) {{
        closePointDetails();
      }}
    }});

    render(progress, performance.now());
    window.requestAnimationFrame(animate);
  </script>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an animated HTML chart for week-by-week half-win average "
            "and cumulative points."
        )
    )
    parser.add_argument(
        "--csv",
        default="data/football-data.co.uk/E0.csv",
        help="Path to E0.csv",
    )
    parser.add_argument(
        "--source",
        default="csv",
        choices=["csv", "db"],
        help="Input source mode.",
    )
    parser.add_argument(
        "--db",
        default="data/footstat.sqlite3",
        help="SQLite file path for --source db.",
    )
    parser.add_argument(
        "--competition",
        default="E0",
        help="Competition code for --source db.",
    )
    parser.add_argument(
        "--seasons",
        default=None,
        help="Optional season filters for --source db (YYYY-YYYY or YYYYYYYY, comma-delimited).",
    )
    parser.add_argument(
        "--team",
        default="Arsenal",
        help="Team name(s), comma-delimited for multiple teams.",
    )
    parser.add_argument(
        "--side",
        default="both",
        choices=["home", "away", "both"],
        help="Filter matches by venue.",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=500,
        help="Animation interval in milliseconds between weeks.",
    )
    parser.add_argument(
        "--out",
        default="docs/arsenal_weekly_halfwin_animated.html",
        help="Output HTML path.",
    )
    parser.add_argument(
        "--trail-glow",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable glow on the currently drawing segment.",
    )
    parser.add_argument(
        "--style",
        default="classic",
        choices=["classic", "cinematic"],
        help="Visual style preset.",
    )
    parser.add_argument(
        "--media-config",
        default=None,
        help=(
            "Optional JSON file mapping team/week points to media payloads. "
            "Supports list/entries or team->week->payload forms."
        ),
    )
    args = parser.parse_args()

    teams = parse_teams(args.team)
    style = _resolve_style(args.style)
    media_map = _load_media_config(args.media_config)
    if args.source == "db":
        season_filter = parse_season_filter(args.seasons)
        series_by_team = build_team_series_from_db(
            db_path=args.db,
            teams=teams,
            side=args.side,
            competition_code=args.competition,
            seasons=season_filter,
        )
        payload = _build_payload_from_series(
            series_by_team,
            teams,
            media_map,
            style=style,
        )
    else:
        payload = _build_payload(args.csv, teams, args.side, media_map, style=style)
    title = " / ".join(teams) + ": Weekly Half-Win Average + Cumulative Points"
    write_animation_html(
        out_path=Path(args.out),
        payload=payload,
        interval_ms=max(50, args.interval_ms),
        title=title,
        trail_glow=args.trail_glow,
        style=style,
    )

    print(f"Wrote {args.out}")
    print(f"Source: {args.source}")
    print(f"Teams: {', '.join(teams)}")
    print(f"Interval: {max(50, args.interval_ms)}ms per week")
    print(f"Trail glow: {'on' if args.trail_glow else 'off'}")
    print(f"Style: {style}")
    print(f"Media config: {args.media_config if args.media_config else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
