#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def default_report_html_path(json_path: Path) -> Path:
    return json_path.with_suffix(".html")


def _resolve_style(style: str) -> str:
    key = style.strip().lower()
    if key not in {"classic", "cinematic"}:
        raise ValueError("style must be 'classic' or 'cinematic'")
    return key


def _theme_vars(style: str) -> dict[str, str]:
    if style == "cinematic":
        return {
            "bg": "#f3efe6",
            "panel": "#fffdf9",
            "ink": "#182c3f",
            "muted": "#4b6073",
            "line": "#d6e1ec",
            "accent": "#b15b1d",
            "font_main": "'Trebuchet MS', 'Avenir Next', sans-serif",
            "font_display": "'Arial Narrow', 'Trebuchet MS', sans-serif",
        }
    return {
        "bg": "#f5f8fc",
        "panel": "#ffffff",
        "ink": "#1b2f42",
        "muted": "#566a7f",
        "line": "#d7e2ee",
        "accent": "#0b6dfa",
        "font_main": "'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
        "font_display": "'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif",
    }


def _polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _relative_href(value: str, *, out_dir: Path) -> str:
    text = value.strip()
    if not text:
        return text
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"}:
        local = unquote(parsed.path or "")
        if parsed.query:
            local += f"?{parsed.query}"
        if parsed.fragment:
            local += f"#{parsed.fragment}"
        local = local.lstrip("/")
        return local or "#"
    if parsed.scheme in {"mailto", "tel", "data", "javascript"}:
        return text
    if text.startswith("#"):
        return text
    if parsed.scheme == "file":
        text = unquote(parsed.path)

    path = Path(text)
    if path.is_absolute():
        rel = os.path.relpath(str(path), str(out_dir))
        return Path(rel).as_posix()
    return Path(text).as_posix()


def _render_trend_svg(weekly_rows: list[dict[str, Any]]) -> str:
    width = 900
    height = 240
    pad_left = 44
    pad_right = 20
    pad_top = 20
    pad_bottom = 32
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    if not weekly_rows:
        return (
            f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}'>"
            "<text x='20' y='30' fill='#9CA3AF'>No data</text></svg>"
        )

    max_week = max(int(row["week"]) for row in weekly_rows)
    max_points = max(float(row["running_league_points"]) for row in weekly_rows)
    max_points = max(3.0, max_points)

    def x_for(week: int) -> float:
        if max_week <= 1:
            return pad_left + plot_w / 2
        return pad_left + (week - 1) * plot_w / (max_week - 1)

    def y_top(value: float) -> float:
        clipped = max(0.0, min(1.0, value))
        return pad_top + (1.0 - clipped) * plot_h

    def y_bottom(value: float) -> float:
        clipped = max(0.0, min(max_points, value))
        return pad_top + (1.0 - clipped / max_points) * plot_h

    avg_points = [
        (x_for(int(row["week"])), y_top(float(row["half_win_average"])))
        for row in weekly_rows
    ]
    league_points = [
        (x_for(int(row["week"])), y_bottom(float(row["running_league_points"])))
        for row in weekly_rows
    ]
    grid_lines = []
    for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = y_top(frac)
        grid_lines.append(
            f"<line x1='{pad_left:.2f}' y1='{y:.2f}' x2='{pad_left + plot_w:.2f}' y2='{y:.2f}' "
            "stroke='rgba(255,255,255,0.08)' stroke-width='1'/>"
        )
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        "role='img' aria-label='Weekly trend chart'>"
        + "".join(grid_lines)
        + f"<polyline points='{_polyline(avg_points)}' fill='none' stroke='#CF102D' stroke-width='2.8'/>"
        + f"<polyline points='{_polyline(league_points)}' fill='none' stroke='#9CA3AF' stroke-width='2.2' stroke-dasharray='5 4'/>"
        + f"<line x1='{pad_left:.2f}' y1='{pad_top + plot_h:.2f}' x2='{pad_left + plot_w:.2f}' y2='{pad_top + plot_h:.2f}' stroke='rgba(255,255,255,0.2)' stroke-width='1.2'/>"
        + f"<line x1='{pad_left:.2f}' y1='{pad_top:.2f}' x2='{pad_left:.2f}' y2='{pad_top + plot_h:.2f}' stroke='rgba(255,255,255,0.2)' stroke-width='1.2'/>"
        + f"<text x='{pad_left + 4:.2f}' y='{pad_top + 14:.2f}' fill='#CF102D' font-size='12'>half-win average</text>"
        + f"<text x='{pad_left + 140:.2f}' y='{pad_top + 14:.2f}' fill='#9CA3AF' font-size='12'>running league points</text>"
        + "</svg>"
    )


