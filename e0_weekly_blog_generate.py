#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from openai_responses_client import (
    create_response,
    extract_output_text,
    incomplete_reason,
    model_from_env,
)


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected JSON object")
    return loaded


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


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


def default_blog_output_path(*, team: str, season: str, week: int) -> Path:
    season_key = season.replace("-", "")
    return Path("docs/reports") / f"weekly-post-{_slug(team)}-{season_key}-w{week}.md"


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


def build_blog_input(
    *,
    selected_story: dict[str, Any],
    context: dict[str, Any],
    selection: dict[str, Any],
) -> str:
    return (
        "Write the weekly blog draft in markdown from the selected story and weekly_context.\n\n"
        "selected_story_candidate:\n"
        + json.dumps(selected_story, indent=2)
        + "\n\nselection_metadata:\n"
        + json.dumps(selection, indent=2)
        + "\n\nweekly_context:\n"
        + json.dumps(context, indent=2)
    )


def _write_debug_artifacts(
    *,
    out_path: Path,
    response: dict[str, Any],
    output_text: str,
) -> tuple[Path, Path]:
    raw_path = out_path.with_suffix(".raw.txt")
    response_path = out_path.with_suffix(".response.json")
    raw_path.write_text(output_text, encoding="utf-8")
    response_path.write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    return raw_path, response_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate weekly blog markdown via the OpenAI Responses API."
    )
    parser.add_argument("--selection-json", required=True, help="Editorial selection JSON path.")
    parser.add_argument(
        "--prompt-file",
        default="docs/prompts/weekly_blog_prompt.md",
        help="Prompt markdown file.",
    )
    parser.add_argument(
        "--model",
        default=model_from_env(),
        help="OpenAI model name. Defaults to OPENAI_MODEL or gpt-5.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional markdown output path. Defaults to docs/reports/weekly-post-...md.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=2500,
        help="Max output tokens for the Responses API call.",
    )
    parser.add_argument(
        "--store",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Whether to allow OpenAI to store the response object.",
    )
    parser.add_argument(
        "--overwrite",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Overwrite the output file if it exists.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Resolve inputs and print the output path without calling the API.",
    )
    args = parser.parse_args()

    selection_path = Path(args.selection_json)
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
    out_path = (
        Path(args.out)
        if args.out
        else default_blog_output_path(team=team, season=season, week=week)
    )
    if args.dry_run:
        print(f"Would write {out_path}")
        return 0
    if out_path.exists() and not args.overwrite:
        raise FileExistsError(f"{out_path} already exists; use --overwrite to replace it")

    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")

    response = create_response(
        model=args.model,
        instructions=prompt_text + "\n\nReturn markdown only.",
        input_text=build_blog_input(
            selected_story=selected_story,
            context=context,
            selection=selection,
        ),
        max_output_tokens=args.max_output_tokens,
        store=args.store,
    )
    markdown = extract_output_text(response)
    reason = incomplete_reason(response)
    if reason:
        raw_path, response_path = _write_debug_artifacts(
            out_path=out_path,
            response=response,
            output_text=markdown,
        )
        raise RuntimeError(
            "OpenAI response was incomplete "
            f"(reason: {reason}). Wrote debug artifacts to {raw_path} and {response_path}. "
            "Try rerunning with a larger --max-output-tokens."
        )
    markdown = markdown.strip() + "\n"
    out_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
