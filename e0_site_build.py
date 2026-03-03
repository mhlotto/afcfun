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
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    if in_code:
        flush_code()
    return "".join(parts) if parts else "<p class='muted'>No draft text.</p>"


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
    bundles: list[WeekBundle] = []
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
        bundles.append(
            WeekBundle(
                selection_path=selection_path.resolve(),
                selection=selection,
                context_path=context_path.resolve(),
                context=context,
                ideation_path=ideation_path.resolve(),
                ideation=ideation,
                selected_story=story_index[selected_story_id],
                secondary_stories=secondary_stories,
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
        )
    return sorted(bundles, key=lambda bundle: bundle.week)


def _metric_chip(metric: dict[str, Any]) -> str:
    name = _escape_html(_clean_text(metric.get("metric")))
    delta = metric.get("delta")
    direction = _escape_html(_clean_text(metric.get("direction_for_team")))
    if isinstance(delta, (int, float)):
        delta_text = f"{delta:+.2f}"
    else:
        delta_text = _escape_html(_clean_text(delta))
    return (
        "<span class='chip'>"
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


def _links_html(bundle: WeekBundle, page_dir: Path) -> str:
    links: list[tuple[str, Path]] = [
        ("Editorial selection", bundle.selection_path),
        ("Weekly context JSON", bundle.context_path),
        ("Ideation JSON", bundle.ideation_path),
    ]
    for key, label in (("report_html", "Weekly report HTML"), ("report_json", "Weekly report JSON")):
        if key in bundle.report_artifacts:
            links.append((label, bundle.report_artifacts[key]))
    for key, label in (
        ("blog_markdown", "Blog markdown"),
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
        blog_html = _markdown_to_html(blog_path.read_text(encoding="utf-8"))
        sections.append(
            "<section class='card'>"
            "<h2>Draft post</h2>"
            f"{blog_html}"
            f"<p class='mini'><a href='{_escape_html(_relpath(blog_path, page_dir))}'>Open source markdown</a></p>"
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
    page_dir = out_path.parent
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape_html(bundle.team)} {bundle.season} Week {bundle.week} sources</title>
  <style>
    :root {{
      --bg: #f5efe3;
      --panel: #fffdf9;
      --ink: #17283a;
      --muted: #5a6b79;
      --line: #d9dddf;
      --accent: #b24f1b;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; color: var(--ink); background: linear-gradient(180deg, #f6efe4, #eee4d7); }}
    a {{ color: var(--accent); }}
    .shell {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 20px; padding: 20px 22px; margin-bottom: 18px; box-shadow: 0 16px 32px rgba(23,40,58,0.08); }}
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
      <p><strong>Selected story:</strong> {_escape_html(_clean_text(bundle.selection.get("selected_story_id")))} - {_escape_html(_clean_text(bundle.selection.get("selected_story_title")))}</p>
      <p><strong>Recommended story:</strong> {_escape_html(_clean_text(bundle.selection.get("recommended_story_id")))}</p>
      <p><strong>Selection matches recommendation:</strong> {_escape_html(str(bool(bundle.selection.get("recommended_matches_selection"))).lower())}</p>
      <p><strong>Selection reason:</strong> {_escape_html(_clean_text(bundle.selection.get("selection_reason"))) or "None"}</p>
      <p><strong>Selection mode:</strong> {_escape_html(_clean_text(bundle.selection.get("selection_mode"))) or "n/a"}</p>
    </section>
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
    form = context.get("form_snapshot", {}) if isinstance(context.get("form_snapshot"), dict) else {}
    executive = bundle.ideation.get("executive_summary", {})
    page_dir = out_path.parent
    upward = context.get("largest_upward_deltas") or []
    downward = context.get("largest_downward_deltas") or []
    week_flags = context.get("week_flags") or []
    selected = bundle.selected_story
    charts = selected.get("charts") if isinstance(selected.get("charts"), list) else []
    supporting_metrics = bundle.selection.get("selection_reason", "")

    chart_items = []
    for chart in charts[:4]:
        if not isinstance(chart, dict):
            continue
        chart_items.append(
            "<li>"
            f"<strong>{_escape_html(_clean_text(chart.get('type')))}</strong>: "
            f"{_escape_html(_clean_text(chart.get('why')))}"
            "</li>"
        )
    flags_html = "".join(
        f"<li>{_escape_html(_clean_text(flag))}</li>" for flag in week_flags[:6]
    ) or "<li class='muted'>No week flags.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape_html(bundle.team)} {bundle.season} Week {bundle.week}</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --panel: #fffdf8;
      --panel-alt: #f7f1e6;
      --ink: #17283a;
      --muted: #5a6b79;
      --line: #d9dddf;
      --accent: #b24f1b;
      --accent-soft: #f4d2bb;
      --good: #1c6b43;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; color: var(--ink); background:
      radial-gradient(circle at top left, #fff9f0 0, transparent 35%),
      linear-gradient(180deg, #f6f0e4 0%, #ece5d8 100%); }}
    a {{ color: var(--accent); }}
    .shell {{ max-width: 1080px; margin: 0 auto; padding: 28px 20px 60px; }}
    .breadcrumbs {{ font-size: 0.95rem; color: var(--muted); margin-bottom: 16px; }}
    .hero {{ background: var(--panel); border: 1px solid var(--line); border-radius: 24px; padding: 26px 28px; box-shadow: 0 20px 40px rgba(23,40,58,0.08); }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; color: var(--accent); margin: 0 0 8px; }}
    h1,h2,h3,h4 {{ margin: 0 0 12px; font-family: "Arial Narrow", "Trebuchet MS", sans-serif; }}
    h1 {{ font-size: clamp(2rem, 5vw, 3.4rem); line-height: 1.05; }}
    .subhead {{ font-size: 1.1rem; color: var(--muted); max-width: 52rem; }}
    .meta-grid, .detail-grid {{ display: grid; gap: 16px; margin-top: 22px; }}
    .meta-grid {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .detail-grid {{ grid-template-columns: 1.3fr 1fr; margin-top: 28px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px 20px; }}
    .card.alt {{ background: var(--panel-alt); }}
    .label {{ display: block; font-size: 0.76rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }}
    .value {{ font-size: 1.3rem; font-weight: 700; }}
    .story-card {{ border: 1px solid var(--line); border-radius: 18px; padding: 18px 20px; background: linear-gradient(180deg, #fffdfa, #fff8ee); }}
    .story-card.secondary {{ background: var(--panel); }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .chip {{ display: inline-flex; gap: 8px; align-items: baseline; padding: 8px 12px; border-radius: 999px; border: 1px solid var(--line); background: white; }}
    .chip em {{ color: var(--muted); font-style: normal; }}
    ul {{ margin: 0; padding-left: 20px; }}
    .muted {{ color: var(--muted); }}
    .mini {{ font-size: 0.92rem; color: var(--muted); }}
    .artifact-links {{ margin-top: 20px; font-size: 0.95rem; }}
    .footer {{ margin-top: 28px; color: var(--muted); font-size: 0.92rem; }}
    @media (max-width: 860px) {{ .detail-grid {{ grid-template-columns: 1fr; }} }}
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
      <h1>{_escape_html(_clean_text(selected.get("title")))}</h1>
      <p class="subhead">{_escape_html(_clean_text(bundle.ideation.get("recommended_story", {}).get("draft_subheading") or executive.get("headline")))}</p>
      <div class="meta-grid">
        <div class="card alt"><span class="label">Match</span><div class="value">{_escape_html(_clean_text(match.get("score")))} { _escape_html(_clean_text(match.get("result"))) }</div><div class="mini">vs {_escape_html(_clean_text(match.get("opponent")))} ({_escape_html(_clean_text(match.get("venue")))})</div></div>
        <div class="card alt"><span class="label">Recent form</span><div class="value">{int(form.get("points", 0))} pts / {float(form.get("halfwin_average", 0.0)):.2f}</div><div class="mini">Last {int(form.get("window", 0) or 0)}: {int((form.get("wdl") or {}).get("w", 0))}W-{int((form.get("wdl") or {}).get("d", 0))}D-{int((form.get("wdl") or {}).get("l", 0))}L</div></div>
        <div class="card alt"><span class="label">More detail</span><div class="value"><a href="{_escape_html(_relpath(sources_path, page_dir))}">Sources &amp; caveats</a></div><div class="mini">Method, artifact links, and process details live here.</div></div>
      </div>
    </section>

    <div class="detail-grid">
      <section class="card">
        <h2>Selected story</h2>
        <div class="story-card">
          <p><strong>Angle:</strong> {_escape_html(_clean_text(selected.get("angle")))}</p>
          <p><strong>Audience value:</strong> {_escape_html(_clean_text(selected.get("audience_value")))}</p>
          <p><strong>Peer signal:</strong> {_escape_html(_clean_text(selected.get("peer_signal")))}</p>
          <p><strong>Season-to-date signal:</strong> {_escape_html(_clean_text(selected.get("season_to_date_signal")))}</p>
          <p><strong>Risks:</strong> {_escape_html(" | ".join(_clean_text(item) for item in selected.get("risks_or_caveats", [])))}</p>
        </div>
      </section>

      <section class="card">
        <h2>Why this week matters</h2>
        <p><strong>Why now:</strong> {_escape_html(_clean_text(executive.get("why_now")))}</p>
        <p><strong>Practical takeaway:</strong> {_escape_html(_clean_text(executive.get("headline")))}</p>
      </section>

      <section class="card">
        <h2>Key signals</h2>
        <h3>Largest upward deltas</h3>
        <div class="chip-row">{"".join(_metric_chip(item) for item in upward[:5]) or "<span class='muted'>None</span>"}</div>
        <h3 style="margin-top:16px;">Largest downward deltas</h3>
        <div class="chip-row">{"".join(_metric_chip(item) for item in downward[:5]) or "<span class='muted'>None</span>"}</div>
        <h3 style="margin-top:16px;">Week flags</h3>
        <ul>{flags_html}</ul>
      </section>

      <section class="card">
        <h2>Suggested visuals</h2>
        <ul>{"".join(chart_items) or "<li class='muted'>No chart suggestions on the selected story.</li>"}</ul>
      </section>

      {(
        "<section class='card'><h2>Alternate stories</h2>"
        + _story_list_items(bundle.secondary_stories)
        + "</section>"
      ) if bundle.secondary_stories else ""}

      {_render_optional_content(bundle, page_dir)}
    </div>

    <p class="footer">Generated from weekly context, ideation, and editorial-selection artifacts.</p>
  </div>
</body>
</html>
"""


def _render_team_index(team: str, season: str, bundles: list[WeekBundle], *, out_path: Path, site_index_path: Path) -> str:
    page_dir = out_path.parent
    cards: list[str] = []
    for bundle in bundles:
        match = bundle.context.get("match", {}) if isinstance(bundle.context.get("match"), dict) else {}
        executive = bundle.ideation.get("executive_summary", {})
        cards.append(
            "<article class='week-card'>"
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
      --bg: #f7f1e5;
      --panel: #fffdf9;
      --ink: #17283a;
      --muted: #5b6d7b;
      --line: #ddd9d1;
      --accent: #b24f1b;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; color: var(--ink); background: linear-gradient(180deg, #f8f3ea, #eee4d6); }}
    a {{ color: var(--accent); }}
    .shell {{ max-width: 1080px; margin: 0 auto; padding: 28px 20px 60px; }}
    .hero, .week-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 22px; box-shadow: 0 18px 34px rgba(23,40,58,0.08); }}
    .hero {{ padding: 26px 28px; margin-bottom: 26px; }}
    .cards {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
    .week-card {{ padding: 18px 18px; }}
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
    </section>
    <section class="cards">
      {"".join(cards)}
    </section>
  </div>
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
    body {{ margin: 0; font: 16px/1.5 "Trebuchet MS", "Avenir Next", sans-serif; background: #f1eadf; color: #17283a; }}
    .shell {{ max-width: 960px; margin: 0 auto; padding: 32px 20px 60px; }}
    .hero, .card {{ background: #fffdf9; border: 1px solid #ddd5ca; border-radius: 22px; padding: 22px; box-shadow: 0 18px 34px rgba(23,40,58,0.08); }}
    .hero {{ margin-bottom: 24px; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
    h1,h2 {{ margin: 0 0 12px; font-family: "Arial Narrow", "Trebuchet MS", sans-serif; }}
    a {{ color: #b24f1b; }}
    .mini, .muted {{ color: #5b6d7b; }}
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
