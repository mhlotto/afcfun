#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

from e0_multi_season import build_multi_season_series, parse_season_filter
from e0_weekly_halfwin_animate import write_animation_html
from e0_weekly_halfwin_plot import WeeklyAveragePoint, parse_teams


_SERIES_COLORS = [
    "#0b6dfa",
    "#e65100",
    "#2e7d32",
    "#8e24aa",
    "#c62828",
    "#00838f",
    "#6d4c41",
    "#5d4037",
    "#3949ab",
    "#7cb342",
]

_SERIES_COLORS_CINEMATIC = [
    "#245c9f",
    "#c4681c",
    "#2a8559",
    "#b0432d",
    "#4556a8",
    "#19808f",
    "#7f5139",
    "#6e7d23",
    "#6f4f97",
    "#5a7ea2",
]


def _points_ticks(max_points: float) -> list[float]:
    if max_points <= 0:
        return [0.0]
    step = max(1, int(math.ceil(max_points / 10.0)))
    upper = int(math.ceil(max_points / step) * step)
    return [float(value) for value in range(0, upper + 1, step)]


def _point_summary(point: WeeklyAveragePoint) -> dict[str, object]:
    return {
        "date": point.date,
        "opponent": point.opponent,
        "venue": point.venue,
        "result": point.result,
        "goals_for": point.goals_for,
        "goals_against": point.goals_against,
        "goal_diff": point.goal_diff,
        "shots": point.shots,
        "shots_on_target": point.shots_on_target,
        "corners": point.corners,
        "fouls": point.fouls,
        "yellow_cards": point.yellow_cards,
        "red_cards": point.red_cards,
        "opponent_shots": point.opponent_shots,
        "opponent_shots_on_target": point.opponent_shots_on_target,
        "opponent_corners": point.opponent_corners,
        "opponent_fouls": point.opponent_fouls,
        "opponent_yellow_cards": point.opponent_yellow_cards,
        "opponent_red_cards": point.opponent_red_cards,
    }


def _build_payload(
    series: dict[str, list[WeeklyAveragePoint]],
    *,
    style: str,
) -> dict[str, object]:
    palette = _SERIES_COLORS_CINEMATIC if style == "cinematic" else _SERIES_COLORS
    payload_teams: list[dict[str, object]] = []
    max_week = 0
    max_points = 0.0
    for index, (series_name, points) in enumerate(series.items()):
        if not points:
            continue
        max_week = max(max_week, len(points))
        max_points = max(max_points, points[-1].running_league_points)
        payload_teams.append(
            {
                "name": series_name,
                "color": palette[index % len(palette)],
                "points": [
                    {
                        "week": point.week,
                        "average": point.average,
                        "running_points": point.running_league_points,
                        "summary": _point_summary(point),
                        "media": None,
                    }
                    for point in points
                ],
            }
        )

    if not payload_teams:
        raise ValueError("No series available for animation payload.")

    return {
        "teams": payload_teams,
        "max_week": max_week,
        "max_points": max_points,
        "y_ticks_top": [0.0, 0.05]
        + [tick / 100.0 for tick in range(15, 100, 10)]
        + [1.0],
        "y_ticks_bottom": _points_ticks(max_points),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate animated week-by-week half-win average and cumulative points "
            "across multiple seasons."
        )
    )
    parser.add_argument(
        "--data-dir",
        default="data/football-data.co.uk",
        help="Directory containing E0.csv and E0-YYYYYYYY.csv files.",
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
        help="Optional comma-delimited seasons (YYYY-YYYY or YYYYYYYY).",
    )
    parser.add_argument(
        "--include-current",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include data-dir/E0.csv in addition to E0-YYYYYYYY.csv files.",
    )
    parser.add_argument(
        "--current-label",
        default=None,
        help="Optional override label for E0.csv season (e.g., 2025-2026).",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=500,
        help="Animation interval in milliseconds between weeks.",
    )
    parser.add_argument(
        "--trail-glow",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable glow on the currently drawing segment.",
    )
    parser.add_argument(
        "--style",
        default="classic",
        choices=["classic", "cinematic"],
        help="Visual style preset.",
    )
    parser.add_argument(
        "--out",
        default="docs/e0_multi_season_weekly_halfwin_animated.html",
        help="Output HTML path.",
    )
    args = parser.parse_args()

    teams = parse_teams(args.team)
    season_filter = parse_season_filter(args.seasons)
    series, sources = build_multi_season_series(
        data_dir=args.data_dir,
        teams=teams,
        side=args.side,
        seasons=season_filter,
        include_current=args.include_current,
        current_label=args.current_label,
    )

    payload = _build_payload(series, style=args.style)
    title = " / ".join(teams) + ": Multi-Season Weekly Half-Win + Cumulative Points"
    write_animation_html(
        out_path=Path(args.out),
        payload=payload,
        interval_ms=max(50, args.interval_ms),
        title=title,
        trail_glow=args.trail_glow,
        style=args.style,
    )

    selected_labels = sorted({source.label for source in sources})
    print(f"Wrote {args.out}")
    print(f"Teams: {', '.join(teams)}")
    print(f"Seasons discovered: {', '.join(selected_labels)}")
    print(f"Series plotted: {len(series)}")
    print(f"Interval: {max(50, args.interval_ms)}ms per week")
    print(f"Trail glow: {'on' if args.trail_glow else 'off'}")
    print(f"Style: {args.style}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
