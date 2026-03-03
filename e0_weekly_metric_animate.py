#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from e0_inspect import (
    extract_team_entries,
    load_normalized_team_rows,
    normalize_by_team,
)
from e0_multi_season import SeasonSource, discover_season_sources
from e0_season_utils import parse_season_filter
from e0_weekly_halfwin_plot import parse_teams
from e0_weekly_metric_plot import (
    WeeklyMetricPoint,
    build_metric_axis,
    build_team_metric_series,
    build_weekly_metric_series,
)


_SERIES_COLORS = [
    "#0b6dfa",
    "#e65100",
    "#2e7d32",
    "#8e24aa",
    "#c62828",
    "#00838f",
    "#6d4c41",
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
            "line_width": 3.2,
        "historical_width": 2.2,
        "point_radius": 3.2,
        "segment_glow": True,
        "font_main": "12px 'Trebuchet MS', 'Avenir Next', sans-serif",
        "font_display": "22px 'Arial Narrow', 'Trebuchet MS', sans-serif",
        "font_meta": "13px 'Trebuchet MS', 'Avenir Next', sans-serif",
        "font_empty": "15px 'Trebuchet MS', 'Avenir Next', sans-serif",
    }
    return {
        "line_ease": "linear",
        "line_fade": False,
        "line_fade_floor": 1.0,
        "line_width": 2.4,
        "historical_width": 2.4,
        "point_radius": 2.8,
        "segment_glow": False,
        "font_main": "12px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
        "font_display": "22px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
        "font_meta": "13px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
        "font_empty": "15px 'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
    }


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _build_payload(
    series_by_team: dict[str, list[WeeklyMetricPoint]],
    *,
    metric: str,
    style: str = "classic",
) -> dict[str, object]:
    max_week = max(len(points) for points in series_by_team.values())
    values = [
        point.value
        for points in series_by_team.values()
        for point in points
        if point.value is not None
    ]
    has_values = bool(values)
    y_min, y_max, y_ticks, y_tick_labels, _ = build_metric_axis(values)

    payload_teams: list[dict[str, object]] = []
    palette = _SERIES_COLORS_CINEMATIC if style == "cinematic" else _SERIES_COLORS
    for index, (team, points) in enumerate(series_by_team.items()):
        color = palette[index % len(palette)]
        payload_teams.append(
            {
                "name": team,
                "color": color,
                "points": [
                    {
                        "week": point.week,
                        "value": point.value,
                        "date": point.date,
                        "opponent": point.opponent,
                        "venue": point.venue,
                        "result": point.result,
                    }
                    for point in points
                ],
            }
        )

    return {
        "metric": metric,
        "teams": payload_teams,
        "max_week": max_week,
        "y_min": y_min,
        "y_max": y_max,
        "y_ticks": y_ticks,
        "y_tick_labels": y_tick_labels,
        "has_values": has_values,
    }


def build_multi_season_metric_series(
    *,
    data_dir: str,
    teams: list[str],
    side: str,
    metric: str,
    seasons: Iterable[str] | None = None,
    include_current: bool = True,
    current_label: str | None = None,
) -> tuple[dict[str, list[WeeklyMetricPoint]], list[SeasonSource]]:
    sources = discover_season_sources(
        data_dir=data_dir,
        include_current=include_current,
        current_label=current_label,
    )
    if not sources:
        raise ValueError(f"No E0 season files found in {data_dir}.")

    if seasons is not None:
        selected = {value.strip() for value in seasons if value.strip()}
        sources = [source for source in sources if source.label in selected]
        if not sources:
            wanted = ", ".join(sorted(selected))
            raise ValueError(f"No season files matched requested seasons: {wanted}.")

    series: dict[str, list[WeeklyMetricPoint]] = {}
    for team in teams:
        for source in sources:
            entries = extract_team_entries(source.path, team=team, side=side)
            if not entries:
                continue
            normalized = normalize_by_team(entries, extract_team=team)
            points = build_weekly_metric_series(normalized, metric=metric)
            if not points:
                continue
            series[f"{team} ({source.label})"] = points

    if not series:
        raise ValueError(
            "No matching rows found for the requested team/season selection."
        )
    return series, sources


