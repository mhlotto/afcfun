#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _slug(text: str) -> str:
    out: list[str] = []
    prev_dash = False
    for ch in text.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
            continue
        if not prev_dash:
            out.append("-")
            prev_dash = True
    value = "".join(out).strip("-")
    return value or "value"


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


_CITATION_RE = re.compile(r"\s*:contentReference\[[^\]]+\]\{[^}]+\}")
_OAICITE_RE = re.compile(r"\s*\[oaicite:[^\]]+\]")
_SPACE_RE = re.compile(r"\s+")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = _CITATION_RE.sub("", text)
    text = _OAICITE_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def _markdown_to_html(text: str) -> str:
    lines = text.splitlines()
    parts: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_code = False
    code_lines: list[str] = []

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

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            parts.append("<pre><code>" + _escape_html("\n".join(code_lines)) + "</code></pre>")
            code_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            flush_list()
            level = min(6, len(stripped) - len(stripped.lstrip("#")))
            content = stripped[level:].strip()
            parts.append(f"<h{level}>{_escape_html(content)}</h{level}>")
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            list_items.append(f"<li>{_escape_html(stripped[2:].strip())}</li>")
            continue
        lowered = stripped.lower()
        if lowered.startswith("- callout:") or lowered.startswith("– callout:"):
            flush_paragraph()
            flush_list()
            callout_text = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped
            parts.append(f"<blockquote>{_escape_html(callout_text)}</blockquote>")
            continue
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    if in_code:
        flush_code()
    return "".join(parts) if parts else "<p class='muted'>No draft text.</p>"


def _split_numbered_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^(\d+)\)\s+(.+)$", line.strip())
        if match:
            if current_title is not None:
                sections.append((current_title, current_lines))
            current_title = match.group(2).strip()
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(line)
    if current_title is not None:
        sections.append((current_title, current_lines))
    return [(title, "\n".join(lines).strip()) for title, lines in sections]


def _parse_blog_post(text: str) -> dict[str, Any]:
    sections = _split_numbered_sections(text)
    if not sections:
        label_map = {
            "headline": "Headline",
            "subheading": "Subheading",
            "body": "Body",
            "what to watch": "What to watch",
            "what to look for next week": "What to look for next week",
            "data appendix": "Data appendix",
        }
        current_title: str | None = None
        current_lines: list[str] = []
        labeled_sections: list[tuple[str, str]] = []
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            lowered = stripped.lower()
            if lowered in label_map:
                if current_title is not None:
                    labeled_sections.append((current_title, "\n".join(current_lines).strip()))
                current_title = label_map[lowered]
                current_lines = []
                continue
            if current_title is not None:
                current_lines.append(raw_line.rstrip())
        if current_title is not None:
            labeled_sections.append((current_title, "\n".join(current_lines).strip()))
        if labeled_sections:
            sections = labeled_sections

    if not sections:
        lines = [line.strip() for line in text.splitlines()]
        title = ""
        body_start = 0
        while body_start < len(lines) and not lines[body_start]:
            body_start += 1
        if body_start < len(lines):
            first = lines[body_start]
            if first.startswith("# "):
                title = first[2:].strip()
                body_start += 1
            elif first and not first.startswith(("-", "*", "##", "###")):
                title = first
                body_start += 1
        while body_start < len(lines) and not lines[body_start]:
            body_start += 1
        thesis = ""
        if body_start < len(lines) and lines[body_start] and not lines[body_start].startswith(("#", "-", "*")):
            thesis = lines[body_start]
            body_start += 1
        remainder = "\n".join(line for line in lines[body_start:]).strip()
        appendix_match = re.search(r"(?im)^data appendix\s*$", remainder)
        appendix_html = ""
        if appendix_match:
            appendix_text = remainder[appendix_match.end():].strip()
            remainder = remainder[:appendix_match.start()].strip()
            appendix_html = _markdown_to_html(appendix_text)
        return {
            "title": title,
            "thesis": thesis,
            "body_html": _markdown_to_html(remainder or text),
            "appendix_html": appendix_html,
        }

    title = ""
    thesis = ""
    body_parts: list[str] = []
    appendix_html = ""
    for section_title, body in sections:
        key = section_title.strip().lower()
        if key in {"title", "headline"}:
            title = " ".join(body.split())
            continue
        if key in {"one-paragraph thesis", "subheading"}:
            thesis = " ".join(body.split())
            continue
        if key == "body":
            body_parts.append(_markdown_to_html(body))
            continue
        if key == "what to watch":
            section_title = "What to look for next week"
        rendered = _markdown_to_html(body)
        if key == "data appendix":
            appendix_html = rendered
            continue
        body_parts.append(f"<section class='article-section'><h2>{_escape_html(section_title)}</h2>{rendered}</section>")
    return {
        "title": title,
        "thesis": thesis,
        "body_html": "".join(body_parts),
        "appendix_html": appendix_html,
    }


def _relpath(target: Path, start: Path) -> str:
    return Path(os.path.relpath(str(target), str(start))).as_posix()


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected JSON object")
    return loaded


def _find_selection_files(reports_dir: Path, team: str, season: str) -> list[Path]:
    pattern = f"editorial-selection-{_slug(team)}-{season.replace('-', '')}-w*.json"
    paths = sorted(reports_dir.glob(pattern), key=_week_from_path)
    if not paths:
        raise FileNotFoundError(f"No editorial selection files matched {pattern}")
    return paths


