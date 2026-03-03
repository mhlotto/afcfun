#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

from e0_inspect import load_normalized_team_rows
from e0_season_utils import parse_season_filter


@dataclass(frozen=True)
class WeeklyAveragePoint:
    week: int
    average: float
    running_points: float
    running_league_points: float
    points_efficiency: float
    matches: int
    result: str
    date: str
    opponent: str
    venue: str
    goals_for: int | None
    goals_against: int | None
    goal_diff: int | None
    shots: int | None
    shots_on_target: int | None
    corners: int | None
    fouls: int | None
    yellow_cards: int | None
    red_cards: int | None
    opponent_shots: int | None
    opponent_shots_on_target: int | None
    opponent_corners: int | None
    opponent_fouls: int | None
    opponent_yellow_cards: int | None
    opponent_red_cards: int | None


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


def _parse_match_datetime(row: dict[str, object]) -> dt.datetime:
    raw_date = str(row.get("Date", "")).strip()
    raw_time = str(row.get("Time", "")).strip()
    if not raw_date:
        raise ValueError("Missing Date in normalized match row.")
    if not raw_time:
        raw_time = "00:00"
    for fmt in ("%d/%m/%y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return dt.datetime.strptime(f"{raw_date} {raw_time}", fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Date/time value {raw_date!r} {raw_time!r} is not in expected format."
    )


def _half_win_value(result: str) -> float:
    key = result.strip().lower()
    if key == "win":
        return 1.0
    if key == "draw":
        return 0.5
    if key == "loss":
        return 0.0
    raise ValueError(f"Unexpected result value: {result!r}")


def _league_points_value(result: str) -> float:
    key = result.strip().lower()
    if key == "win":
        return 3.0
    if key == "draw":
        return 1.0
    if key == "loss":
        return 0.0
    raise ValueError(f"Unexpected result value: {result!r}")


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def build_weekly_half_win_average(
    normalized_matches: Iterable[dict[str, object]],
) -> list[WeeklyAveragePoint]:
    rows = list(normalized_matches)
    if not rows:
        return []

    sorted_rows = sorted(rows, key=_parse_match_datetime)
    points: list[WeeklyAveragePoint] = []
    running_points = 0.0
    running_league_points = 0.0
    for index, row in enumerate(sorted_rows, start=1):
        result = str(row.get("result", "")).strip().lower()
        if not result:
            raise ValueError("Normalized row is missing a result value.")
        running_points += _half_win_value(result)
        running_league_points += _league_points_value(result)
        average = running_points / index
        points_efficiency = running_league_points / (3.0 * index)
        goals_for = _as_int(row.get("total_goals"))
        goals_against = _as_int(row.get("opponent_total_goals"))
        goal_diff = None
        if goals_for is not None and goals_against is not None:
            goal_diff = goals_for - goals_against
        points.append(
            WeeklyAveragePoint(
                week=index,
                average=average,
                running_points=running_points,
                running_league_points=running_league_points,
                points_efficiency=points_efficiency,
                matches=index,
                result=result,
                date=str(row.get("Date", "")),
                opponent=str(row.get("opponent", "")),
                venue=str(row.get("venue", "")),
                goals_for=goals_for,
                goals_against=goals_against,
                goal_diff=goal_diff,
                shots=_as_int(row.get("shots")),
                shots_on_target=_as_int(row.get("shots_on_target")),
                corners=_as_int(row.get("corners")),
                fouls=_as_int(row.get("fouls")),
                yellow_cards=_as_int(row.get("yellow_cards")),
                red_cards=_as_int(row.get("red_cards")),
                opponent_shots=_as_int(row.get("opponent_shots")),
                opponent_shots_on_target=_as_int(row.get("opponent_shots_on_target")),
                opponent_corners=_as_int(row.get("opponent_corners")),
                opponent_fouls=_as_int(row.get("opponent_fouls")),
                opponent_yellow_cards=_as_int(row.get("opponent_yellow_cards")),
                opponent_red_cards=_as_int(row.get("opponent_red_cards")),
            )
        )
    return points


def parse_teams(value: str) -> list[str]:
    teams = [team.strip() for team in value.split(",") if team.strip()]
    if not teams:
        raise ValueError("Expected at least one team in --team argument.")
    unique: list[str] = []
    seen: set[str] = set()
    for team in teams:
        key = team.lower()
        if key in seen:
            continue
        unique.append(team)
        seen.add(key)
    return unique