def _section_heading(label: str) -> str:
    return (
        "<div class='section-head'>"
        f"<p class='section-label'>{_escape_html(label)}</p>"
        "</div>"
    )


def _looks_like_path_string(text: str) -> bool:
    return (
        text.startswith(("./", "../"))
        or "/" in text
        or "\\" in text
        or text.endswith((".md", ".markdown", ".txt", ".html", ".htm"))
    )


def _extract_candidate_story_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if _looks_like_path_string(text):
            return None
        return text
    if isinstance(value, list):
        for item in value:
            text = _extract_candidate_story_text(item)
            if text:
                return text
        return None
    if not isinstance(value, dict):
        return None
    for key in (
        "content",
        "body",
        "markdown",
        "html",
        "draft",
        "writeup",
        "article",
        "text",
        "story_text",
        "longform",
        "longform_markdown",
        "post",
        "blog",
        "article_markdown",
        "article_text",
    ):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            text = candidate.strip()
            if _looks_like_path_string(text):
                return None
            return text
    return None


def _extract_story_from_path_dict(value: Any, *, base_dir: Path) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("path", "file", "filepath", "markdown_path", "html_path"):
        candidate = value.get(key)
        if not isinstance(candidate, str):
            continue
        text = candidate.strip()
        if not text or text.startswith(("http://", "https://")):
            continue
        path = Path(text)
        resolved = path if path.is_absolute() else (base_dir / path)
        if not resolved.exists() or not resolved.is_file():
            continue
        try:
            # Cap story reads so oversized files do not bloat the rendered HTML.
            contents = resolved.read_text(encoding="utf-8")[:200_000].strip()
        except OSError:
            continue
        if contents:
            return contents
    return None


def _extract_story_from_path_string(value: Any, *, base_dir: Path) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if (
        not text
        or text.startswith(("http://", "https://", "#"))
    ):
        return None
    if not _looks_like_path_string(text):
        return None
    path = Path(text)
    resolved = path if path.is_absolute() else (base_dir / path)
    if not resolved.exists() or not resolved.is_file():
        return None
    try:
        # Cap story reads so oversized files do not bloat the rendered HTML.
        contents = resolved.read_text(encoding="utf-8")[:200_000].strip()
    except OSError:
        return None
    return contents or None


def _search_story_container(
    value: Any,
    *,
    base_dir: Path,
    seen: set[int] | None = None,
) -> str | None:
    if seen is None:
        seen = set()
    if isinstance(value, (dict, list)):
        value_id = id(value)
        if value_id in seen:
            return None
        seen.add(value_id)
    text = _extract_story_from_path_dict(value, base_dir=base_dir)
    if text:
        return text
    text = _extract_story_from_path_string(value, base_dir=base_dir)
    if text:
        return text
    text = _extract_candidate_story_text(value)
    if text:
        return text
    if isinstance(value, dict):
        for nested in value.values():
            text = _search_story_container(nested, base_dir=base_dir, seen=seen)
            if text:
                return text
    elif isinstance(value, list):
        for item in value:
            text = _search_story_container(item, base_dir=base_dir, seen=seen)
            if text:
                return text
    return None


def _extract_longform_story(
    *,
    report: dict[str, Any],
    team_name: str,
    season: str,
    season_block: dict[str, Any],
    base_dir: Path,
) -> str | None:
    for key in ("blog_post", "story"):
        text = _search_story_container(season_block.get(key), base_dir=base_dir)
        if text:
            return text
    text = _search_story_container(season_block.get("narrative"), base_dir=base_dir)
    if text:
        return text
    text = _search_story_container(season_block.get("recommended_story"), base_dir=base_dir)
    if text:
        return text
    for key in ("writeups", "posts", "blog", "stories", "narratives"):
        text = _search_story_container(season_block.get(key), base_dir=base_dir)
        if text:
            return text

    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        return None

    def _matches(item: dict[str, Any]) -> bool:
        return str(item.get("team")) == team_name and str(item.get("season")) == season

    for key in ("blog_posts", "stories"):
        items = artifacts.get(key)
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict) or not _matches(item):
                    continue
                text = _search_story_container(item, base_dir=base_dir)
                if text:
                    return text
        elif isinstance(items, dict):
            text = _search_story_container(items, base_dir=base_dir)
            if text:
                return text
    return None


