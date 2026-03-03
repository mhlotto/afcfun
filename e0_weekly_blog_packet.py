#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _display_path(path: Path) -> str:
    try:
        return os.path.relpath(path, Path.cwd())
    except ValueError:
        return str(path)


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


def default_packet_path(*, team: str, season: str, week: int) -> Path:
    season_key = season.replace("-", "")
    return Path("exports") / f"weekly-blog-packet-{_slug(team)}-{season_key}-w{week}.md"


def default_blog_output_path(*, team: str, season: str, week: int) -> Path:
    season_key = season.replace("-", "")
    return Path("docs/reports") / f"weekly-post-{_slug(team)}-{season_key}-w{week}.md"


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _story_index(ideation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    story_candidates = ideation.get("story_candidates")
    if not isinstance(story_candidates, list):
        raise ValueError("ideation JSON missing story_candidates list")
    out: dict[str, dict[str, Any]] = {}
    for item in story_candidates:
        if not isinstance(item, dict):
            continue
        story_id = str(item.get("id", "")).strip()
        if story_id:
            out[story_id] = item
    return out


def _render_packet(
    *,
    selection_path: Path,
    selection: dict[str, Any],
    context_path: Path,
    ideation_path: Path,
    selected_story: dict[str, Any],
    out_blog_path: Path,
) -> str:
    team = str(selection["team"])
    season = str(selection["season"])
    week = int(selection["week"])
    blog_prompt = Path("docs/prompts/weekly_blog_prompt.md")

    selected_story_json = json.dumps(selected_story, indent=2)

    lines = [
        f"# Weekly blog packet: {team} {season} week {week}",
        "",
        "## Files",
        f"- blog prompt: `{_display_path(blog_prompt)}`",
        f"- editorial selection: `{_display_path(selection_path)}`",
        f"- ideation json: `{_display_path(ideation_path)}`",
        f"- weekly context json: `{_display_path(context_path)}`",
        f"- save draft to: `{_display_path(out_blog_path)}`",
        "",
        "## Selected story",
        "```json",
        selected_story_json,
        "```",
        "",
        "## Selection reason",
        selection.get("selection_reason", "") or "(none)",
        "",
        "## ChatGPT workflow",
        "1. Open a fresh chat.",
        "2. Paste the contents of `docs/prompts/weekly_blog_prompt.md`.",
        "3. Paste the `Selected story` JSON block from this packet.",
        "4. Paste the weekly context JSON contents.",
        "5. Optionally paste the editorial selection JSON if you want the model to see your selection metadata.",
        "6. Ask: `Write the weekly blog draft in markdown.`",
        "7. Copy the markdown response into the `save draft to` path listed above.",
        "",
        "## Notes",
        "- Keep the weekly context JSON as the main grounding artifact.",
        "- The selected story JSON is the narrow story brief; the context JSON is the evidence base.",
        "- Use a fresh chat to avoid prior-week framing carryover.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print or write a copy/paste packet for ChatGPT weekly blog drafting."
    )
    parser.add_argument(
        "--selection-json",
        required=True,
        help="Editorial selection JSON path.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional markdown output path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--write-default",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write to exports/weekly-blog-packet-...md when --out is omitted.",
    )
    args = parser.parse_args()

    selection_path = Path(args.selection_json).resolve()
    selection = _load_json(selection_path)
    context_path = _resolve_path(str(selection.get("weekly_context_file", "")))
    ideation_path = _resolve_path(str(selection.get("ideation_file", "")))
    context = _load_json(context_path)
    ideation = _load_json(ideation_path)
    story_index = _story_index(ideation)
    selected_story_id = str(selection.get("selected_story_id", "")).strip()
    if selected_story_id not in story_index:
        raise ValueError(
            f"{selection_path}: selected_story_id {selected_story_id!r} not found in ideation story_candidates"
        )
    selected_story = story_index[selected_story_id]

    team = str(selection.get("team") or context.get("meta", {}).get("team") or "")
    season = str(selection.get("season") or context.get("meta", {}).get("season") or "")
    week = int(selection.get("week") or context.get("meta", {}).get("week") or 0)
    packet = _render_packet(
        selection_path=selection_path,
        selection=selection,
        context_path=context_path,
        ideation_path=ideation_path,
        selected_story=selected_story,
        out_blog_path=default_blog_output_path(team=team, season=season, week=week),
    )

    if args.out or args.write_default:
        out_path = (
            Path(args.out)
            if args.out
            else default_packet_path(team=team, season=season, week=week)
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(packet, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(packet, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