def build_team_series(
    *,
    csv_path: str,
    teams: list[str],
    side: str,
) -> dict[str, list[WeeklyAveragePoint]]:
    series: dict[str, list[WeeklyAveragePoint]] = {}
    for team in teams:
        normalized = load_normalized_team_rows(
            source="csv",
            team=team,
            side=side,
            csv_path=csv_path,
        )
        points = build_weekly_half_win_average(normalized)
        if not points:
            raise ValueError(
                f"No matches found for team={team!r} with side={side!r}."
            )
        series[team] = points
    return series


def build_team_series_from_db(
    *,
    db_path: str,
    teams: list[str],
    side: str,
    competition_code: str = "E0",
    seasons: list[str] | None = None,
) -> dict[str, list[WeeklyAveragePoint]]:
    series: dict[str, list[WeeklyAveragePoint]] = {}
    for team in teams:
        normalized = load_normalized_team_rows(
            source="db",
            team=team,
            side=side,
            db_path=db_path,
            competition_code=competition_code,
            seasons=seasons,
        )
        points = build_weekly_half_win_average(normalized)
        if not points:
            raise ValueError(
                f"No DB matches found for team={team!r} with side={side!r}."
            )
        series[team] = points
    return series


def render_weekly_average_svg(
    points: list[WeeklyAveragePoint],
    *,
    team: str,
    out_path: Path,
) -> None:
    render_weekly_average_svg_multi({team: points}, out_path=out_path)


