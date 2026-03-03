#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from e0_multi_season import build_multi_season_series, parse_season_filter
from e0_weekly_halfwin_plot import parse_teams, render_weekly_average_svg_multi


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plot week-by-week half-win average and cumulative points across "
            "multiple seasons on one SVG."
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
        help="Team name(s) to analyze. Use comma delimiters for multiple teams.",
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
        "--out",
        default="docs/e0_multi_season_weekly_halfwin.svg",
        help="Output SVG path.",
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

    render_weekly_average_svg_multi(series, out_path=Path(args.out))

    selected_labels = sorted({source.label for source in sources})
    print(f"Wrote {args.out}")
    print(f"Teams: {', '.join(teams)}")
    print(f"Seasons discovered: {', '.join(selected_labels)}")
    print(f"Series plotted: {len(series)}")
    for key, points in series.items():
        latest = points[-1]
        print(
            f"{key}: avg={latest.average:.4f}, "
            f"points={latest.running_league_points:.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