def build_db_multi_season_metric_series(
    *,
    teams: list[str],
    side: str,
    metric: str,
    db_path: str,
    competition_code: str,
    seasons: Iterable[str] | None = None,
    source_scope: str = "",
) -> tuple[dict[str, list[WeeklyMetricPoint]], list[str]]:
    series: dict[str, list[WeeklyMetricPoint]] = {}
    all_seasons: set[str] = set()

    for team in teams:
        rows = load_normalized_team_rows(
            source="db",
            team=team,
            side=side,
            db_path=db_path,
            competition_code=competition_code,
            seasons=seasons,
            source_scope=source_scope,
        )
        by_season: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            season = str(row.get("season", "")).strip()
            if not season:
                continue
            by_season.setdefault(season, []).append(row)

        season_order = [label for label in (seasons or []) if label in by_season]
        if not season_order:
            season_order = sorted(by_season.keys())
        for season in season_order:
            points = build_weekly_metric_series(by_season[season], metric=metric)
            if not points:
                continue
            key = f"{team} ({season})"
            series[key] = points
            all_seasons.add(season)

    if not series:
        raise ValueError(
            "No matching rows found for the requested team/season selection."
        )

    if seasons is not None:
        labels = [label for label in seasons if label in all_seasons]
    else:
        labels = sorted(all_seasons)
    return series, labels


