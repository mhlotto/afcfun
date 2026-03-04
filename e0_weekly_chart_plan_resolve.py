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


def _resolve_candidates(report: dict[str, Any], *, team: str, season: str) -> list[dict[str, Any]]:
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
        out.append(item)
    return out


def _resolve_plan_item(item: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    chart_type = str(item.get("chart_type", "")).strip().lower()
    metrics = [str(v).strip() for v in item.get("metrics", []) if str(v).strip()]

    if chart_type == "result_form":
        for candidate in candidates:
            if str(candidate.get("kind", "")).strip().lower() == "halfwin":
                return {
                    "status": "mapped",
                    "kind": "halfwin",
                    "metric": "",
                    "path": str(candidate.get("path", "")),
                }

    for metric in metrics:
        for candidate in candidates:
            if str(candidate.get("kind", "")).strip().lower() != "metric":
                continue
            if str(candidate.get("metric", "")).strip() != metric:
                continue
            return {
                "status": "mapped",
                "kind": "metric",
                "metric": metric,
                "path": str(candidate.get("path", "")),
            }

    return {
        "status": "unmapped",
        "kind": "",
        "metric": "",
        "path": "",
        "reason": "No matching embedded animation for chart intent.",
    }


def default_output_path(ideation_path: Path, week: int) -> Path:
    return ideation_path.parent / f"weekly-chart-plan-resolved-w{week}.json"


def _infer_report_json_path(*, reports_dir: Path, team: str, season: str, week: int) -> Path:
    pattern = f"weekly-report-{_slug(team)}-{season.replace('-', '')}-through-w{week}-*.json"
    matches = sorted(reports_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No report JSON matched {pattern}")
    return matches[-1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve ideation chart_plan items to local renderable chart artifacts."
    )
    parser.add_argument("--ideation-json", default="", help="Weekly ideation JSON path.")
    parser.add_argument("--report-json", default="", help="Weekly report JSON path.")
    parser.add_argument("--context-json", default="", help="Weekly context JSON path.")
    parser.add_argument(
        "--selection-json",
        default="",
        help="Optional editorial selection JSON; if set, ideation/context/report paths are inferred.",
    )
    parser.add_argument("--out", default=None, help="Output JSON path.")
    parser.add_argument(
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write compact JSON (default pretty).",
    )
    args = parser.parse_args()

    if args.selection_json:
        selection_path = Path(args.selection_json)
        selection = _load_json(selection_path)
        ideation_path = Path(str(selection.get("ideation_file", "")))
        context_path = Path(str(selection.get("weekly_context_file", "")))
        if not ideation_path.is_absolute():
            ideation_path = Path.cwd() / ideation_path
        if not context_path.is_absolute():
            context_path = Path.cwd() / context_path
        team = str(selection.get("team", "")).strip()
        season = str(selection.get("season", "")).strip()
        week = int(selection.get("week", 0))
        report_path = (
            Path(args.report_json)
            if args.report_json
            else _infer_report_json_path(
                reports_dir=selection_path.parent,
                team=team,
                season=season,
                week=week,
            )
        )
    else:
        if not args.ideation_json or not args.context_json or not args.report_json:
            raise ValueError(
                "Provide --selection-json or all of --ideation-json/--context-json/--report-json."
            )
        ideation_path = Path(args.ideation_json)
        context_path = Path(args.context_json)
        report_path = Path(args.report_json)

    report = _load_json(report_path)
    ideation = _load_json(ideation_path)
    context = _load_json(context_path)

    meta = context.get("meta", {})
    if not isinstance(meta, dict):
        raise ValueError("context JSON missing meta object")
    team = str(meta.get("team", "")).strip()
    season = str(meta.get("season", "")).strip()
    week = int(meta.get("week", 0))

    candidates = _resolve_candidates(report, team=team, season=season)
    chart_plan = ideation.get("chart_plan")
    if not isinstance(chart_plan, list):
        chart_plan = []

    resolved_items: list[dict[str, Any]] = []
    for item in chart_plan:
        if not isinstance(item, dict):
            continue
        resolved = _resolve_plan_item(item, candidates)
        out_item = dict(item)
        out_item["resolved"] = resolved
        resolved_items.append(out_item)

    primary = next(
        (
            item
            for item in resolved_items
            if str(item.get("priority", "")).strip().lower() == "primary"
            and isinstance(item.get("resolved"), dict)
            and item["resolved"].get("status") == "mapped"
        ),
        None,
    )
    out = {
        "team": team,
        "season": season,
        "week": week,
        "report_json_file": str(report_path),
        "ideation_file": str(ideation_path),
        "context_file": str(context_path),
        "chart_plan_items": resolved_items,
        "primary_mapped_chart_id": str(primary.get("id", "")) if isinstance(primary, dict) else "",
    }
    out_path = Path(args.out) if args.out else default_output_path(ideation_path, week)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, separators=(",", ":")) if args.compact else json.dumps(out, indent=2)
    out_path.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    mapped = sum(
        1 for item in resolved_items
        if isinstance(item.get("resolved"), dict) and item["resolved"].get("status") == "mapped"
    )
    print(f"Chart intents: {len(resolved_items)} | mapped: {mapped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
