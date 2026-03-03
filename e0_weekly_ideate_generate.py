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


def default_ideation_output_path(*, context_json: Path, week: int) -> Path:
    return context_json.parent / f"weekly-chatgpt-ideate-w{week}.json"


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected JSON object")
    return loaded


def ideation_json_schema() -> dict[str, Any]:
    delta_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "metric": {"type": "string"},
            "delta": {"type": "number"},
        },
        "required": ["metric", "delta"],
    }
    chart_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": ["line", "bar", "scatter", "heatmap"]},
            "metric_or_fields": {"type": "array", "items": {"type": "string"}},
            "why": {"type": "string"},
        },
        "required": ["type", "metric_or_fields", "why"],
    }
    hypothesis_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "claim": {"type": "string"},
            "signal_strength": {"type": "string", "enum": ["weak", "moderate", "strong"]},
            "evidence_from_context": {"type": "array", "items": {"type": "string"}},
            "corroborating_signals": {"type": "array", "items": {"type": "string"}},
            "what_to_check_next": {"type": "array", "items": {"type": "string"}},
            "novelty": {"type": "string", "enum": ["standard", "interesting", "weird"]},
        },
        "required": [
            "id",
            "title",
            "claim",
            "signal_strength",
            "evidence_from_context",
            "corroborating_signals",
            "what_to_check_next",
            "novelty",
        ],
    }
    story_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "angle": {"type": "string"},
            "peg_type": {
                "type": "string",
                "enum": ["week-spike", "season-trend", "peer-shift", "anomaly", "mixed"],
            },
            "audience_value": {"type": "string"},
            "signal_strength": {"type": "string", "enum": ["weak", "moderate", "strong"]},
            "charts": {"type": "array", "items": chart_item},
            "risks_or_caveats": {"type": "array", "items": {"type": "string"}},
            "why_not_top_story": {"type": "string"},
            "peer_signal": {"type": "string"},
            "season_to_date_signal": {"type": "string"},
        },
        "required": [
            "id",
            "title",
            "angle",
            "peg_type",
            "audience_value",
            "signal_strength",
            "charts",
            "risks_or_caveats",
            "why_not_top_story",
            "peer_signal",
            "season_to_date_signal",
        ],
    }
    return {
        "type": "json_schema",
        "name": "weekly_ideation_pack",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "executive_summary": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "headline": {"type": "string"},
                        "why_now": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "confidence_rationale": {"type": "string"},
                    },
                    "required": ["headline", "why_now", "confidence", "confidence_rationale"],
                },
                "state_snapshot": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "match": {"type": "string"},
                        "form_window_takeaway": {"type": "string"},
                        "top_positive_delta": {"type": "array", "items": delta_item},
                        "top_negative_delta": {"type": "array", "items": delta_item},
                        "peer_context_takeaway": {"type": "string"},
                        "season_vs_week_tension": {"type": "string"},
                    },
                    "required": [
                        "match",
                        "form_window_takeaway",
                        "top_positive_delta",
                        "top_negative_delta",
                        "peer_context_takeaway",
                        "season_vs_week_tension",
                    ],
                },
                "hypotheses": {"type": "array", "items": hypothesis_item},
                "story_candidates": {"type": "array", "items": story_item},
                "recommended_story": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "story_id": {"type": "string"},
                        "reason": {"type": "string"},
                        "draft_subheading": {"type": "string"},
                        "supporting_metrics": {"type": "array", "items": {"type": "string"}},
                        "supporting_peer_metrics": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "story_id",
                        "reason",
                        "draft_subheading",
                        "supporting_metrics",
                        "supporting_peer_metrics",
                    ],
                },
                "data_gaps": {"type": "array", "items": {"type": "string"}},
                "next_week_data_to_collect": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "executive_summary",
                "state_snapshot",
                "hypotheses",
                "story_candidates",
                "recommended_story",
                "data_gaps",
                "next_week_data_to_collect",
            ],
        },
        "strict": True,
    }


def build_ideation_input(context: dict[str, Any]) -> str:
    return (
        "Generate the weekly ideation pack from this weekly_context JSON.\n\n"
        "weekly_context:\n"
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
        description="Generate weekly ideation JSON via the OpenAI Responses API."
    )
    parser.add_argument("--context-json", required=True, help="Weekly context JSON path.")
    parser.add_argument(
        "--prompt-file",
        default="docs/prompts/weekly_ideation_prompt.md",
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
        help="Optional output path. Defaults to docs/reports/weekly-chatgpt-ideate-wN.json.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=8000,
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

    context_path = Path(args.context_json)
    context = _load_json(context_path)
    meta = context.get("meta")
    if not isinstance(meta, dict):
        raise ValueError(f"{context_path}: missing meta object")
    week = int(meta.get("week"))
    out_path = (
        Path(args.out)
        if args.out
        else default_ideation_output_path(context_json=context_path, week=week)
    )
    if args.dry_run:
        print(f"Would write {out_path}")
        return 0
    if out_path.exists() and not args.overwrite:
        raise FileExistsError(f"{out_path} already exists; use --overwrite to replace it")

    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")

    response = create_response(
        model=args.model,
        instructions=prompt_text
        + "\n\nReturn only the JSON object matching the required structure.",
        input_text=build_ideation_input(context),
        text_format=ideation_json_schema(),
        max_output_tokens=args.max_output_tokens,
        store=args.store,
    )
    reason = incomplete_reason(response)
    if reason:
        output_text = extract_output_text(response)
        raw_path, response_path = _write_debug_artifacts(
            out_path=out_path,
            response=response,
            output_text=output_text,
        )
        raise RuntimeError(
            "OpenAI response was incomplete "
            f"(reason: {reason}). Wrote debug artifacts to {raw_path} and {response_path}. "
            "Try rerunning with a larger --max-output-tokens."
        )
    output_text = extract_output_text(response)
    try:
        ideation = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raw_path, response_path = _write_debug_artifacts(
            out_path=out_path,
            response=response,
            output_text=output_text,
        )
        raise RuntimeError(
            "OpenAI returned ideation text that was not valid JSON. "
            f"Wrote debug artifacts to {raw_path} and {response_path}. "
            "This usually means the response was truncated; rerun with a larger "
            "--max-output-tokens."
        ) from exc
    out_path.write_text(json.dumps(ideation, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