def write_metric_animation_html(
    *,
    out_path: Path,
    payload: dict[str, object],
    interval_ms: int,
    title: str,
    style: str,
) -> None:
    data_json = json.dumps(payload, separators=(",", ":"))
    style_cfg = _style_options(style)
    style_json = json.dumps(style_cfg, separators=(",", ":"))
    theme = _theme_vars(style)
    subtitle = (
        "Cinematic mode: eased motion and richer visual styling."
        if style == "cinematic"
        else "Animated weekly metric progression."
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
    * {{ box-sizing: border-box; }}
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
      font-weight: 800;
      font-family: var(--font-display);
    }}
    .subtitle {{
      margin: 0 0 12px 0;
      color: var(--muted);
      font-size: 13px;
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
      cursor: pointer;
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
      width: 90px;
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
    .modal.open {{ display: flex; }}
    .modal-card {{
      width: min(560px, 100%);
      border-radius: 14px;
      border: 1px solid #d4e1ef;
      background: #fff;
      box-shadow: 0 20px 44px rgba(8, 24, 44, 0.26);
      padding: 16px;
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
      cursor: pointer;
    }}
    .modal-title {{
      margin: 0 34px 8px 0;
      font-size: 19px;
      color: #13293d;
    }}
    .detail {{
      margin: 0 0 6px 0;
      color: #26435f;
      font-size: 14px;
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
        <input id="interval" type="number" min="50" step="50" value="{interval_ms}" />
      </label>
      <span class="meta">Week: <span id="weekLabel">0</span></span>
    </div>
    <canvas id="chart" width="1100" height="620"></canvas>
  </div>
  <div id="detailModal" class="modal" aria-hidden="true">
    <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
      <button id="modalClose" class="modal-close" aria-label="Close">x</button>
      <h3 id="modalTitle" class="modal-title"></h3>
      <p id="detailLine1" class="detail"></p>
      <p id="detailLine2" class="detail"></p>
      <p id="detailLine3" class="detail"></p>
    </div>
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
    const detailModal = document.getElementById("detailModal");
    const modalCloseBtn = document.getElementById("modalClose");
    const modalTitle = document.getElementById("modalTitle");
    const detailLine1 = document.getElementById("detailLine1");
    const detailLine2 = document.getElementById("detailLine2");
    const detailLine3 = document.getElementById("detailLine3");

    const layout = {{
      width: canvas.width,
      height: canvas.height,
      padLeft: 90,
      padRight: 90,
      chartTop: 130,
      panelHeight: 380
    }};
    layout.chartW = layout.width - layout.padLeft - layout.padRight;
    layout.chartRight = layout.padLeft + layout.chartW;
    layout.chartBottom = layout.chartTop + layout.panelHeight;

    let progress = 0;
    let playing = true;
    let lastTimestamp = null;
    let clickTargets = [];

    function clamp(value, min, max) {{
      return Math.max(min, Math.min(max, value));
    }}

    function xFor(week) {{
      if (data.max_week <= 1) return layout.padLeft + layout.chartW / 2;
      return layout.padLeft + (week - 1) * layout.chartW / (data.max_week - 1);
    }}

    function yFor(value) {{
      const span = data.y_max - data.y_min;
      if (span <= 0) return layout.chartBottom;
      const ratio = (value - data.y_min) / span;
      return layout.chartTop + (1 - ratio) * layout.panelHeight;
    }}

    function currentIntervalMs() {{
      return Math.max(50, Number(intervalInput.value) || {interval_ms});
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

    function drawText(text, x, y, opts = {{}}) {{
      ctx.save();
      ctx.font = opts.font || styleCfg.font_main;
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
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
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

    function showPointDetails(teamName, point) {{
      modalTitle.textContent = `${{teamName}} - Week ${{point.week}}`;
      const valueText = point.value == null ? "n/a" : point.value.toFixed(2);
      detailLine1.textContent = `Value: ${{valueText}}`;
      detailLine2.textContent = `${{point.date}} | ${{point.venue}} vs ${{point.opponent}}`;
      detailLine3.textContent = `Result: ${{point.result || "n/a"}}`;
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

    function drawAxes() {{
      ctx.save();
      ctx.fillStyle = "#f8fbff";
      ctx.fillRect(layout.padLeft, layout.chartTop, layout.chartW, layout.panelHeight);
      ctx.restore();

      for (let i = 0; i < data.y_ticks.length; i += 1) {{
        const tick = data.y_ticks[i];
        const label = data.y_tick_labels[i] ?? tick.toFixed(2);
        const y = yFor(tick);
        drawLine(layout.padLeft, y, layout.chartRight, y, {{ color: "#dfe9f5", width: 1 }});
        drawText(label, layout.padLeft - 14, y + 4, {{ align: "right", color: "#3f5f80" }});
        drawText(label, layout.chartRight + 14, y + 4, {{ align: "left", color: "#3f5f80" }});
      }}

      const step = data.max_week <= 10 ? 1 : Math.max(1, Math.floor(data.max_week / 10));
      for (let week = 1; week <= data.max_week; week += step) {{
        const x = xFor(week);
        drawLine(x, layout.chartTop, x, layout.chartBottom, {{ color: "#ebeff4", width: 1 }});
        drawText(`W${{week}}`, x, layout.chartBottom + 24, {{ align: "center", color: "#446180" }});
      }}
      if ((data.max_week - 1) % step !== 0) {{
        const x = xFor(data.max_week);
        drawLine(x, layout.chartTop, x, layout.chartBottom, {{ color: "#ebeff4", width: 1 }});
        drawText(`W${{data.max_week}}`, x, layout.chartBottom + 24, {{ align: "center", color: "#446180" }});
      }}

      drawLine(layout.padLeft, layout.chartBottom, layout.chartRight, layout.chartBottom, {{ color: "#21374f", width: 1.3 }});
      drawLine(layout.padLeft, layout.chartTop, layout.padLeft, layout.chartBottom, {{ color: "#21374f", width: 1.3 }});
      drawLine(layout.chartRight, layout.chartTop, layout.chartRight, layout.chartBottom, {{ color: "#21374f", width: 1.3 }});
      drawText(`Metric: ${{data.metric}}`, layout.padLeft, layout.chartTop - 10, {{ font: styleCfg.font_meta, color: "#2f4b68" }});
    }}

    function drawLegend(progressWeek) {{
      const completedWeek = Math.floor(progressWeek);
      let y = 95;
      for (const team of data.teams) {{
        const idx = Math.max(0, Math.min(completedWeek, team.points.length) - 1);
        const p = idx >= 0 ? team.points[idx] : null;
        drawLine(layout.padLeft, y, layout.padLeft + 18, y, {{ color: team.color, width: styleCfg.line_width }});
        const val = p && p.value != null ? p.value.toFixed(2) : "n/a";
        drawText(`${{team.name}}: value=${{val}}`, layout.padLeft + 24, y + 4, {{ color: "#2c4661" }});
        y += 18;
      }}
    }}

    function drawSeries(progressWeek) {{
      clickTargets = [];
      for (const team of data.teams) {{
        const completedFloor = Math.floor(progressWeek);
        const completed = Math.min(completedFloor, team.points.length);
        const partialIndex = completedFloor;
        const partialFrac = easedFrac(clamp(progressWeek - completedFloor, 0, 1));
        for (let i = 1; i < completed; i += 1) {{
          const a = team.points[i - 1];
          const b = team.points[i];
          if (a.value == null || b.value == null) continue;
          const t = completed <= 1 ? 1 : i / (completed - 1);
          const alpha = styleCfg.line_fade
            ? styleCfg.line_fade_floor + (1 - styleCfg.line_fade_floor) * t
            : 1;
          const segmentColor = styleCfg.line_fade ? colorWithAlpha(team.color, alpha) : team.color;
          drawLine(xFor(a.week), yFor(a.value), xFor(b.week), yFor(b.value), {{
            color: segmentColor,
            width: styleCfg.historical_width
          }});
        }}
        if (partialFrac > 0 && partialIndex > 0 && partialIndex < team.points.length) {{
          const a = team.points[partialIndex - 1];
          const b = team.points[partialIndex];
          if (a.value != null && b.value != null) {{
            const x1 = xFor(a.week);
            const y1 = yFor(a.value);
            const x2 = xFor(b.week);
            const y2 = yFor(b.value);
            const xMid = x1 + (x2 - x1) * partialFrac;
            const yMid = y1 + (y2 - y1) * partialFrac;
            if (styleCfg.segment_glow) {{
              drawLine(x1, y1, xMid, yMid, {{
                color: colorWithAlpha(team.color, 0.34),
                width: styleCfg.line_width + 2.2
              }});
            }}
            drawLine(x1, y1, xMid, yMid, {{
              color: team.color,
              width: styleCfg.line_width
            }});
          }}
        }}
        for (let i = 0; i < completed; i += 1) {{
          const p = team.points[i];
          if (p.value == null) continue;
          const x = xFor(p.week);
          const y = yFor(p.value);
          drawCircle(x, y, styleCfg.point_radius, team.color);
          registerClickTarget(x, y, team.name, p);
        }}
      }}
    }}

    function render(progressWeek) {{
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      drawText("Weekly Metric Animation", layout.padLeft, 34, {{
        font: styleCfg.font_display,
        color: "#13293d"
      }});
      if (!data.has_values) {{
        drawAxes();
        drawLegend(progressWeek);
        drawText("No non-missing values for selected metric.", layout.padLeft + layout.chartW / 2, layout.chartTop + layout.panelHeight / 2, {{
          align: "center",
          color: "#8a5a2b",
          font: styleCfg.font_empty
        }});
      }} else {{
        drawLegend(progressWeek);
        drawAxes();
        drawSeries(progressWeek);
      }}
      weekLabel.textContent = `${{Math.floor(progressWeek)}} / ${{data.max_week}}`;
    }}

    function animate(timestamp) {{
      if (lastTimestamp === null) lastTimestamp = timestamp;
      const delta = timestamp - lastTimestamp;
      lastTimestamp = timestamp;
      if (playing) {{
        progress = clamp(progress + (delta / currentIntervalMs()), 0, data.max_week);
        if (progress >= data.max_week) {{
          playing = false;
          playPauseBtn.textContent = "Play";
        }}
      }}
      render(progress);
      window.requestAnimationFrame(animate);
    }}

    playPauseBtn.addEventListener("click", () => {{
      playing = !playing;
      playPauseBtn.textContent = playing ? "Pause" : "Play";
      if (playing && progress >= data.max_week) progress = 0;
      lastTimestamp = null;
    }});

    resetBtn.addEventListener("click", () => {{
      progress = 0;
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
      canvas.style.cursor = pickTarget(mx, my) ? "pointer" : "default";
    }});

    canvas.addEventListener("click", (event) => {{
      const rect = canvas.getBoundingClientRect();
      const mx = (event.clientX - rect.left) * (canvas.width / rect.width);
      const my = (event.clientY - rect.top) * (canvas.height / rect.height);
      const target = pickTarget(mx, my);
      if (!target) return;
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

    render(progress);
    window.requestAnimationFrame(animate);
  </script>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate animated weekly metric chart HTML."
    )
    parser.add_argument(
        "--source",
        default="csv",
        choices=["csv", "db", "csv-multi", "db-multi"],
        help="Input source mode.",
    )
    parser.add_argument(
        "--csv",
        default="data/football-data.co.uk/E0.csv",
        help="Path to E0.csv for --source csv.",
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
        "--data-dir",
        default="data/football-data.co.uk",
        help="Directory containing E0.csv and E0-YYYYYYYY.csv files for --source csv-multi.",
    )
    parser.add_argument(
        "--seasons",
        default=None,
        help="Optional season filters for --source db/db-multi/csv-multi (YYYY-YYYY or YYYYYYYY, comma-delimited).",
    )
    parser.add_argument(
        "--include-current",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="For --source csv-multi: include data-dir/E0.csv in addition to E0-YYYYYYYY.csv files.",
    )
    parser.add_argument(
        "--current-label",
        default=None,
        help="For --source csv-multi: optional label override for E0.csv (e.g., 2025-2026).",
    )
    parser.add_argument(
        "--team",
        default="Arsenal",
        help="Team name(s), comma-delimited.",
    )
    parser.add_argument(
        "--side",
        default="both",
        choices=["home", "away", "both"],
        help="Filter matches by venue.",
    )
    parser.add_argument(
        "--metric",
        default="opponent_fouls",
        help="Normalized metric field to animate.",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=500,
        help="Animation interval in milliseconds between weeks.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional chart title override.",
    )
    parser.add_argument(
        "--style",
        default="classic",
        choices=["classic", "cinematic"],
        help="Visual style preset.",
    )
    parser.add_argument(
        "--out",
        default="docs/weekly_opponent_fouls_animated.html",
        help="Output HTML path.",
    )
    args = parser.parse_args()

    teams = parse_teams(args.team)
    style = _resolve_style(args.style)
    season_filter = parse_season_filter(args.seasons)
    if args.source == "csv-multi":
        series, sources = build_multi_season_metric_series(
            data_dir=args.data_dir,
            teams=teams,
            side=args.side,
            metric=args.metric,
            seasons=season_filter,
            include_current=args.include_current,
            current_label=args.current_label,
        )
        season_labels: list[str] = sorted({source.label for source in sources})
    elif args.source == "db-multi":
        series, season_labels = build_db_multi_season_metric_series(
            teams=teams,
            side=args.side,
            metric=args.metric,
            db_path=args.db,
            competition_code=args.competition,
            seasons=season_filter,
        )
        sources = []
    else:
        series = build_team_metric_series(
            source=args.source,
            teams=teams,
            side=args.side,
            metric=args.metric,
            csv_path=args.csv,
            db_path=args.db,
            competition_code=args.competition,
            seasons=season_filter,
        )
        sources = []
        season_labels = []

    payload = _build_payload(series, metric=args.metric, style=style)
    title = args.title or (" / ".join(teams) + f": Weekly {args.metric}")
    write_metric_animation_html(
        out_path=Path(args.out),
        payload=payload,
        interval_ms=max(50, args.interval_ms),
        title=title,
        style=style,
    )

    print(f"Wrote {args.out}")
    print(f"Source: {args.source}")
    print(f"Metric: {args.metric}")
    print(f"Style: {style}")
    print(f"Interval: {max(50, args.interval_ms)}ms per week")
    if args.source in {"csv-multi", "db-multi"}:
        print(f"Seasons discovered: {', '.join(season_labels)}")
        print(f"Series plotted: {len(series)}")
    for team in teams:
        matching_keys = [
            key for key in series.keys() if key == team or key.startswith(f"{team} (")
        ]
        for key in matching_keys:
            values = [point.value for point in series[key] if point.value is not None]
            last = "n/a" if not values else f"{values[-1]:.2f}"
            print(
                f"{key}: weeks={len(series[key])}, "
                f"non_missing={len(values)}, latest={last}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
