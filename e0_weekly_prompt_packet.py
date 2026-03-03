#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from e0_weekly_context_export import build_weekly_context, default_context_path


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


def default_packet_path(*, team: str, season: str, week: int) -> Path:
    season_key = season.replace("-", "")
    return Path("exports") / f"weekly-prompt-packet-{_slug(team)}-{season_key}-w{week}.md"


def _resolve_context_path(
    *,
    report_path: Path,
    report: dict[str, object],
    team: str | None,
    season: str | None,
    week: int | None,
    explicit_context_path: str | None,
) -> Path:
    if explicit_context_path:
        return Path(explicit_context_path)
    context = build_weekly_context(
        report=report,
        team=team,
        season=season,
        week=week,
    )
    meta = context["meta"]
    return default_context_path(
        report_path=report_path,
        team=str(meta["team"]),
        season=str(meta["season"]),
        week=int(meta["week"]),
        report_date=str(meta["report_date"]),
    )


def _render_packet(
    *,
    report_path: Path,
    context_path: Path,
    team: str,
    season: str,
    week: int,
) -> str:
    ideation_prompt = Path("docs/prompts/weekly_ideation_prompt.md")
    blog_prompt = Path("docs/prompts/weekly_blog_prompt.md")
    report_json = _display_path(report_path)
    context_json = _display_path(context_path)

    lines = [
        f"# Weekly prompt packet: {team} {season} week {week}",
        "",
        "## Files",
        f"- ideation prompt: `{_display_path(ideation_prompt)}`",
        f"- blog prompt: `{_display_path(blog_prompt)}`",
        f"- weekly report json: `{report_json}`",
        f"- weekly context json: `{context_json}`",
        "",
    ]
    if not context_path.exists():
        lines.extend(
            [
                "## Generate missing context JSON",
                "```bash",
                "./bin/python e0_weekly_context_export.py \\",
                f"  --report-json {report_json} \\",
                f"  --team \"{team}\" \\",
                f"  --season {season} \\",
                f"  --week {week} \\",
                f"  --out {context_json}",
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## ChatGPT workflow",
            "1. Open a new chat.",
            "2. Paste the ideation prompt file contents.",
            "3. Paste the weekly context JSON contents.",
            "4. Ask: `Generate this week's ideation pack.`",
            "5. Pick one story candidate.",
            "6. In a new message, paste the blog prompt file contents.",
            "7. Paste the chosen story candidate and the same weekly context JSON.",
            "8. Ask: `Write the blog draft.`",
            "",
            "## Notes",
            "- The report JSON is useful as backup context if ChatGPT needs more detail.",
            "- The context JSON should remain the primary grounding artifact.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print or write the weekly ChatGPT prompt packet for a report/context pair."
    )
    parser.add_argument(
        "--report-json",
        required=True,
        help="Weekly report JSON produced by e0_weekly_report_data/run.",
    )
    parser.add_argument("--team", default=None, help="Optional team override.")
    parser.add_argument("--season", default=None, help="Optional season override.")
    parser.add_argument("--week", type=int, default=None, help="Optional week override.")
    parser.add_argument(
        "--context-json",
        default=None,
        help="Optional existing weekly context JSON path. Defaults to inferred export path.",
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
        help="Write to exports/weekly-prompt-packet-...md when --out is omitted.",
    )
    args = parser.parse_args()

    report_path = Path(args.report_json)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    context = build_weekly_context(
        report=report,
        team=args.team,
        season=args.season,
        week=args.week,
    )
    meta = context["meta"]
    context_path = _resolve_context_path(
        report_path=report_path,
        report=report,
        team=args.team,
        season=args.season,
        week=args.week,
        explicit_context_path=args.context_json,
    )

    packet = _render_packet(
        report_path=report_path,
        context_path=context_path,
        team=str(meta["team"]),
        season=str(meta["season"]),
        week=int(meta["week"]),
    )

    if args.out or args.write_default:
        out_path = (
            Path(args.out)
            if args.out
            else default_packet_path(
                team=str(meta["team"]),
                season=str(meta["season"]),
                week=int(meta["week"]),
            )
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(packet, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(packet, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