def render_weekly_average_svg_multi(
    series_by_team: dict[str, list[WeeklyAveragePoint]],
    *,
    out_path: Path,
) -> None:
    if not series_by_team:
        raise ValueError("No points provided for plotting.")

    width = 980
    legend_rows = len(series_by_team)
    legend_height = 50 + legend_rows * 18
    top_chart_top = 60 + legend_height
    panel_height = 240
    panel_gap = 95
    bottom_chart_top = top_chart_top + panel_height + panel_gap
    pad_bottom = 70
    height = int(bottom_chart_top + panel_height + pad_bottom)
    pad_left = 80
    pad_right = 80

    chart_w = width - pad_left - pad_right
    max_week = max(
        point.week for points in series_by_team.values() for point in points
    )
    max_points = max(
        point.running_league_points
        for points in series_by_team.values()
        for point in points
    )
    points_ticks = _points_ticks(max_points)

    def x_for(week: int) -> float:
        if max_week <= 1:
            return float(pad_left + chart_w // 2)
        return pad_left + (week - 1) * chart_w / (max_week - 1)

    def y_top(value: float) -> float:
        clamped = max(0.0, min(1.0, value))
        return top_chart_top + (1.0 - clamped) * panel_height

    def y_bottom(value: float) -> float:
        if max_points <= 0.0:
            return bottom_chart_top + panel_height
        clamped = max(0.0, min(max_points, value))
        return bottom_chart_top + (1.0 - clamped / max_points) * panel_height

    y_ticks = [0.0, 0.05] + [tick / 100.0 for tick in range(15, 100, 10)] + [1.0]
    x_ticks = _x_ticks(max_week)

    svg_parts: list[str] = []
    svg_parts.append(
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}'>"
    )
    svg_parts.append("<rect width='100%' height='100%' fill='white'/>")
    svg_parts.append(
        f"<text x='{pad_left}' y='30' font-size='22' font-family='Arial, sans-serif' "
        "font-weight='700'>Weekly Half-Win Average + Points Trends</text>"
    )
    svg_parts.append(
        f"<text x='{pad_left}' y='50' font-size='13' font-family='Arial, sans-serif' "
        "fill='#555'>Top panel: half-win running average. "
        "Bottom panel: cumulative league points.</text>"
    )

    # Style legend for top panel line meaning.
    style_y = 70
    svg_parts.append(
        f"<line x1='{pad_left}' y1='{style_y}' x2='{pad_left + 24}' y2='{style_y}' "
        "stroke='#333' stroke-width='2.5'/>"
    )
    svg_parts.append(
            f"<text x='{pad_left + 30}' y='{style_y + 4}' font-size='12' "
            "font-family='Arial, sans-serif' fill='#333'>Half-win average</text>"
        )

    legend_x = pad_left
    legend_y = 92
    for idx, team in enumerate(series_by_team):
        points = series_by_team[team]
        latest = points[-1]
        color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
        y = legend_y + idx * 18
        svg_parts.append(
            f"<line x1='{legend_x}' y1='{y}' x2='{legend_x + 18}' y2='{y}' "
            f"stroke='{color}' stroke-width='3'/>"
        )
        svg_parts.append(
            f"<text x='{legend_x + 24}' y='{y + 4}' font-size='12' "
            "font-family='Arial, sans-serif' fill='#333'>"
            f"{_escape_xml(team)}: avg={latest.average:.3f}, "
            f"pts={latest.running_league_points:.0f}"
            "</text>"
        )

    # Top panel grid and labels.
    for y_tick in y_ticks:
        y = y_top(y_tick)
        svg_parts.append(
            f"<line x1='{pad_left}' y1='{y:.2f}' x2='{pad_left + chart_w}' y2='{y:.2f}' "
            "stroke='#e3e3e3' stroke-width='1'/>"
        )
        svg_parts.append(
            f"<text x='{pad_left - 12}' y='{y + 4:.2f}' text-anchor='end' "
            "font-size='12' font-family='Arial, sans-serif' fill='#333'>"
            f"{y_tick:.2f}</text>"
        )
        svg_parts.append(
            f"<text x='{pad_left + chart_w + 12}' y='{y + 4:.2f}' text-anchor='start' "
            "font-size='12' font-family='Arial, sans-serif' fill='#333'>"
            f"{y_tick:.2f}</text>"
        )

    # Bottom panel grid and labels (cumulative points).
    for tick in points_ticks:
        y = y_bottom(tick)
        svg_parts.append(
            f"<line x1='{pad_left}' y1='{y:.2f}' x2='{pad_left + chart_w}' y2='{y:.2f}' "
            "stroke='#ededed' stroke-width='1'/>"
        )
        svg_parts.append(
            f"<text x='{pad_left - 12}' y='{y + 4:.2f}' text-anchor='end' "
            "font-size='12' font-family='Arial, sans-serif' fill='#333'>"
            f"{tick:.0f}</text>"
        )
        svg_parts.append(
            f"<text x='{pad_left + chart_w + 12}' y='{y + 4:.2f}' text-anchor='start' "
            "font-size='12' font-family='Arial, sans-serif' fill='#333'>"
            f"{tick:.0f}</text>"
        )

    # Shared vertical week guides and bottom x labels.
    for week in x_ticks:
        x = x_for(week)
        svg_parts.append(
            f"<line x1='{x:.2f}' y1='{top_chart_top}' x2='{x:.2f}' "
            f"y2='{bottom_chart_top + panel_height}' "
            "stroke='#efefef' stroke-width='1'/>"
        )
        svg_parts.append(
            f"<text x='{x:.2f}' y='{bottom_chart_top + panel_height + 24}' text-anchor='middle' "
            "font-size='12' font-family='Arial, sans-serif' fill='#333'>"
            f"W{week}</text>"
        )

    # Axes for both panels.
    svg_parts.append(
        f"<line x1='{pad_left}' y1='{top_chart_top + panel_height}' x2='{pad_left + chart_w}' "
        f"y2='{top_chart_top + panel_height}' stroke='#222' stroke-width='1.5'/>"
    )
    svg_parts.append(
        f"<line x1='{pad_left}' y1='{top_chart_top}' x2='{pad_left}' y2='{top_chart_top + panel_height}' "
        "stroke='#222' stroke-width='1.5'/>"
    )
    svg_parts.append(
        f"<line x1='{pad_left + chart_w}' y1='{top_chart_top}' x2='{pad_left + chart_w}' "
        f"y2='{top_chart_top + panel_height}' stroke='#222' stroke-width='1.5'/>"
    )
    svg_parts.append(
        f"<line x1='{pad_left}' y1='{bottom_chart_top + panel_height}' x2='{pad_left + chart_w}' "
        f"y2='{bottom_chart_top + panel_height}' stroke='#222' stroke-width='1.5'/>"
    )
    svg_parts.append(
        f"<line x1='{pad_left}' y1='{bottom_chart_top}' x2='{pad_left}' y2='{bottom_chart_top + panel_height}' "
        "stroke='#222' stroke-width='1.5'/>"
    )
    svg_parts.append(
        f"<line x1='{pad_left + chart_w}' y1='{bottom_chart_top}' x2='{pad_left + chart_w}' "
        f"y2='{bottom_chart_top + panel_height}' "
        "stroke='#222' stroke-width='1.5'/>"
    )

    # Panel labels.
    svg_parts.append(
        f"<text x='{pad_left}' y='{top_chart_top - 10}' font-size='13' "
        "font-family='Arial, sans-serif' fill='#444'>Half-win running average (0..1)</text>"
    )
    svg_parts.append(
        f"<text x='{pad_left}' y='{bottom_chart_top - 10}' font-size='13' "
        "font-family='Arial, sans-serif' fill='#444'>Cumulative points (3/1/0)</text>"
    )

    # Draw lines.
    for idx, team in enumerate(series_by_team):
        points = series_by_team[team]
        color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
        top_avg = " ".join(
            f"{x_for(point.week):.2f},{y_top(point.average):.2f}" for point in points
        )
        bottom_pts = " ".join(
            f"{x_for(point.week):.2f},{y_bottom(point.running_league_points):.2f}"
            for point in points
        )
        svg_parts.append(
            f"<polyline points='{top_avg}' fill='none' stroke='{color}' "
            "stroke-width='2.4'/>"
        )
        svg_parts.append(
            f"<polyline points='{bottom_pts}' fill='none' stroke='{color}' "
            "stroke-width='2.4'/>"
        )
        for point in points:
            x = x_for(point.week)
            y = y_top(point.average)
            svg_parts.append(
                f"<circle cx='{x:.2f}' cy='{y:.2f}' r='2.4' fill='{color}'/>"
            )
            yb = y_bottom(point.running_league_points)
            svg_parts.append(
                f"<circle cx='{x:.2f}' cy='{yb:.2f}' r='2.2' fill='{color}'/>"
            )
    svg_parts.append("</svg>")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(svg_parts), encoding="utf-8")


