#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected JSON object")
    return loaded


def default_visual_selection_path(
    *,
    selection_path: Path,
    team: str,
    season: str,
    week: int,
    report_date: str,
) -> Path:
    name = (
        f"visual-selection-{_slug(team)}-"
        f"{season.replace('-', '')}-w{week}-{report_date}.json"
    )
    return selection_path.parent / name


def _infer_report_json_path(*, reports_dir: Path, team: str, season: str, week: int) -> Path:
    pattern = f"weekly-report-{_slug(team)}-{season.replace('-', '')}-through-w{week}-*.json"
    matches = sorted(reports_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"Expected exactly one weekly report JSON matching {pattern}, found {len(matches)}"
        )
    return matches[-1]


def _story_index(ideation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    story_candidates = ideation.get("story_candidates")
    if not isinstance(story_candidates, list):
        return out
    for item in story_candidates:
        if not isinstance(item, dict):
            continue
        story_id = str(item.get("id", "")).strip()
        if story_id:
            out[story_id] = item
    return out


def _selected_story(selection: dict[str, Any], ideation: dict[str, Any]) -> dict[str, Any]:
    story_id = str(selection.get("selected_story_id", "")).strip()
    index = _story_index(ideation)
    if story_id not in index:
        raise ValueError(f"selected_story_id {story_id!r} not found in ideation story_candidates")
    return index[story_id]


def _candidate_metrics(*, selected_story: dict[str, Any], context: dict[str, Any]) -> set[str]:
    metrics: set[str] = set()
    charts = selected_story.get("charts")
    if isinstance(charts, list):
        for chart in charts:
            if not isinstance(chart, dict):
                continue
            fields = chart.get("metric_or_fields")
            if not isinstance(fields, list):
                continue
            for field in fields:
                text = str(field).strip()
                if text:
                    metrics.add(text)
    for key in ("largest_upward_deltas", "largest_downward_deltas"):
        items = context.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            metric = str(item.get("metric", "")).strip()
            if metric:
                metrics.add(metric)
    return metrics


def _chart_plan_metrics(ideation: dict[str, Any]) -> set[str]:
    metrics: set[str] = set()
    chart_plan = ideation.get("chart_plan")
    if not isinstance(chart_plan, list):
        return metrics
    for item in chart_plan:
        if not isinstance(item, dict):
            continue
        fields = item.get("metrics")
        if not isinstance(fields, list):
            continue
        for field in fields:
            text = str(field).strip()
            if text:
                metrics.add(text)
    return metrics


def _prefer_halfwin_from_chart_plan(ideation: dict[str, Any]) -> bool:
    chart_plan = ideation.get("chart_plan")
    if not isinstance(chart_plan, list):
        return False
    for item in chart_plan:
        if not isinstance(item, dict):
            continue
        if str(item.get("priority", "")).strip().lower() != "primary":
            continue
        chart_type = str(item.get("chart_type", "")).strip().lower()
        if chart_type == "result_form":
            return True
    return False


def _animation_candidates(
    *,
    report: dict[str, Any],
    team: str,
    season: str,
) -> list[dict[str, Any]]:
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    embeds = artifacts.get("embedded_animations")
    if not isinstance(embeds, list):
        return []
    out: list[dict[str, Any]] = []
    for item in embeds:
        if not isinstance(item, dict):
            continue
        if str(item.get("team", "")).strip() != team:
            continue
        if str(item.get("season", "")).strip() != season:
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        out.append(item)
    return out


def _score_candidate(
    candidate: dict[str, Any],
    *,
    preferred_metrics: set[str],
    prefer_halfwin: bool,
) -> int:
    score = 0
    kind = str(candidate.get("kind", "")).strip().lower()
    metric = str(candidate.get("metric", "")).strip()
    if kind == "halfwin":
        score += 20
        if prefer_halfwin:
            score += 120
    if kind == "metric":
        score += 10
    if metric and metric in preferred_metrics:
        score += 100
    return score


def build_visual_selection(
    *,
    selection: dict[str, Any],
    context: dict[str, Any],
    ideation: dict[str, Any],
    report: dict[str, Any],
    report_json_file: str,
    editorial_selection_file: str,
) -> dict[str, Any]:
    team = str(selection.get("team", "")).strip()
    season = str(selection.get("season", "")).strip()
    week = int(selection.get("week", 0))
    report_date = str(selection.get("report_date", "")).strip()
    selected_story = _selected_story(selection, ideation)
    candidates = _animation_candidates(report=report, team=team, season=season)
    if not candidates:
        raise ValueError("No embedded animation candidates found in report artifacts")
    preferred_metrics = _candidate_metrics(selected_story=selected_story, context=context)
    preferred_metrics.update(_chart_plan_metrics(ideation))
    prefer_halfwin = _prefer_halfwin_from_chart_plan(ideation)
    ranked = sorted(
        candidates,
        key=lambda item: (
            -_score_candidate(
                item,
                preferred_metrics=preferred_metrics,
                prefer_halfwin=prefer_halfwin,
            ),
            candidates.index(item),
        ),
    )
    primary = ranked[0]
    selected_visual_id = str(primary.get("kind", "visual")).strip()
    if str(primary.get("metric", "")).strip():
        selected_visual_id = f"{selected_visual_id}:{str(primary.get('metric')).strip()}"
    selected_visual_title = (
        "Half-win animation"
        if str(primary.get("kind", "")).strip() == "halfwin"
        else f"{str(primary.get('metric', 'Metric')).strip()} animation"
    )
    return {
        "team": team,
        "season": season,
        "week": week,
        "report_date": report_date,
        "editorial_selection_file": editorial_selection_file,
        "report_json_file": report_json_file,
        "selected_visual_id": selected_visual_id,
        "selected_visual_title": selected_visual_title,
        "selected_visual_kind": str(primary.get("kind", "")).strip(),
        "selected_visual_metric": str(primary.get("metric", "")).strip(),
        "selected_visual_path": str(primary.get("path", "")).strip(),
        "selection_mode": "auto-v1",
        "selection_reason": (
            "Auto-selected the strongest available embedded visual for the primary story and chart plan."
        ),
        "candidate_visual_ids": [
            (
                f"{str(item.get('kind', '')).strip()}:{str(item.get('metric', '')).strip()}".rstrip(":")
            )
            for item in ranked
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a weekly visual-selection artifact from report + editorial selection."
    )
    parser.add_argument("--selection-json", required=True, help="Editorial selection JSON path.")
    parser.add_argument("--report-json", default=None, help="Weekly report JSON path.")
    parser.add_argument("--out", default=None, help="Output visual-selection JSON path.")
    parser.add_argument(
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write compact JSON (default pretty).",
    )
    args = parser.parse_args()

    selection_path = Path(args.selection_json)
    selection = _load_json(selection_path)
    context_path = Path(str(selection.get("weekly_context_file", "")))
    ideation_path = Path(str(selection.get("ideation_file", "")))
    context = _load_json(context_path)
    ideation = _load_json(ideation_path)
    report_json_path = (
        Path(args.report_json)
        if args.report_json
        else _infer_report_json_path(
            reports_dir=selection_path.parent,
            team=str(selection.get("team", "")),
            season=str(selection.get("season", "")),
            week=int(selection.get("week", 0)),
        )
    )
    report = _load_json(report_json_path)

    visual_selection = build_visual_selection(
        selection=selection,
        context=context,
        ideation=ideation,
        report=report,
        report_json_file=str(report_json_path),
        editorial_selection_file=str(selection_path),
    )
    out_path = (
        Path(args.out)
        if args.out
        else default_visual_selection_path(
            selection_path=selection_path,
            team=str(visual_selection["team"]),
            season=str(visual_selection["season"]),
            week=int(visual_selection["week"]),
            report_date=str(visual_selection["report_date"]),
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(visual_selection, separators=(",", ":"))
        if args.compact
        else json.dumps(visual_selection, indent=2)
    )
    out_path.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Selected visual: {visual_selection['selected_visual_title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