def _week_from_path(path: Path) -> int:
    match = re.search(r"-w(\d+)-", path.name)
    if not match:
        return 0
    return int(match.group(1))


def _story_index(ideation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    story_candidates = ideation.get("story_candidates")
    if not isinstance(story_candidates, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in story_candidates:
        if not isinstance(item, dict):
            continue
        story_id = _clean_text(item.get("id"))
        if story_id:
            out[story_id] = item
    return out


def _pick_artifact_links(
    reports_dir: Path,
    *,
    team: str,
    season: str,
    week: int,
) -> dict[str, Path]:
    slug = _slug(team)
    compact_season = season.replace("-", "")
    links: dict[str, Path] = {}
    for suffix in ("html", "json"):
        pattern = f"weekly-report-{slug}-{compact_season}-through-w{week}-*.{suffix}"
        matches = sorted(reports_dir.glob(pattern))
        if len(matches) == 1:
            links[f"report_{suffix}"] = matches[0]
    return links


def _pick_optional_content(
    reports_dir: Path,
    *,
    team: str,
    season: str,
    week: int,
) -> dict[str, Path]:
    slug = _slug(team)
    compact_season = season.replace("-", "")
    candidates = {
        "blog_markdown": [
            f"weekly-post-{slug}-{compact_season}-w{week}.md",
            f"weekly-blog-{slug}-{compact_season}-w{week}.md",
            f"blog-draft-{slug}-{compact_season}-w{week}.md",
        ],
        "chart_plan_resolved_json": [
            f"weekly-chart-plan-resolved-w{week}.json",
        ],
        "publication_notes_json": [
            f"publication-notes-{slug}-{compact_season}-w{week}.json",
        ],
        "publication_notes_md": [
            f"publication-notes-{slug}-{compact_season}-w{week}.md",
        ],
    }
    out: dict[str, Path] = {}
    for key, names in candidates.items():
        for name in names:
            path = reports_dir / name
            if path.exists():
                out[key] = path
                break
    return out


@dataclass
class WeekBundle:
    selection_path: Path
    selection: dict[str, Any]
    context_path: Path
    context: dict[str, Any]
    ideation_path: Path
    ideation: dict[str, Any]
    selected_story: dict[str, Any]
    secondary_stories: list[dict[str, Any]]
    visual_selection_path: Path | None
    visual_selection: dict[str, Any] | None
    report_artifacts: dict[str, Path]
    optional_artifacts: dict[str, Path]

    @property
    def team(self) -> str:
        return _clean_text(self.selection.get("team"))

    @property
    def season(self) -> str:
        return _clean_text(self.selection.get("season"))

    @property
    def week(self) -> int:
        return int(self.selection.get("week", 0))


def load_week_bundles(reports_dir: Path, *, team: str, season: str) -> list[WeekBundle]:
    bundles_by_week: dict[int, WeekBundle] = {}
    for selection_path in _find_selection_files(reports_dir, team, season):
        selection = _load_json(selection_path)
        context_path = Path(str(selection.get("weekly_context_file", "")))
        ideation_path = Path(str(selection.get("ideation_file", "")))
        if not context_path.is_absolute():
            context_path = Path.cwd() / context_path
        if not ideation_path.is_absolute():
            ideation_path = Path.cwd() / ideation_path
        context = _load_json(context_path)
        ideation = _load_json(ideation_path)
        story_index = _story_index(ideation)
        selected_story_id = _clean_text(selection.get("selected_story_id"))
        if selected_story_id not in story_index:
            raise ValueError(f"{selection_path}: selected_story_id {selected_story_id!r} not found")
        secondary_stories = [
            story_index[story_id]
            for story_id in selection.get("secondary_story_ids", [])
            if story_id in story_index
        ]
        visual_matches = sorted(
            reports_dir.glob(
                f"visual-selection-{_slug(team)}-{season.replace('-', '')}-w{int(selection.get('week', 0))}-*.json"
            )
        )
        visual_selection_path = visual_matches[0].resolve() if len(visual_matches) == 1 else None
        visual_selection = _load_json(visual_selection_path) if visual_selection_path is not None else None
        bundle = WeekBundle(
            selection_path=selection_path.resolve(),
            selection=selection,
            context_path=context_path.resolve(),
            context=context,
            ideation_path=ideation_path.resolve(),
            ideation=ideation,
            selected_story=story_index[selected_story_id],
            secondary_stories=secondary_stories,
            visual_selection_path=visual_selection_path,
            visual_selection=visual_selection,
            report_artifacts=_pick_artifact_links(
                reports_dir.resolve(),
                team=team,
                season=season,
                week=int(selection.get("week", 0)),
            ),
            optional_artifacts=_pick_optional_content(
                reports_dir.resolve(),
                team=team,
                season=season,
                week=int(selection.get("week", 0)),
            ),
        )
        bundles_by_week[bundle.week] = bundle
    return [bundles_by_week[week] for week in sorted(bundles_by_week)]


def _metric_chip(metric: dict[str, Any]) -> str:
    name = _escape_html(_clean_text(metric.get("metric")))
    delta = metric.get("delta")
    raw_direction = _clean_text(metric.get("direction_for_team")).lower()
    direction_labels = {
        "beneficial": "Beneficial",
        "harmful": "Harmful",
        "mixed": "Mixed impact",
        "unknown": "Unclear impact",
    }
    direction = _escape_html(direction_labels.get(raw_direction, raw_direction.title()))
    chip_class = f"chip chip-{raw_direction}" if raw_direction else "chip"
    if isinstance(delta, (int, float)):
        delta_text = f"{delta:+.2f}"
    else:
        delta_text = _escape_html(_clean_text(delta))
    return (
        f"<span class='{chip_class}'>"
        f"<strong>{name}</strong> {delta_text}"
        + (f" <em>{direction}</em>" if direction else "")
        + "</span>"
    )


def _story_list_items(stories: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for story in stories:
        parts.append(
            "<article class='story-card secondary'>"
            f"<h4>{_escape_html(_clean_text(story.get('id')))} - "
            f"{_escape_html(_clean_text(story.get('title')))}</h4>"
            f"<p>{_escape_html(_clean_text(story.get('angle')))}</p>"
            f"<p class='mini'><strong>Signal:</strong> "
            f"{_escape_html(_clean_text(story.get('signal_strength')))}</p>"
            "</article>"
        )
    return "".join(parts)


def _recommended_story(bundle: WeekBundle) -> dict[str, Any] | None:
    recommended = bundle.ideation.get("recommended_story")
    if not isinstance(recommended, dict):
        return None
    story_id = _clean_text(recommended.get("story_id"))
    if not story_id:
        return None
    return _story_index(bundle.ideation).get(story_id)


def _why_now_paragraph(ideation: dict[str, Any]) -> str:
    executive = ideation.get("executive_summary")
    state = ideation.get("state_snapshot")
    parts: list[str] = []
    if isinstance(executive, dict):
        why_now = _clean_text(executive.get("why_now"))
        if why_now:
            parts.append(why_now)
    if isinstance(state, dict):
        peer = _clean_text(state.get("peer_context_takeaway"))
        tension = _clean_text(state.get("season_vs_week_tension"))
        for extra in (peer, tension):
            if extra and extra not in parts:
                parts.append(extra)
    return " ".join(parts[:3]).strip()


def _links_html(bundle: WeekBundle, page_dir: Path) -> str:
    links: list[tuple[str, Path]] = [
        ("Editorial selection", bundle.selection_path),
        ("Weekly context JSON", bundle.context_path),
        ("Ideation JSON", bundle.ideation_path),
    ]
    if bundle.visual_selection_path is not None:
        links.append(("Visual selection", bundle.visual_selection_path))
    for key, label in (("report_html", "Weekly report HTML"), ("report_json", "Weekly report JSON")):
        if key in bundle.report_artifacts:
            links.append((label, bundle.report_artifacts[key]))
    for key, label in (
        ("blog_markdown", "Blog markdown"),
        ("chart_plan_resolved_json", "Chart plan resolved JSON"),
        ("publication_notes_json", "Publication notes JSON"),
        ("publication_notes_md", "Publication notes"),
    ):
        if key in bundle.optional_artifacts:
            links.append((label, bundle.optional_artifacts[key]))
    rendered = [
        f"<a href='{_escape_html(_relpath(path, page_dir))}'>{_escape_html(label)}</a>"
        for label, path in links
    ]
    return " | ".join(rendered)


def _render_optional_content(bundle: WeekBundle, page_dir: Path) -> str:
    sections: list[str] = []
    blog_path = bundle.optional_artifacts.get("blog_markdown")
    if blog_path is not None:
        parsed_blog = _parse_blog_post(blog_path.read_text(encoding="utf-8"))
        blog_html = parsed_blog["body_html"] or _markdown_to_html(blog_path.read_text(encoding="utf-8"))
        next_fixture = bundle.context.get("next_fixture", {}) if isinstance(bundle.context.get("next_fixture"), dict) else {}
        if next_fixture:
            opponent = _clean_text(next_fixture.get("opponent"))
            venue = _clean_text(next_fixture.get("venue"))
            kickoff = _clean_text(next_fixture.get("kickoff_utc"))
            if opponent:
                escaped_opp = _escape_html(opponent)
                if opponent not in blog_html and escaped_opp not in blog_html:
                    marker = "<h2>What to look for next week</h2><ul>"
                    if marker in blog_html:
                        opponent_last_week = bundle.context.get("next_opponent_last_week", {})
                        line_parts = [f"Next up: {opponent}"]
                        if venue:
                            line_parts.append(f"({venue})")
                        if kickoff:
                            line_parts.append(f"- {kickoff}")
                        watchline = "<li>" + _escape_html(" ".join(line_parts)) + "</li>"
                        if isinstance(opponent_last_week, dict):
                            op_result = _clean_text(opponent_last_week.get("result"))
                            op_score = _clean_text(opponent_last_week.get("score"))
                            op_opp = _clean_text(opponent_last_week.get("opponent"))
                            op_week = int(opponent_last_week.get("week", 0) or 0)
                            if op_result and op_score and op_opp:
                                watchline += (
                                    "<li>"
                                    + _escape_html(
                                        f"{opponent} last week (W{op_week}): {op_result} {op_score} vs {op_opp}."
                                    )
                                    + "</li>"
                                )
                        matchup = bundle.context.get("next_week_matchup_lens", {})
                        if isinstance(matchup, dict):
                            beneficial = matchup.get("top_beneficial", [])
                            harmful = matchup.get("top_harmful", [])
                            if isinstance(beneficial, list) and beneficial:
                                top = beneficial[0]
                                label = _clean_text(top.get("label")) or _clean_text(top.get("metric"))
                                delta = top.get("delta")
                                if isinstance(delta, (int, float)) and label:
                                    watchline += (
                                        "<li>"
                                        + _escape_html(
                                            f"Matchup edge: Arsenal are {delta:+.2f} better on {label} in recent form."
                                        )
                                        + "</li>"
                                    )
                            if isinstance(harmful, list) and harmful:
                                top = harmful[0]
                                label = _clean_text(top.get("label")) or _clean_text(top.get("metric"))
                                delta = top.get("delta")
                                if isinstance(delta, (int, float)) and label:
                                    watchline += (
                                        "<li>"
                                        + _escape_html(
                                            f"Matchup risk: Arsenal are {delta:+.2f} worse on {label} in recent form."
                                        )
                                        + "</li>"
                                    )
                        blog_html = blog_html.replace(marker, marker + watchline, 1)
        sections.append(
            "<section class='card'>"
            f"{blog_html}"
            "</section>"
        )

    notes_json_path = bundle.optional_artifacts.get("publication_notes_json")
    if notes_json_path is not None:
        notes_json = _load_json(notes_json_path)
        pretty = _escape_html(json.dumps(notes_json, indent=2))
        sections.append(
            "<section class='card'>"
            "<h2>Publication notes</h2>"
            f"<pre><code>{pretty}</code></pre>"
            f"<p class='mini'><a href='{_escape_html(_relpath(notes_json_path, page_dir))}'>Open source notes JSON</a></p>"
            "</section>"
        )

    notes_md_path = bundle.optional_artifacts.get("publication_notes_md")
    if notes_md_path is not None:
        sections.append(
            "<section class='card'>"
            "<h2>Publication notes</h2>"
            f"{_markdown_to_html(notes_md_path.read_text(encoding='utf-8'))}"
            f"<p class='mini'><a href='{_escape_html(_relpath(notes_md_path, page_dir))}'>Open source notes</a></p>"
            "</section>"
        )
    return "".join(sections)


def _render_week_sources_page(
    bundle: WeekBundle,
    *,
    out_path: Path,
    week_page_path: Path,
    season_index_path: Path,
    site_index_path: Path,
) -> str:
    context = bundle.context
    executive = bundle.ideation.get("executive_summary", {})
    state = bundle.ideation.get("state_snapshot", {})
    quality = context.get("context_quality", {}) if isinstance(context.get("context_quality"), dict) else {}
    recommended_story = _recommended_story(bundle) or {}
    parsed_blog = None
    blog_path = bundle.optional_artifacts.get("blog_markdown")
    if blog_path is not None:
        parsed_blog = _parse_blog_post(blog_path.read_text(encoding="utf-8"))
    selected = bundle.selected_story
    charts = selected.get("charts") if isinstance(selected.get("charts"), list) else []
    chart_items = []
    for chart in charts[:4]:
        if not isinstance(chart, dict):
            continue
        fields = chart.get("metric_or_fields")
        field_text = ", ".join(_clean_text(item) for item in fields) if isinstance(fields, list) else ""
        chart_items.append(
            "<li>"
            f"<strong>{_escape_html(_clean_text(chart.get('type')))}</strong>"
            + (f" ({_escape_html(field_text)})" if field_text else "")
            + f": {_escape_html(_clean_text(chart.get('why')))}"
            "</li>"
        )
    page_dir = out_path.parent
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape_html(bundle.team)} {bundle.season} Week {bundle.week} sources</title>
  <style>
    :root {{
      --bg: #0b0f14;
      --panel: #111827;
      --ink: #f3f4f6;
      --muted: #9ca3af;
      --line: rgba(255,255,255,0.08);
      --accent: #cf102d;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; color: var(--ink); background:
      radial-gradient(circle at top left, rgba(207,16,45,0.06), transparent 38%),
      linear-gradient(180deg, #0b0f14, #111827); }}
    a {{ color: var(--accent); }}
    .shell {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 20px; padding: 20px 22px; margin-bottom: 18px; box-shadow: 0 22px 60px rgba(0,0,0,0.45); }}
    h1,h2,h3 {{ margin: 0 0 12px; font-family: "Arial Narrow", "Trebuchet MS", sans-serif; }}
    .mini,.muted {{ color: var(--muted); }}
    pre {{ white-space: pre-wrap; word-break: break-word; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <div class="shell">
    <p class="mini">
      <a href="{_escape_html(_relpath(site_index_path, page_dir))}">Site</a> /
      <a href="{_escape_html(_relpath(season_index_path, page_dir))}">{_escape_html(bundle.team)} {bundle.season}</a> /
      <a href="{_escape_html(_relpath(week_page_path, page_dir))}">Week {bundle.week}</a> /
      Sources
    </p>
    <section class="card">
      <h1>Week {bundle.week} backing page</h1>
      <p class="muted">Process details, caveats, sources, and artifact links for the main week page.</p>
    </section>
    <section class="card">
      <h2>Confidence and caveats</h2>
      <p><strong>Confidence:</strong> {_escape_html(_clean_text(executive.get("confidence") or quality.get("overall_confidence") or "n/a"))}</p>
      <p><strong>Confidence rationale:</strong> {_escape_html(_clean_text(executive.get("confidence_rationale")))}</p>
      <p><strong>Peer context:</strong> {_escape_html(_clean_text(state.get("peer_context_takeaway")))}</p>
      <p><strong>Season tension:</strong> {_escape_html(_clean_text(state.get("season_vs_week_tension")))}</p>
    </section>
    <section class="card">
      <h2>Context quality</h2>
      <p><strong>Peer teams:</strong> {int(quality.get("peer_team_count", 0))}</p>
      <p><strong>Trend window:</strong> {int(quality.get("trend_window_size", 0))}</p>
      <p><strong>Flat-signal metrics:</strong> {_escape_html(", ".join(_clean_text(item) for item in quality.get("flat_signal_metrics", [])) or "None")}</p>
      <p><strong>Notes:</strong> {_escape_html(" | ".join(_clean_text(item) for item in quality.get("notes", [])) or "None")}</p>
    </section>
    <section class="card">
      <h2>Selection metadata</h2>
      <p><strong>Primary story:</strong> {_escape_html(_clean_text(bundle.selection.get("selected_story_title")))}</p>
      <p><strong>Recommended story:</strong> {_escape_html(_clean_text(recommended_story.get("title")) or _clean_text(bundle.selection.get("recommended_story_id")) or "None")}</p>
      <p><strong>Selection matches recommendation:</strong> {_escape_html(str(bool(bundle.selection.get("recommended_matches_selection"))).lower())}</p>
      <p><strong>Selection reason:</strong> {_escape_html(_clean_text(bundle.selection.get("selection_reason"))) or "None"}</p>
      <p><strong>Selection mode:</strong> {_escape_html(_clean_text(bundle.selection.get("selection_mode"))) or "n/a"}</p>
      <p><strong>Story caveats:</strong> {_escape_html(" | ".join(_clean_text(item) for item in bundle.selected_story.get("risks_or_caveats", [])) or "None")}</p>
      <p><strong>Angle:</strong> {_escape_html(_clean_text(bundle.selected_story.get("angle")) or "None")}</p>
      <p><strong>Audience value:</strong> {_escape_html(_clean_text(bundle.selected_story.get("audience_value")) or "None")}</p>
      <p><strong>Peer signal:</strong> {_escape_html(_clean_text(bundle.selected_story.get("peer_signal")) or "None")}</p>
      <p><strong>Season-to-date signal:</strong> {_escape_html(_clean_text(bundle.selected_story.get("season_to_date_signal")) or "None")}</p>
    </section>
    <section class="card">
      <h2>Visual selection</h2>
      <p><strong>Primary visual:</strong> {_escape_html(_clean_text((bundle.visual_selection or {}).get("selected_visual_title")) or "None")}</p>
      <p><strong>Selection reason:</strong> {_escape_html(_clean_text((bundle.visual_selection or {}).get("selection_reason")) or "None")}</p>
      <p><strong>Selection mode:</strong> {_escape_html(_clean_text((bundle.visual_selection or {}).get("selection_mode")) or "n/a")}</p>
      <p><strong>Suggested visuals:</strong></p>
      <ul>{"".join(chart_items) or "<li class='muted'>No suggested visuals.</li>"}</ul>
    </section>
    {(
        "<section class='card'><h2>Data appendix</h2>"
        + parsed_blog["appendix_html"]
        + "</section>"
    ) if parsed_blog and parsed_blog.get("appendix_html") else ""}
    <section class="card">
      <h2>Artifact links</h2>
      <p>{_links_html(bundle, page_dir)}</p>
    </section>
  </div>
</body>
</html>
"""


def _render_week_page(bundle: WeekBundle, *, out_path: Path, sources_path: Path, season_index_path: Path, site_index_path: Path) -> str:
    context = bundle.context
    match = context.get("match", {}) if isinstance(context.get("match"), dict) else {}
    next_fixture = context.get("next_fixture", {}) if isinstance(context.get("next_fixture"), dict) else {}
    form = context.get("form_snapshot", {}) if isinstance(context.get("form_snapshot"), dict) else {}
    executive = bundle.ideation.get("executive_summary", {})
    why_now_text = _why_now_paragraph(bundle.ideation)
    page_dir = out_path.parent
    upward = context.get("largest_upward_deltas") or []
    downward = context.get("largest_downward_deltas") or []
    week_flags = context.get("week_flags") or []
    selected = bundle.selected_story
    parsed_blog = None
    blog_path = bundle.optional_artifacts.get("blog_markdown")
    if blog_path is not None:
        parsed_blog = _parse_blog_post(blog_path.read_text(encoding="utf-8"))
    flags_html = "".join(
        f"<li>{_escape_html(_clean_text(flag))}</li>" for flag in week_flags[:6]
    ) or "<li class='muted'>No week flags.</li>"
    visual = bundle.visual_selection or {}
    visual_path = _clean_text(visual.get("selected_visual_path"))
    visual_block = ""
    if visual_path:
        visual_file = Path(visual_path)
        if not visual_file.is_absolute():
            visual_file = (bundle.context_path.parent / visual_file).resolve()
        visual_href = _escape_html(_relpath(visual_file, page_dir))
        visual_title = _escape_html(_clean_text(visual.get("selected_visual_title")) or "Primary visual")
        visual_block = (
            "<section class='card'>"
            f"<h2>{visual_title}</h2>"
            f"<iframe title='{visual_title}' src='{visual_href}' loading='lazy' "
            "referrerpolicy='no-referrer' style='width:100%;min-height:460px;border:0;border-radius:14px;background:#0b1118;'></iframe>"
            "</section>"
        )

    next_fixture_block = ""
    if next_fixture:
        opponent = _escape_html(_clean_text(next_fixture.get("opponent")))
        venue = _escape_html(_clean_text(next_fixture.get("venue")))
        kickoff = _escape_html(_clean_text(next_fixture.get("kickoff_utc")))
        stadium = _escape_html(_clean_text(next_fixture.get("stadium")))
        matchday = int(next_fixture.get("matchday", 0) or 0)
        opponent_recent = context.get("next_opponent_recent_form", {})
        opponent_recent_line = ""
        if isinstance(opponent_recent, dict):
            wdl = opponent_recent.get("wdl", {})
            if isinstance(wdl, dict):
                def _fmt(value: Any) -> str:
                    try:
                        return f"{float(value):.2f}"
                    except (TypeError, ValueError):
                        return _clean_text(value)
                recent_window = int(opponent_recent.get("window", 0) or 0)
                recent_pts = _fmt(opponent_recent.get("points_per_match"))
                recent_gf = _fmt(opponent_recent.get("goals_for_per_match"))
                recent_ga = _fmt(opponent_recent.get("goals_against_per_match"))
                opponent_recent_line = (
                    f"<div class='mini'>Opponent last {recent_window}: "
                    f"{int(wdl.get('w', 0))}W-{int(wdl.get('d', 0))}D-{int(wdl.get('l', 0))}L, "
                    f"{recent_pts} pts/m, GF {recent_gf}, GA {recent_ga}</div>"
                )
        next_fixture_block = (
            "<div class='card alt'>"
            "<span class='label'>Next fixture</span>"
            f"<div class='value'>vs {opponent}</div>"
            f"<div class='mini'>{venue} | Matchday {matchday}</div>"
            + (f"<div class='mini'>{kickoff}</div>" if kickoff else "")
            + (f"<div class='mini'>{stadium}</div>" if stadium else "")
            + opponent_recent_line
            + "</div>"
        )

    has_key_signals = bool(upward or downward or week_flags)
    key_signals_block = (
        "<section class='card'>"
        "<h2>Key signals</h2>"
        + (
            "<h3>Biggest rises vs season average</h3>"
            + "<div class='chip-row'>"
            + "".join(_metric_chip(item) for item in upward[:5])
            + "</div>"
            if upward
            else ""
        )
        + (
            "<h3 style='margin-top:16px;'>Biggest drops vs season average</h3>"
            + "<div class='chip-row'>"
            + "".join(_metric_chip(item) for item in downward[:5])
            + "</div>"
            if downward
            else ""
        )
        + (
            "<h3 style='margin-top:16px;'>What stood out</h3><ul>"
            + "".join(f"<li>{_escape_html(_clean_text(flag))}</li>" for flag in week_flags[:6])
            + "</ul>"
            if week_flags
            else ""
        )
        + "</section>"
    ) if has_key_signals else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape_html(bundle.team)} {bundle.season} Week {bundle.week}</title>
  <style>
    :root {{
      --bg: #0b0f14;
      --panel: #111827;
      --panel-alt: #0b1118;
      --ink: #f3f4f6;
      --muted: #9ca3af;
      --line: rgba(255,255,255,0.08);
      --accent: #cf102d;
      --accent-soft: rgba(207,16,45,0.14);
      --good: #d4af37;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; color: var(--ink); background:
      radial-gradient(circle at top left, rgba(207,16,45,0.06), transparent 38%),
      linear-gradient(180deg, #0b0f14 0%, #111827 100%); }}
    a {{ color: var(--accent); }}
    .shell {{ max-width: 1080px; margin: 0 auto; padding: 28px 20px 60px; }}
    .breadcrumbs {{ font-size: 0.95rem; color: var(--muted); margin-bottom: 16px; }}
    .hero {{ background: var(--panel); border: 1px solid rgba(207,16,45,0.18); border-radius: 24px; padding: 26px 28px; box-shadow: 0 22px 60px rgba(0,0,0,0.45); }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; color: var(--accent); margin: 0 0 8px; }}
    h1,h2,h3,h4 {{ margin: 0 0 12px; font-family: "Arial Narrow", "Trebuchet MS", sans-serif; }}
    h1 {{ font-size: clamp(2rem, 5vw, 3.4rem); line-height: 1.05; color: var(--accent); }}
    .subhead {{ font-size: 1.1rem; color: var(--muted); max-width: 52rem; }}
    .meta-grid {{ display: grid; gap: 16px; margin-top: 22px; }}
    .meta-grid {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .detail-stack {{ display: flex; flex-direction: column; gap: 20px; margin-top: 28px; }}
    .article-card {{ max-width: 860px; width: 100%; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px 20px; box-shadow: 0 22px 60px rgba(0,0,0,0.35); }}
    .card.alt {{ background: var(--panel-alt); }}
    .label {{ display: block; font-size: 0.76rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }}
    .value {{ font-size: 1.3rem; font-weight: 700; }}
    .story-card {{ border: 1px solid var(--line); border-radius: 18px; padding: 18px 20px; background: linear-gradient(180deg, #111827, #0b1118); }}
    .story-card.secondary {{ background: var(--panel); }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .chip {{ display: inline-flex; gap: 8px; align-items: baseline; padding: 8px 12px; border-radius: 999px; border: 1px solid var(--line); background: rgba(255,255,255,0.04); }}
    .chip em {{ color: var(--muted); font-style: normal; }}
    .chip-beneficial {{ border-color: rgba(212,175,55,0.30); background: rgba(212,175,55,0.08); }}
    .chip-beneficial em {{ color: #d4af37; }}
    .chip-harmful {{ border-color: rgba(207,16,45,0.28); background: rgba(207,16,45,0.08); }}
    .chip-harmful em {{ color: #ff8c99; }}
    .chip-mixed {{ border-color: rgba(156,163,175,0.22); }}
    .chip-unknown {{ border-color: rgba(156,163,175,0.22); }}
    ul {{ margin: 0; padding-left: 20px; }}
    .muted {{ color: var(--muted); }}
    .mini {{ font-size: 0.92rem; color: var(--muted); }}
    .artifact-links {{ margin-top: 20px; font-size: 0.95rem; }}
    .footer {{ margin-top: 28px; color: var(--muted); font-size: 0.92rem; }}
    .article-section + .article-section {{ margin-top: 24px; }}
    .article-section h2 {{ color: var(--accent); }}
    @media (max-width: 860px) {{ .article-card {{ max-width: 100%; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="breadcrumbs">
      <a href="{_escape_html(_relpath(site_index_path, page_dir))}">Site</a> /
      <a href="{_escape_html(_relpath(season_index_path, page_dir))}">{_escape_html(bundle.team)} {bundle.season}</a> /
      Week {bundle.week}
    </div>
    <section class="hero">
      <p class="eyebrow">{_escape_html(bundle.team)} / {bundle.season} / Week {bundle.week}</p>
      <h1>{_escape_html(_clean_text((parsed_blog or {}).get("title")) or _clean_text(selected.get("title")))}</h1>
      <p class="subhead">{_escape_html(_clean_text((parsed_blog or {}).get("thesis")) or _clean_text(bundle.ideation.get("recommended_story", {}).get("draft_subheading") or executive.get("headline")))}</p>
      <div class="meta-grid">
        <div class="card alt"><span class="label">Match</span><div class="value">{_escape_html(_clean_text(match.get("score")))} { _escape_html(_clean_text(match.get("result"))) }</div><div class="mini">vs {_escape_html(_clean_text(match.get("opponent")))} ({_escape_html(_clean_text(match.get("venue")))})</div></div>
        <div class="card alt"><span class="label">Recent form</span><div class="value">{int(form.get("points", 0))} pts / {float(form.get("halfwin_average", 0.0)):.2f}</div><div class="mini">Last {int(form.get("window", 0) or 0)}: {int((form.get("wdl") or {}).get("w", 0))}W-{int((form.get("wdl") or {}).get("d", 0))}D-{int((form.get("wdl") or {}).get("l", 0))}L</div></div>
        {next_fixture_block}
        <div class="card alt"><span class="label">More detail</span><div class="value"><a href="{_escape_html(_relpath(sources_path, page_dir))}">Sources &amp; caveats</a></div><div class="mini">Method, artifact links, and process details live here.</div></div>
      </div>
    </section>

    <div class="detail-stack">
      <section class="card">
        <h2>Why this week matters</h2>
        <p>{_escape_html(why_now_text)}</p>
        <p><strong>Practical takeaway:</strong> {_escape_html(_clean_text(executive.get("headline")))}</p>
      </section>

      {key_signals_block}

      {visual_block}

      {(
        "<section class='card'><h2>Alternate stories</h2>"
        + _story_list_items(bundle.secondary_stories)
        + "</section>"
      ) if bundle.secondary_stories else ""}

      {_render_optional_content(bundle, page_dir).replace("<section class='card'>", "<section class='card article-card'>", 1)}
    </div>
  </div>
</body>
</html>
"""


def _render_team_index(team: str, season: str, bundles: list[WeekBundle], *, out_path: Path, site_index_path: Path) -> str:
    page_dir = out_path.parent
    cards: list[str] = []
    for bundle in sorted(bundles, key=lambda item: item.week, reverse=True):
        match = bundle.context.get("match", {}) if isinstance(bundle.context.get("match"), dict) else {}
        executive = bundle.ideation.get("executive_summary", {})
        cards.append(
            f"<article class='week-card' data-week='{bundle.week}'>"
            f"<p class='mini'>Week {bundle.week}</p>"
            f"<h3><a href='week-{bundle.week}.html'>{_escape_html(_clean_text(bundle.selected_story.get('title')))}</a></h3>"
            f"<p><strong>{_escape_html(_clean_text(match.get('score')))} "
            f"{_escape_html(_clean_text(match.get('result')))}</strong> vs "
            f"{_escape_html(_clean_text(match.get('opponent')))} "
            f"({_escape_html(_clean_text(match.get('venue')))})</p>"
            f"<p class='muted'>{_escape_html(_clean_text(executive.get('headline')))}</p>"
            "</article>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape_html(team)} {season}</title>
  <style>
    :root {{
      --bg: #0b0f14;
      --panel: #111827;
      --ink: #f3f4f6;
      --muted: #9ca3af;
      --line: rgba(255,255,255,0.08);
      --accent: #cf102d;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; color: var(--ink); background:
      radial-gradient(circle at top left, rgba(207,16,45,0.06), transparent 38%),
      linear-gradient(180deg, #0b0f14, #111827); }}
    a {{ color: var(--accent); }}
    .shell {{ max-width: 1080px; margin: 0 auto; padding: 28px 20px 60px; }}
    .hero, .week-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 22px; box-shadow: 0 22px 60px rgba(0,0,0,0.35); }}
    .hero {{ padding: 26px 28px; margin-bottom: 26px; }}
    .cards {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
    .week-card {{ padding: 18px 18px; }}
    .order-btn {{ border: 1px solid var(--line); background: rgba(255,255,255,0.04); color: var(--ink); border-radius: 999px; padding: 8px 12px; cursor: pointer; }}
    .order-btn:hover {{ border-color: rgba(207,16,45,0.45); }}
    h1,h2,h3 {{ margin: 0 0 12px; font-family: "Arial Narrow", "Trebuchet MS", sans-serif; }}
    .muted, .mini {{ color: var(--muted); }}
    .mini {{ font-size: 0.92rem; }}
  </style>
</head>
<body>
  <div class="shell">
    <p class="mini"><a href="{_escape_html(_relpath(site_index_path, page_dir))}">Site</a> / {_escape_html(team)} / {_escape_html(season)}</p>
    <section class="hero">
      <h1>{_escape_html(team)} { _escape_html(season) }</h1>
      <p class="muted">Minimal static season portal generated from weekly context, ideation, and editorial-selection artifacts.</p>
      <p><strong>Weeks:</strong> {len(bundles)}</p>
      <p><button id="order-btn" class="order-btn" type="button">Order: Newest first</button></p>
    </section>
    <section class="cards" id="weeks">
      {"".join(cards)}
    </section>
  </div>
  <script>
    (() => {{
      const container = document.getElementById("weeks");
      const button = document.getElementById("order-btn");
      if (!container || !button) return;
      let newestFirst = true;
      const render = () => {{
        const cards = Array.from(container.querySelectorAll(".week-card"));
        cards.sort((a, b) => {{
          const aWeek = Number(a.getAttribute("data-week") || 0);
          const bWeek = Number(b.getAttribute("data-week") || 0);
          return newestFirst ? (bWeek - aWeek) : (aWeek - bWeek);
        }});
        cards.forEach((card) => container.appendChild(card));
        button.textContent = newestFirst ? "Order: Newest first" : "Order: Oldest first";
      }};
      button.addEventListener("click", () => {{
        newestFirst = !newestFirst;
        render();
      }});
      render();
    }})();
  </script>
</body>
</html>
"""


def _render_site_index(entries: list[tuple[str, str, Path]]) -> str:
    cards = []
    for team, season, path in entries:
        cards.append(
            "<article class='card'>"
            f"<p class='mini'>{_escape_html(team)}</p>"
            f"<h2><a href='{_escape_html(path.as_posix())}'>{_escape_html(season)}</a></h2>"
            "<p class='muted'>Weekly portal built from selected editorial artifacts.</p>"
            "</article>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Footstat site</title>
  <style>
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; background:
      radial-gradient(circle at top left, rgba(207,16,45,0.06), transparent 38%),
      linear-gradient(180deg, #0b0f14, #111827); color: #f3f4f6; }}
    .shell {{ max-width: 960px; margin: 0 auto; padding: 32px 20px 60px; }}
    .hero, .card {{ background: #111827; border: 1px solid rgba(255,255,255,0.08); border-radius: 22px; padding: 22px; box-shadow: 0 22px 60px rgba(0,0,0,0.35); }}
    .hero {{ margin-bottom: 24px; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
    h1,h2 {{ margin: 0 0 12px; font-family: "Arial Narrow", "Trebuchet MS", sans-serif; }}
    a {{ color: #cf102d; }}
    .mini, .muted {{ color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <p class="mini">Footstat</p>
      <h1>Static weekly portal</h1>
      <p class="muted">Entry point for artifact-driven season pages.</p>
    </section>
    <section class="grid">
      {"".join(cards)}
    </section>
  </div>
</body>
</html>
"""


def build_site(*, reports_dir: Path, out_dir: Path, team: str, season: str) -> list[Path]:
    bundles = load_week_bundles(reports_dir, team=team, season=season)
    season_dir = out_dir / _slug(team) / season
    season_dir.mkdir(parents=True, exist_ok=True)
    team_index_path = season_dir / "index.html"
    site_index_path = out_dir / "index.html"

    written: list[Path] = []
    for bundle in bundles:
        week_path = season_dir / f"week-{bundle.week}.html"
        sources_path = season_dir / f"week-{bundle.week}-sources.html"
        week_path.write_text(
            _render_week_page(
                bundle,
                out_path=week_path,
                sources_path=sources_path,
                season_index_path=team_index_path,
                site_index_path=site_index_path,
            ),
            encoding="utf-8",
        )
        written.append(week_path)
        sources_path.write_text(
            _render_week_sources_page(
                bundle,
                out_path=sources_path,
                week_page_path=week_path,
                season_index_path=team_index_path,
                site_index_path=site_index_path,
            ),
            encoding="utf-8",
        )
        written.append(sources_path)

    team_index_path.write_text(
        _render_team_index(
            team,
            season,
            bundles,
            out_path=team_index_path,
            site_index_path=site_index_path,
        ),
        encoding="utf-8",
    )
    written.append(team_index_path)

    site_index_path.write_text(
        _render_site_index(
            [
                (
                    team,
                    season,
                    Path(_slug(team)) / season / "index.html",
                )
            ]
        ),
        encoding="utf-8",
    )
    written.append(site_index_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a minimal static site from weekly context, ideation, and editorial selections."
    )
    parser.add_argument("--reports-dir", default="docs/reports", help="Reports/artifacts directory.")
    parser.add_argument("--out-dir", default="docs/site", help="Site output directory.")
    parser.add_argument("--team", required=True, help="Team name, e.g. Arsenal.")
    parser.add_argument("--season", required=True, help="Season label, e.g. 2025-2026.")
    args = parser.parse_args()

    written = build_site(
        reports_dir=Path(args.reports_dir),
        out_dir=Path(args.out_dir),
        team=args.team,
        season=args.season,
    )
    for path in written:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
