#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from e0_season_utils import parse_season_filter
from e0_weekly_halfwin_animate import (
    _build_payload_from_series as _build_halfwin_payload_from_series,
    write_animation_html,
)
from e0_weekly_halfwin_plot import build_team_series_from_db
from e0_weekly_metric_animate import (
    _build_payload as _build_metric_payload,
    write_metric_animation_html,
)
from e0_weekly_metric_plot import build_team_metric_series
from e0_weekly_halfwin_plot import parse_teams
from e0_weekly_report_annotations import (
    apply_weekly_annotations,
    load_weekly_annotations,
)
from e0_weekly_report_data import (
    _parse_metrics,
    _resolve_default_seasons,
    build_weekly_report,
    default_report_json_path,
    write_report_json,
)
from e0_weekly_report_html import default_report_html_path, render_report_html
from e0_weekly_report_schema import assert_valid_weekly_report_schema


def _slug(text: str) -> str:
    chars: list[str] = []
    prev_dash = False
    for ch in text.strip().lower():
        if ch.isalnum():
            chars.append(ch)
            prev_dash = False
            continue
        if not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-") or "value"


def _build_embedded_animation_artifacts(
    *,
    report: dict[str, object],
    out_html: Path,
    db_path: str,
    competition_code: str,
    side: str,
    metric: str,
    style: str,
    interval_ms: int,
    through_week: int | None,
) -> list[dict[str, object]]:
    assets_dir = out_html.parent / f"{out_html.stem}_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    embeds: list[dict[str, object]] = []
    for team_block in report.get("teams", []):
        if not isinstance(team_block, dict):
            continue
        team = str(team_block.get("team", "")).strip()
        if not team:
            continue
        seasons = team_block.get("seasons", [])
        if not isinstance(seasons, list):
            continue
        for season_block in seasons:
            if not isinstance(season_block, dict):
                continue
            season = str(season_block.get("season", "")).strip()
            if not season:
                continue

            halfwin_series = build_team_series_from_db(
                db_path=db_path,
                teams=[team],
                side=side,
                competition_code=competition_code,
                seasons=[season],
            )
            if through_week is not None:
                halfwin_series = {
                    key: [point for point in points if point.week <= through_week]
                    for key, points in halfwin_series.items()
                }
            halfwin_payload = _build_halfwin_payload_from_series(
                halfwin_series,
                [team],
                {},
                style=style,
            )
            halfwin_out = assets_dir / f"{_slug(team)}-{season}-halfwin.html"
            write_animation_html(
                out_path=halfwin_out,
                payload=halfwin_payload,
                interval_ms=interval_ms,
                title=f"{team} ({season}): Weekly Half-Win Average + Cumulative Points",
                trail_glow=False,
                style=style,
            )
            embeds.append(
                {
                    "team": team,
                    "season": season,
                    "kind": "halfwin",
                    "path": str(halfwin_out.relative_to(out_html.parent)),
                }
            )

            metric_series = build_team_metric_series(
                source="db",
                teams=[team],
                side=side,
                metric=metric,
                csv_path="",
                db_path=db_path,
                competition_code=competition_code,
                seasons=[season],
            )
            if through_week is not None:
                metric_series = {
                    key: [point for point in points if point.week <= through_week]
                    for key, points in metric_series.items()
                }
            metric_payload = _build_metric_payload(
                metric_series,
                metric=metric,
                style=style,
            )
            metric_out = assets_dir / f"{_slug(team)}-{season}-{_slug(metric)}.html"
            write_metric_animation_html(
                out_path=metric_out,
                payload=metric_payload,
                interval_ms=interval_ms,
                title=f"{team} ({season}): Weekly {metric}",
                style=style,
            )
            embeds.append(
                {
                    "team": team,
                    "season": season,
                    "kind": "metric",
                    "metric": metric,
                    "path": str(metric_out.relative_to(out_html.parent)),
                }
            )
    return embeds


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run weekly report pipeline: build JSON then render HTML."
    )
    parser.add_argument(
        "--db",
        default="data/footstat.sqlite3",
        help="SQLite file path.",
    )
    parser.add_argument(
        "--competition",
        default="E0",
        help="Competition code.",
    )
    parser.add_argument(
        "--team",
        default="Arsenal",
        help="Team name(s), comma-delimited.",
    )
    parser.add_argument(
        "--side",
        default="both",
        choices=["home", "away", "both"],
        help="Filter matches by venue.",
    )
    parser.add_argument(
        "--seasons",
        default=None,
        help=(
            "Optional season filters (YYYY-YYYY or YYYYYYYY, comma-delimited). "
            "If omitted, uses latest season in DB for competition."
        ),
    )
    parser.add_argument(
        "--metrics",
        default=None,
        help="Optional comma-delimited normalized metrics to include in report series.",
    )
    parser.add_argument(
        "--report-date",
        default=dt.date.today().isoformat(),
        help="Logical report date (YYYY-MM-DD) used in output naming/metadata.",
    )
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=2.0,
        help="Absolute z-score threshold for metric_outlier_zscore detector.",
    )
    parser.add_argument(
        "--regime-effect-threshold",
        type=float,
        default=0.8,
        help="Absolute effect size threshold for regime_shift detector.",
    )
    parser.add_argument(
        "--out-json",
        default=None,
        help="Output JSON path. Default uses docs/reports/weekly-report-...json",
    )
    parser.add_argument(
        "--out-html",
        default=None,
        help="Output HTML path. Default matches --out-json basename.",
    )
    parser.add_argument(
        "--annotations",
        default=None,
        help=(
            "Optional JSON config for team/season/week annotations "
            "(media/events/notes)."
        ),
    )
    parser.add_argument(
        "--report-style",
        default="classic",
        choices=["classic", "cinematic"],
        help="Visual style preset for report HTML page.",
    )
    parser.add_argument(
        "--embed-animations",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate and embed half-win + metric animation iframes in report HTML.",
    )
    parser.add_argument(
        "--embed-metric",
        default="opponent_fouls",
        help="Metric used for embedded metric animation.",
    )
    parser.add_argument(
        "--embed-style",
        default="cinematic",
        choices=["classic", "cinematic"],
        help="Style used for embedded animation assets.",
    )
    parser.add_argument(
        "--embed-interval-ms",
        type=int,
        default=500,
        help="Interval for embedded animations in milliseconds.",
    )
    parser.add_argument(
        "--league-context",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Include same-season peer team context in the report JSON for stronger "
            "weekly league-relative context export."
        ),
    )
    parser.add_argument(
        "--through-week",
        type=int,
        default=None,
        help="Optional inclusive week cutoff; only include matches up to this week.",
    )
    args = parser.parse_args()
    if args.z_threshold <= 0:
        raise ValueError("--z-threshold must be > 0.")
    if args.regime_effect_threshold <= 0:
        raise ValueError("--regime-effect-threshold must be > 0.")
    if args.through_week is not None and args.through_week <= 0:
        raise ValueError("--through-week must be > 0.")

    teams = parse_teams(args.team)
    season_filter = parse_season_filter(args.seasons)
    seasons = (
        season_filter
        if season_filter is not None
        else _resolve_default_seasons(
            db_path=args.db,
            competition_code=args.competition,
        )
    )
    metrics = _parse_metrics(args.metrics)

    report = build_weekly_report(
        db_path=args.db,
        competition_code=args.competition,
        teams=teams,
        side=args.side,
        seasons=seasons,
        metrics=metrics,
        report_date=args.report_date,
        z_threshold=args.z_threshold,
        regime_effect_threshold=args.regime_effect_threshold,
        include_league_context=args.league_context,
        through_week=args.through_week,
    )
    annotations = load_weekly_annotations(args.annotations)
    annotation_count = apply_weekly_annotations(report, annotations)

    out_json = (
        Path(args.out_json)
        if args.out_json
        else default_report_json_path(
            teams=teams,
            seasons=seasons,
            report_date=args.report_date,
            through_week=args.through_week,
        )
    )
    out_html = Path(args.out_html) if args.out_html else default_report_html_path(out_json)
    if args.embed_animations:
        embeds = _build_embedded_animation_artifacts(
            report=report,
            out_html=out_html,
            db_path=args.db,
            competition_code=args.competition,
            side=args.side,
            metric=args.embed_metric,
            style=args.embed_style,
            interval_ms=max(50, args.embed_interval_ms),
            through_week=args.through_week,
        )
        report["artifacts"] = {"embedded_animations": embeds}

    assert_valid_weekly_report_schema(report)
    write_report_json(report, out_path=out_json, pretty=True)
    render_report_html(report, out_path=out_html, in_path=out_json, style=args.report_style)

    print(f"Wrote {out_json}")
    print(f"Wrote {out_html}")
    print(f"Teams: {', '.join(teams)}")
    print(f"Seasons: {', '.join(seasons)}")
    if args.through_week is not None:
        print(f"Through week: {args.through_week}")
    print(
        "Detector thresholds: "
        f"z_threshold={args.z_threshold:.3f}, "
        f"regime_effect_threshold={args.regime_effect_threshold:.3f}"
    )
    print(f"Annotations applied: {annotation_count}")
    print(f"League context: {'enabled' if args.league_context else 'disabled'}")
    if args.embed_animations:
        artifacts = report.get("artifacts", {})
        embeds = artifacts.get("embedded_animations", []) if isinstance(artifacts, dict) else []
        print(
            "Embedded animations: "
            f"{len(embeds)} (metric={args.embed_metric}, style={args.embed_style}, "
            f"interval={max(50, args.embed_interval_ms)}ms)"
        )
    print(f"Report style: {args.report_style}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