def _render_rich_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parts: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    ordered_items: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            parts.append(f"<p>{_escape_html(' '.join(paragraph).strip())}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            parts.append("<ul>" + "".join(list_items) + "</ul>")
            list_items = []

    def flush_ordered_list() -> None:
        nonlocal ordered_items
        if ordered_items:
            parts.append("<ol>" + "".join(ordered_items) + "</ol>")
            ordered_items = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            parts.append(f"<h4>{_escape_html(line[4:].strip())}</h4>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            parts.append(f"<h3>{_escape_html(line[3:].strip())}</h3>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            parts.append(f"<h2>{_escape_html(line[2:].strip())}</h2>")
            continue
        if line.startswith("- "):
            flush_paragraph()
            flush_ordered_list()
            list_items.append(f"<li>{_escape_html(line[2:].strip())}</li>")
            continue
        ordered_match = None
        if len(line) > 3 and line[0].isdigit():
            prefix, sep, remainder = line.partition(". ")
            if sep and prefix.isdigit() and remainder.strip():
                ordered_match = remainder.strip()
        if ordered_match is not None:
            flush_paragraph()
            flush_list()
            ordered_items.append(f"<li>{_escape_html(ordered_match)}</li>")
            continue
        if line.startswith("> "):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            parts.append(f"<blockquote>{_escape_html(line[2:].strip())}</blockquote>")
            continue
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    flush_ordered_list()
    return "".join(parts)


def _render_lead_story(
    *,
    report: dict[str, Any],
    team_name: str,
    season: str,
    summary: dict[str, Any],
    weekly_rows: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    longform_story: str | None,
) -> str:
    latest = weekly_rows[-1] if weekly_rows else {}
    latest_week = latest.get("week", "n/a")
    latest_result = str(latest.get("result", "n/a"))
    latest_opponent = str(latest.get("opponent", "opponent"))
    latest_score = f"{latest.get('goals_for', 'n/a')}-{latest.get('goals_against', 'n/a')}"
    record = (
        f"{summary.get('wins', 0)} wins, {summary.get('draws', 0)} draws, "
        f"{summary.get('losses', 0)} losses"
    )
    headline = f"{team_name} {season}: what this week meant"
    quote = ""
    findings_html = ""
    if findings:
        lead_finding = findings[0]
        headline = str(lead_finding.get("title") or headline)
        quote = str(lead_finding.get("summary") or "").strip()
        if quote:
            quote = f"<blockquote>{_escape_html(quote)}</blockquote>"
        findings_html = (
            f"<p>{_escape_html(str(lead_finding.get('summary', '')))}</p>"
            if str(lead_finding.get("summary", "")).strip()
            else ""
        )

    if longform_story and longform_story.strip():
        story_text = longform_story.strip()
        story_lines = story_text.splitlines()
        derived_headline = headline
        if story_lines:
            first = story_lines[0].strip()
            if first.startswith("# "):
                derived_headline = first[2:].strip() or headline
                story_text = "\n".join(story_lines[1:]).strip()
            elif first.startswith("## "):
                derived_headline = first[3:].strip() or headline
                story_text = "\n".join(story_lines[1:]).strip()
        story_html = _render_rich_text(story_text)
        return (
            "<section class='lead-story'>"
            f"<h2>{_escape_html(derived_headline)}</h2>"
            f"{story_html}"
            "</section>"
        )

    lead_paragraph = (
        f"Week {latest_week} ended with {team_name} {latest_result} against "
        f"{latest_opponent}. The latest scoreline landed at {latest_score}, and the "
        f"season now sits at {record} across {summary.get('matches', 0)} matches."
    )
    context_paragraph = (
        f"The running picture remains defined by a latest half-win average of "
        f"{float(summary.get('latest_half_win_average', 0.0)):.3f} and "
        f"{float(summary.get('latest_running_league_points', 0.0)):.0f} running league points. "
        "This page starts with the narrative read, then moves into the supporting evidence."
    )
    return (
        "<section class='lead-story'>"
        f"<h2>{_escape_html(headline)}</h2>"
        f"<p>{_escape_html(lead_paragraph)}</p>"
        f"{findings_html}"
        f"{quote}"
        f"<p>{_escape_html(context_paragraph)}</p>"
        "</section>"
    )


def _render_findings(
    findings: list[dict[str, Any]],
    *,
    weekly_rows: list[dict[str, Any]],
    out_dir: Path,
) -> str:
    if not findings:
        return "<p class='muted'>No flagged findings for this season.</p>"
    annotations_by_week: dict[int, dict[str, Any]] = {}
    for row in weekly_rows:
        annotation = row.get("annotation")
        week = row.get("week")
        if not isinstance(annotation, dict):
            continue
        try:
            week_int = int(week)
        except (TypeError, ValueError):
            continue
        annotations_by_week[week_int] = annotation

    cards: list[str] = []
    for finding in findings:
        weeks = finding.get("weeks") or []
        weeks_text = ", ".join(str(value) for value in weeks[:8])
        if weeks_text:
            weeks_text = f"<p class='mini'>Weeks: {weeks_text}</p>"
        matched_annotations: list[str] = []
        for week in weeks:
            try:
                week_int = int(week)
            except (TypeError, ValueError):
                continue
            annotation = annotations_by_week.get(week_int)
            if annotation is None:
                continue
            ann_type = str(annotation.get("type") or "note").strip().lower()
            title = str(
                annotation.get("title")
                or annotation.get("event")
                or "Annotated event"
            ).strip()
            note = str(
                annotation.get("note")
                or annotation.get("summary")
                or annotation.get("text")
                or ""
            ).strip()
            link = str(
                annotation.get("url")
                or annotation.get("media_url")
                or annotation.get("video_url")
                or annotation.get("image_url")
                or ""
            ).strip()
            link_html = ""
            if link:
                safe_link = _escape_html(_relative_href(link, out_dir=out_dir))
                link_html = (
                    f" (<a href='{safe_link}' target='_blank' "
                    "rel='noopener noreferrer'>link</a>)"
                )
            detail = _escape_html(title)
            if note:
                detail += f": {_escape_html(note)}"
            matched_annotations.append(
                f"<li><span class='ann-type-chip ann-type-{_escape_html(ann_type)}'>"
                f"{_escape_html(ann_type)}</span> "
                f"W{week_int} - {detail}{link_html}</li>"
            )
        annotation_block = ""
        if matched_annotations:
            annotation_block = (
                "<details><summary>Matched annotations</summary>"
                "<ul class='mini-list'>"
                + "".join(matched_annotations)
                + "</ul></details>"
            )
        evidence = json.dumps(finding.get("evidence", {}), indent=2)
        cards.append(
            "<article class='finding'>"
            f"<h5>{_escape_html(str(finding.get('title', 'Finding')))}</h5>"
            f"<p>{_escape_html(str(finding.get('summary', '')))}</p>"
            f"{weeks_text}"
            f"{annotation_block}"
            f"<details><summary>Evidence</summary><pre>{_escape_html(evidence)}</pre></details>"
            "</article>"
        )
    return "".join(cards)


def _render_week_table(weekly_rows: list[dict[str, Any]], *, out_dir: Path) -> str:
    def annotation_cell(row: dict[str, Any]) -> str:
        annotation = row.get("annotation")
        if not isinstance(annotation, dict):
            return ""
        ann_type = str(annotation.get("type") or "").strip().lower()
        title = str(annotation.get("title") or annotation.get("event") or "").strip()
        note = str(
            annotation.get("note")
            or annotation.get("summary")
            or annotation.get("text")
            or ""
        ).strip()
        link = str(
            annotation.get("url")
            or annotation.get("media_url")
            or annotation.get("video_url")
            or annotation.get("image_url")
            or ""
        ).strip()
        parts: list[str] = []
        if ann_type:
            parts.append(_escape_html(f"[{ann_type}]"))
        if title:
            parts.append(_escape_html(title))
        if note:
            parts.append(_escape_html(note))
        if link:
            safe_link = _escape_html(_relative_href(link, out_dir=out_dir))
            parts.append(
                f"<a href='{safe_link}' target='_blank' rel='noopener noreferrer'>link</a>"
            )
        return " | ".join(parts)

    rows: list[str] = []
    for row in weekly_rows:
        rows.append(
            "<tr>"
            f"<td>{row['week']}</td>"
            f"<td>{_escape_html(str(row['date']))}</td>"
            f"<td>{_escape_html(str(row['opponent']))}</td>"
            f"<td>{_escape_html(str(row['venue']))}</td>"
            f"<td>{_escape_html(str(row['result']))}</td>"
            f"<td>{float(row['half_win_average']):.3f}</td>"
            f"<td>{float(row['running_league_points']):.0f}</td>"
            f"<td>{row.get('shots', 'n/a')}</td>"
            f"<td>{row.get('opponent_shots', 'n/a')}</td>"
            f"<td>{row.get('fouls', 'n/a')}</td>"
            f"<td>{row.get('opponent_fouls', 'n/a')}</td>"
            f"<td>{annotation_cell(row)}</td>"
            "</tr>"
        )
    return (
        "<table>"
        "<caption>Per-week normalized stats</caption>"
        "<thead><tr>"
        "<th scope='col'>Week</th><th scope='col'>Date</th><th scope='col'>Opponent</th><th scope='col'>Venue</th><th scope='col'>Result</th>"
        "<th scope='col'>Half-win avg</th><th scope='col'>Pts</th><th scope='col'>Shots</th><th scope='col'>Opp shots</th><th scope='col'>Fouls</th><th scope='col'>Opp fouls</th><th scope='col'>Annotation</th>"
        "</tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_annotations(weekly_rows: list[dict[str, Any]], *, out_dir: Path) -> str:
    annotated = [
        row
        for row in weekly_rows
        if isinstance(row.get("annotation"), dict)
    ]
    if not annotated:
        return ""
    cards: list[str] = []
    for row in annotated:
        annotation = row["annotation"]
        ann_type = str(annotation.get("type") or "note").strip().lower()
        title = str(annotation.get("title") or annotation.get("event") or "Annotated event")
        note = str(
            annotation.get("note")
            or annotation.get("summary")
            or annotation.get("text")
            or ""
        ).strip()
        link = str(
            annotation.get("url")
            or annotation.get("media_url")
            or annotation.get("video_url")
            or annotation.get("image_url")
            or ""
        ).strip()
        link_block = ""
        if link:
            safe_link = _escape_html(_relative_href(link, out_dir=out_dir))
            link_block = (
                f"<p class='mini'><a href='{safe_link}' target='_blank' "
                "rel='noopener noreferrer'>Open media/event link</a></p>"
            )
        cards.append(
            f"<article class='finding ann-type-{_escape_html(ann_type)}'>"
            f"<h5>W{row.get('week')}: {_escape_html(title)}</h5>"
            f"<p class='ann-type-label'>Type: {_escape_html(ann_type)}</p>"
            f"<p>{_escape_html(note)}</p>"
            f"{link_block}"
            "</article>"
        )
    return "".join(cards)


def _render_embedded_animations(
    *,
    report: dict[str, Any],
    team: str,
    season: str,
    out_dir: Path,
) -> str:
    artifacts = report.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return ""
    embeds = artifacts.get("embedded_animations", [])
    if not isinstance(embeds, list):
        return ""
    selected = [
        item
        for item in embeds
        if isinstance(item, dict)
        and str(item.get("team")) == team
        and str(item.get("season")) == season
        and isinstance(item.get("path"), str)
    ]
    if not selected:
        return ""
    blocks: list[str] = []
    for item in selected:
        kind = _escape_html(str(item.get("kind", "animation")))
        metric = item.get("metric")
        title = f"{kind} animation"
        if metric:
            title = f"{kind} animation ({_escape_html(str(metric))})"
        src = _escape_html(_relative_href(str(item["path"]), out_dir=out_dir))
        blocks.append(
            "<article class='embed'>"
            f"<h5>{title}</h5>"
            f"<iframe title='{title}' src='{src}' loading='lazy' referrerpolicy='no-referrer'></iframe>"
            "</article>"
        )
    return "<div class='embeds'>" + "".join(blocks) + "</div>"


def render_report_html(
    report: dict[str, Any],
    *,
    out_path: Path,
    in_path: Path,
    style: str = "classic",
) -> None:
    style_key = _resolve_style(style)
    theme = _theme_vars(style_key)
    input_block = report.get("input", {})
    teams = [str(value) for value in input_block.get("teams", [])]
    seasons = [str(value) for value in input_block.get("seasons", [])]
    title = " / ".join(teams) + " Weekly Report"
    subtitle = (
        f"Competition {input_block.get('competition_code')} | "
        f"Seasons {', '.join(seasons)} | "
        f"Generated {report.get('generated_at')}"
    )
    hero_chips = [
        f"<span class='stat-chip'>Competition: {_escape_html(str(input_block.get('competition_code', 'n/a')))}</span>",
        f"<span class='stat-chip'>Teams: {len(teams)}</span>",
        f"<span class='stat-chip'>Seasons: {len(seasons)}</span>",
        f"<span class='stat-chip'>Generated: {_escape_html(str(report.get('generated_at', 'n/a')))}</span>",
    ]

    sections: list[str] = []
    debug_enabled = os.environ.get("FOOTSTAT_DEBUG") == "1"
    for team_block in report.get("teams", []):
        team_name = str(team_block.get("team"))
        for season_block in team_block.get("seasons", []):
            season = str(season_block.get("season"))
            summary = season_block.get("summary", {})
            weekly_rows = list(season_block.get("weekly_rows", []))
            findings = list(season_block.get("findings", []))
            longform_story = _extract_longform_story(
                report=report,
                team_name=team_name,
                season=season,
                season_block=season_block,
                base_dir=in_path.parent,
            )
            if debug_enabled:
                if longform_story:
                    print(f"[story] {team_name} {season}: FOUND (len={len(longform_story)})")
                else:
                    print(f"[story] {team_name} {season}: MISSING")
                    print(f"[story] season_block keys: {sorted(season_block.keys())}")
                    artifacts = report.get('artifacts', {})
                    artifact_keys = sorted(artifacts.keys()) if isinstance(artifacts, dict) else []
                    print(f"[story] artifacts keys: {artifact_keys}")
            embedded = _render_embedded_animations(
                report=report,
                team=team_name,
                season=season,
                out_dir=out_path.parent,
            )
            annotations_html = _render_annotations(weekly_rows, out_dir=out_path.parent)
            embedded_block = (
                "<h4>Embedded animations</h4>" + embedded if embedded else ""
            )
            annotations_panel = (
                "<div class='content-panel'>"
                f"{_section_heading('Event / Media Annotations')}"
                f"{annotations_html}"
                "</div>"
                if annotations_html
                else ""
            )
            sections.append(
                _render_lead_story(
                    report=report,
                    team_name=team_name,
                    season=season,
                    summary=summary,
                    weekly_rows=weekly_rows,
                    findings=findings,
                    longform_story=longform_story,
                )
                + "<div class='section-transition'></div>"
                + "<section class='card'>"
                f"<div class='card-top'><h3>{_escape_html(team_name)} ({_escape_html(season)})</h3>"
                f"<p class='mini'>Matches={summary.get('matches')} | "
                f"W/D/L={summary.get('wins')}/{summary.get('draws')}/{summary.get('losses')} | "
                f"Findings={summary.get('findings_count')}</p></div>"
                "<div class='content-panel'>"
                f"{_section_heading('Trend')}"
                "<div class='chart-shell'>"
                f"{_render_trend_svg(weekly_rows)}"
                "</div>"
                f"{embedded_block}"
                "</div>"
                + annotations_panel
                + "<div class='content-panel'>"
                f"{_section_heading('Weird Findings')}"
                f"{_render_findings(findings, weekly_rows=weekly_rows, out_dir=out_path.parent)}"
                "</div>"
                "<div class='content-panel'>"
                f"{_section_heading('Week Drill-Down')}"
                "<details><summary>Show week table</summary>"
                f"{_render_week_table(weekly_rows, out_dir=out_path.parent)}"
                "</details>"
                "</div>"
                "</section>"
            )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape_html(title)}</title>
  <style>
    :root {{
      --bg:#0B0F14;
      --panel:#111827;
      --deep:#0B1118;
      --ink:#F3F4F6;
      --muted:#9CA3AF;
      --line:rgba(255,255,255,0.08);
      --accent:#CF102D;
      --accent-deep:#9C1C1C;
      --gold:#D4AF37;
      --focus:#CF102D;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      padding:0;
      color:var(--ink);
      background:
        radial-gradient(900px 520px at 18% 8%, rgba(207,16,45,0.06) 0%, transparent 48%),
        radial-gradient(700px 420px at 86% 12%, rgba(156,28,28,0.05) 0%, transparent 42%),
        var(--bg);
      font-family:{theme["font_main"]};
      line-height:1.45;
    }}
    .wrap {{ max-width:72rem; margin:0 auto; padding:0 20px 64px; }}
    .hero {{
      min-height:70vh;
      background:var(--deep);
      position:relative;
      overflow:hidden;
      display:flex;
      align-items:flex-end;
      padding:56px 0 40px;
      margin-bottom:40px;
      border-bottom:1px solid rgba(207,16,45,0.18);
    }}
    .hero::before {{
      content:"";
      position:absolute;
      inset:auto auto -120px -120px;
      width:420px;
      height:420px;
      background:radial-gradient(circle, rgba(207,16,45,0.10) 0%, rgba(207,16,45,0.05) 38%, transparent 75%);
      pointer-events:none;
      filter:blur(14px);
    }}
    .hero-inner {{
      width:100%;
      max-width:72rem;
      margin:0 auto;
      padding:0 20px;
      position:relative;
      z-index:1;
    }}
    .hero::after {{
      content:"";
      position:absolute;
      inset:0;
      background:radial-gradient(circle at center, transparent 60%, rgba(0,0,0,0.35) 100%);
      pointer-events:none;
    }}
    .hero-meta {{
      margin-bottom:14px;
      position:relative;
      z-index:1;
    }}
    .eyebrow-top {{
      margin:0;
      font-size:11px;
      letter-spacing:0.28em;
      text-transform:uppercase;
      color:var(--muted);
      opacity:0.75;
      font-weight:700;
    }}
    .eyebrow-bottom {{
      margin:6px 0 0 0;
      font-size:12px;
      letter-spacing:0.18em;
      text-transform:uppercase;
      color:var(--accent);
      font-weight:700;
    }}
    h1 {{ margin:0; font-size:clamp(3rem, 6vw, 5rem); line-height:0.95; font-family:{theme["font_display"]}; font-weight:900; color:var(--accent); text-shadow:0 0 18px rgba(207,16,45,0.25); }}
    .hero-divider {{
      width:80px;
      height:2px;
      background:var(--accent);
      margin:18px 0 20px 0;
      opacity:0.6;
    }}
    .sub {{ margin:0; max-width:36rem; color:var(--muted); opacity:0.85; font-size:1rem; }}
    .hero-stats {{
      display:flex;
      flex-wrap:wrap;
      gap:12px;
      margin-top:28px;
    }}
    .stat-chip {{
      display:inline-flex;
      align-items:center;
      padding:8px 12px;
      border-radius:999px;
      background:rgba(255,255,255,0.04);
      border:1px solid rgba(255,255,255,0.05);
      color:var(--ink);
      font-size:11px;
      transition:transform .18s ease, border-color .18s ease, background .18s ease;
    }}
    .stat-chip:hover {{
      transform:translateY(-2px);
      border-color:rgba(207,16,45,0.30);
      background:rgba(255,255,255,0.07);
    }}
    .card {{
      background:var(--panel);
      border:1px solid rgba(255,255,255,0.05);
      border-radius:16px;
      padding:32px 28px 36px;
      margin-top:5rem;
      box-shadow:0 18px 50px rgba(0,0,0,0.35);
      transition:transform .18s ease, border-color .18s ease;
    }}
    .card:hover {{
      transform:translateY(-1px);
      border-color:rgba(207,16,45,0.20);
    }}
    .lead-story {{
      max-width:52rem;
      margin:6rem auto 5rem auto;
      padding:0 20px;
    }}
    .lead-story h2 {{
      font-size:2.2rem;
      font-weight:800;
      color:var(--accent);
      margin:0 0 1.25rem 0;
      font-family:{theme["font_display"]};
    }}
    .lead-story p {{
      font-size:1.1rem;
      line-height:1.75;
      color:var(--ink);
      margin:0 0 1.2rem 0;
    }}
    .lead-story blockquote {{
      border-left:3px solid var(--accent);
      padding-left:16px;
      margin:2rem 0;
      color:var(--muted);
      font-style:italic;
    }}
    .section-transition {{
      height:1px;
      max-width:60rem;
      margin:3rem auto;
      background:linear-gradient(
        to right,
        transparent,
        rgba(207,16,45,0.35),
        transparent
      );
    }}
    .card-top {{
      margin-bottom:18px;
    }}
    h3 {{ margin:0 0 8px 0; font-size:1.6rem; font-family:{theme["font_display"]}; color:var(--accent); opacity:0.9; }}
    h4 {{ margin:10px 0; font-size:1.2rem; color:var(--muted); }}
    h5 {{ margin:10px 0; }}
    .mini {{ color:var(--muted); font-size:13px; margin:6px 0; }}
    .muted {{ color:var(--muted); }}
    .section-head {{
      border-bottom:1px solid rgba(255,255,255,0.05);
      padding-bottom:8px;
      margin-bottom:24px;
    }}
    .section-label {{
      margin:0;
      font-size:12px;
      letter-spacing:0.22em;
      text-transform:uppercase;
      color:var(--accent);
      opacity:0.85;
      font-weight:700;
    }}
    .content-panel {{
      background:var(--deep);
      border:1px solid rgba(255,255,255,0.05);
      border-radius:12px;
      padding:16px;
      margin-top:18px;
    }}
    .content-panel p {{
      margin-bottom:1rem;
    }}
    .chart-shell {{
      background:var(--deep);
      border:1px solid rgba(255,255,255,0.05);
      border-radius:12px;
      padding:16px;
    }}
    .finding {{
      border:1px solid rgba(255,255,255,0.05);
      border-left:4px solid var(--accent);
      border-radius:10px;
      padding:12px;
      margin-bottom:10px;
      background:rgba(255,255,255,0.02);
    }}
    .mini-list {{
      margin:8px 0 0 18px;
      padding:0;
    }}
    .ann-type-label {{
      display:inline-block;
      margin:0 0 6px 0;
      font-size:12px;
      color:var(--muted);
      border:1px solid rgba(255,255,255,0.08);
      background:rgba(255,255,255,0.05);
      border-radius:999px;
      padding:2px 8px;
    }}
    .ann-type-chip {{
      display:inline-block;
      font-size:11px;
      border-radius:999px;
      border:1px solid rgba(255,255,255,0.08);
      background:rgba(255,255,255,0.05);
      color:var(--muted);
      padding:1px 6px;
      margin-right:6px;
      vertical-align:middle;
    }}
    .ann-type-event {{
      border-left-color:var(--gold);
      background:rgba(212,175,55,0.08);
    }}
    .ann-type-event .ann-type-label,
    .ann-type-chip.ann-type-event {{
      border-color:rgba(212,175,55,0.25);
      background:rgba(212,175,55,0.10);
      color:var(--gold);
    }}
    .ann-type-injury {{
      border-left-color:var(--accent-deep);
      background:rgba(156,28,28,0.10);
    }}
    .ann-type-injury .ann-type-label,
    .ann-type-chip.ann-type-injury {{
      border-color:rgba(207,16,45,0.24);
      background:rgba(207,16,45,0.10);
      color:#f7c1ca;
    }}
    .ann-type-tactical {{
      border-left-color:#9CA3AF;
      background:rgba(255,255,255,0.03);
    }}
    .ann-type-tactical .ann-type-label,
    .ann-type-chip.ann-type-tactical {{
      border-color:rgba(255,255,255,0.08);
      background:rgba(255,255,255,0.05);
      color:#d1d5db;
    }}
    .ann-type-media {{
      border-left-color:#9CA3AF;
      background:rgba(255,255,255,0.03);
    }}
    .ann-type-media .ann-type-label,
    .ann-type-chip.ann-type-media {{
      border-color:rgba(255,255,255,0.08);
      background:rgba(255,255,255,0.05);
      color:#d1d5db;
    }}
    .embeds {{
      display:grid;
      grid-template-columns:repeat(auto-fit, minmax(340px, 1fr));
      gap:12px;
      margin-bottom:8px;
    }}
    .embed {{
      border:1px solid rgba(255,255,255,0.05);
      border-radius:10px;
      padding:12px;
      background:rgba(255,255,255,0.02);
    }}
    .embed h5 {{
      margin:4px 0 8px 0;
    }}
    .embed iframe {{
      width:100%;
      min-height:340px;
      border:1px solid rgba(255,255,255,0.05);
      border-radius:8px;
      background:var(--deep);
    }}
    details > summary:focus-visible,
    iframe:focus-visible {{
      outline:3px solid var(--focus);
      outline-offset:2px;
      border-radius:6px;
    }}
    details > summary {{
      cursor:pointer;
      color:var(--ink);
    }}
    pre {{
      margin:8px 0 0 0;
      padding:8px;
      border-radius:8px;
      background:rgba(255,255,255,0.03);
      border:1px solid rgba(255,255,255,0.06);
      overflow:auto;
      font-size:12px;
    }}
    table {{ width:100%; border-collapse:collapse; margin-top:10px; font-size:13px; }}
    th,td {{ border:1px solid rgba(255,255,255,0.05); padding:6px; text-align:left; }}
    th {{ background:rgba(255,255,255,0.05); }}
    svg {{ width:100%; height:auto; border:1px solid rgba(255,255,255,0.05); border-radius:8px; background:var(--deep); }}
    footer {{
      text-align:center;
      color:#6b7280;
      font-size:12px;
      margin-top:48px;
    }}
    @media (max-width: 768px) {{
      .hero {{ min-height:auto; padding:40px 0 28px; }}
      .wrap {{ padding:0 16px 56px; }}
      .card {{ margin-top:3.5rem; padding:20px; }}
      .embeds {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <section class="hero">
    <div class="hero-inner">
      <div class="hero-meta">
        <p class="eyebrow-top">Arsenal Analytics Lab</p>
        <p class="eyebrow-bottom">{_escape_html(str(input_block.get('competition_code', 'Competition')))} - {_escape_html(", ".join(seasons).replace("-", "/"))}</p>
      </div>
      <h1>{_escape_html(title)}</h1>
      <div class="hero-divider"></div>
      <p class="sub">{_escape_html(subtitle)}</p>
      <div class="hero-stats">{''.join(hero_chips)}</div>
    </div>
  </section>
  <div class="wrap">
    {''.join(sections)}
    <footer>
      Week-by-week lab report | Seasons {', '.join(_escape_html(value) for value in seasons)} | Generated {_escape_html(str(report.get('generated_at')))}
    </footer>
  </div>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render weekly report HTML from weekly-report.v1 JSON."
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        required=True,
        help="Input report JSON path.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output HTML path. Defaults to same name as --in with .html extension.",
    )
    parser.add_argument(
        "--style",
        default="classic",
        choices=["classic", "cinematic"],
        help="Visual style preset for report page.",
    )
    args = parser.parse_args()

    in_path = Path(args.in_path)
    report = json.loads(in_path.read_text(encoding="utf-8"))
    out_path = Path(args.out) if args.out else default_report_html_path(in_path)
    render_report_html(report, out_path=out_path, in_path=in_path, style=args.style)
    print(f"Wrote {out_path}")
    print(f"Schema: {report.get('schema_version')}")
    print(f"Style: {args.style}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
