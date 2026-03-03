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


def default_editorial_selection_path(
    *,
    context_path: Path,
    team: str,
    season: str,
    week: int,
    report_date: str,
) -> Path:
    name = (
        f"editorial-selection-{_slug(team)}-"
        f"{season.replace('-', '')}-w{week}-{report_date}.json"
    )
    return context_path.parent / name


def _load_json(path: str) -> dict[str, Any]:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected JSON object")
    return loaded


def _story_candidates_index(ideation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    story_candidates = ideation.get("story_candidates")
    if not isinstance(story_candidates, list):
        raise ValueError("ideation JSON missing story_candidates list")
    index: dict[str, dict[str, Any]] = {}
    for item in story_candidates:
        if not isinstance(item, dict):
            continue
        story_id = str(item.get("id", "")).strip()
        if not story_id:
            continue
        index[story_id] = item
    if not index:
        raise ValueError("ideation JSON does not contain any valid story_candidates ids")
    return index


def _validate_story_ids(
    *,
    story_index: dict[str, dict[str, Any]],
    selected_story_id: str,
    secondary_story_ids: list[str],
    rejected_story_ids: list[str],
) -> None:
    missing = [
        story_id
        for story_id in [selected_story_id, *secondary_story_ids, *rejected_story_ids]
        if story_id not in story_index
    ]
    if missing:
        raise ValueError(f"Unknown story id(s): {', '.join(missing)}")


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def build_editorial_selection(
    *,
    ideation: dict[str, Any],
    context: dict[str, Any],
    ideation_file: str,
    context_file: str,
    selected_story_id: str,
    secondary_story_ids: list[str],
    rejected_story_ids: list[str],
    selection_reason: str,
    notes: list[str],
    selection_mode: str = "manual",
) -> dict[str, Any]:
    story_index = _story_candidates_index(ideation)
    secondary_story_ids = _unique(secondary_story_ids)
    rejected_story_ids = _unique(rejected_story_ids)
    _validate_story_ids(
        story_index=story_index,
        selected_story_id=selected_story_id,
        secondary_story_ids=secondary_story_ids,
        rejected_story_ids=rejected_story_ids,
    )

    meta = context.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("context JSON missing meta object")

    selected_story = story_index[selected_story_id]
    recommended_story = ideation.get("recommended_story", {})
    recommended_story_id = (
        str(recommended_story.get("story_id", "")).strip()
        if isinstance(recommended_story, dict)
        else ""
    )

    return {
        "team": str(meta.get("team", "")),
        "season": str(meta.get("season", "")),
        "week": int(meta.get("week")),
        "report_date": str(meta.get("report_date", "")),
        "weekly_context_file": context_file,
        "ideation_file": ideation_file,
        "selected_story_id": selected_story_id,
        "selected_story_title": str(selected_story.get("title", "")),
        "secondary_story_ids": secondary_story_ids,
        "rejected_story_ids": rejected_story_ids,
        "recommended_story_id": recommended_story_id,
        "recommended_matches_selection": recommended_story_id == selected_story_id,
        "selection_reason": selection_reason,
        "selection_mode": selection_mode,
        "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write a weekly editorial selection artifact from ideation + context JSON."
    )
    parser.add_argument("--ideation-json", required=True, help="ChatGPT ideation JSON path.")
    parser.add_argument("--context-json", required=True, help="Weekly context JSON path.")
    parser.add_argument("--story-id", required=True, help="Selected story id from story_candidates.")
    parser.add_argument(
        "--secondary-story-id",
        action="append",
        default=[],
        help="Optional secondary story id. Repeat flag for multiple.",
    )
    parser.add_argument(
        "--rejected-story-id",
        action="append",
        default=[],
        help="Optional rejected story id. Repeat flag for multiple.",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Short explanation for why this story was selected.",
    )
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Optional note. Repeat flag for multiple.",
    )
    parser.add_argument(
        "--selection-mode",
        default="manual",
        help="Selection mode label (default: manual).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output path. Defaults to docs/reports/editorial-selection-...json",
    )
    parser.add_argument(
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write compact JSON (default pretty).",
    )
    args = parser.parse_args()

    ideation = _load_json(args.ideation_json)
    context = _load_json(args.context_json)

    selection = build_editorial_selection(
        ideation=ideation,
        context=context,
        ideation_file=args.ideation_json,
        context_file=args.context_json,
        selected_story_id=args.story_id,
        secondary_story_ids=list(args.secondary_story_id),
        rejected_story_ids=list(args.rejected_story_id),
        selection_reason=args.reason,
        notes=list(args.note),
        selection_mode=args.selection_mode,
    )

    out_path = (
        Path(args.out)
        if args.out
        else default_editorial_selection_path(
            context_path=Path(args.context_json),
            team=str(selection["team"]),
            season=str(selection["season"]),
            week=int(selection["week"]),
            report_date=str(selection["report_date"]),
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(selection, separators=(",", ":"))
        if args.compact
        else json.dumps(selection, indent=2)
    )
    out_path.write_text(text + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Selected story: {selection['selected_story_id']} - {selection['selected_story_title']}")
    print(f"Recommended matches selection: {selection['recommended_matches_selection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