def _x_ticks(max_week: int) -> list[int]:
    if max_week <= 10:
        return list(range(1, max_week + 1))
    step = max(1, max_week // 10)
    ticks = list(range(1, max_week + 1, step))
    if ticks[-1] != max_week:
        ticks.append(max_week)
    return ticks


def _points_ticks(max_points: float) -> list[float]:
    if max_points <= 0:
        return [0.0]
    step = max(1, int(math.ceil(max_points / 10.0)))
    upper = int(math.ceil(max_points / step) * step)
    return [float(value) for value in range(0, upper + 1, step)]


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plot week-by-week running half-win average and cumulative points "
            "(top: average, bottom: cumulative points)."
        )
    )
    parser.add_argument(
        "--csv",
        default="data/football-data.co.uk/E0.csv",
        help="Path to E0.csv",
    )
    parser.add_argument(
        "--source",
        default="csv",
        choices=["csv", "db"],
        help="Input source mode.",
    )
    parser.add_argument(
        "--db",
        default="data/footstat.sqlite3",
        help="SQLite file path for --source db.",
    )
    parser.add_argument(
        "--competition",
        default="E0",
        help="Competition code for --source db.",
    )
    parser.add_argument(
        "--seasons",
        default=None,
        help="Optional season filters for --source db (YYYY-YYYY or YYYYYYYY, comma-delimited).",
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
        "--out",
        default="docs/arsenal_weekly_halfwin_average.svg",
        help="Output SVG path.",
    )
    args = parser.parse_args()

    teams = parse_teams(args.team)
    if args.source == "db":
        season_filter = parse_season_filter(args.seasons)
        series = build_team_series_from_db(
            db_path=args.db,
            teams=teams,
            side=args.side,
            competition_code=args.competition,
            seasons=season_filter,
        )
    else:
        series = build_team_series(csv_path=args.csv, teams=teams, side=args.side)
    render_weekly_average_svg_multi(series, out_path=Path(args.out))

    print(f"Wrote {args.out}")
    print(f"Source: {args.source}")
    for team in teams:
        latest = series[team][-1]
        print(
            f"{team}: avg={latest.average:.4f}, "
            f"points={latest.running_league_points:.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
