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
from e0_weekly_halfwin_plot import parse_teams


@dataclass(frozen=True)
class WeeklyMetricPoint:
    week: int
    value: float | None
    date: str
    opponent: str
    venue: str
    result: str


_SERIES_COLORS = [
    "#0b6dfa",
    "#e65100",
    "#2e7d32",
    "#8e24aa",
    "#c62828",
    "#00838f",
    "#6d4c41",
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


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def build_weekly_metric_series(
    normalized_matches: Iterable[dict[str, object]],
    *,
    metric: str,
) -> list[WeeklyMetricPoint]:
    rows = list(normalized_matches)
    if not rows:
        return []

    sorted_rows = sorted(rows, key=_parse_match_datetime)
    points: list[WeeklyMetricPoint] = []
    for index, row in enumerate(sorted_rows, start=1):
        points.append(
            WeeklyMetricPoint(
                week=index,
                value=_as_float(row.get(metric)),
                date=str(row.get("Date", "")),
                opponent=str(row.get("opponent", "")),
                venue=str(row.get("venue", "")),
                result=str(row.get("result", "")),
            )
        )
    return points


def build_team_metric_series(
    *,
    source: str,
    teams: list[str],
    side: str,
    metric: str,
    csv_path: str,
    db_path: str,
    competition_code: str,
    seasons: list[str] | None,
) -> dict[str, list[WeeklyMetricPoint]]:
    series: dict[str, list[WeeklyMetricPoint]] = {}
    for team in teams:
        normalized = load_normalized_team_rows(
            source=source,
            team=team,
            side=side,
            csv_path=csv_path,
            db_path=db_path,
            competition_code=competition_code,
            seasons=seasons,
        )
        points = build_weekly_metric_series(normalized, metric=metric)
        if not points:
            raise ValueError(
                f"No matches found for team={team!r} with side={side!r}."
            )
        series[team] = points
    return series


def build_db_multi_season_metric_series(
    *,
    teams: list[str],
    side: str,
    metric: str,
    db_path: str,
    competition_code: str,
    seasons: Iterable[str] | None = None,
    source_scope: str = "",
) -> tuple[dict[str, list[WeeklyMetricPoint]], list[str]]:
    series: dict[str, list[WeeklyMetricPoint]] = {}
    all_seasons: set[str] = set()

    for team in teams:
        rows = load_normalized_team_rows(
            source="db",
            team=team,
            side=side,
            db_path=db_path,
            competition_code=competition_code,
            seasons=seasons,
            source_scope=source_scope,
        )
        by_season: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            season = str(row.get("season", "")).strip()
            if not season:
                continue
            by_season.setdefault(season, []).append(row)

        season_order = [label for label in (seasons or []) if label in by_season]
        if not season_order:
            season_order = sorted(by_season.keys())
        for season in season_order:
            points = build_weekly_metric_series(by_season[season], metric=metric)
            if not points:
                continue
            key = f"{team} ({season})"
            series[key] = points
            all_seasons.add(season)

    if not series:
        raise ValueError(
            "No matching rows found for the requested team/season selection."
        )

    if seasons is not None:
        labels = [label for label in seasons if label in all_seasons]
    else:
        labels = sorted(all_seasons)
    return series, labels


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _x_ticks(max_week: int) -> list[int]:
    if max_week <= 10:
        return list(range(1, max_week + 1))
    step = max(1, max_week // 10)
    ticks = list(range(1, max_week + 1, step))
    if ticks[-1] != max_week:
        ticks.append(max_week)
    return ticks


def _linear_ticks(min_value: float, max_value: float, count: int = 6) -> list[float]:
    if count < 2:
        return [min_value]
    if math.isclose(min_value, max_value):
        return [min_value + float(i) for i in range(count)]
    step = (max_value - min_value) / float(count - 1)
    return [min_value + step * i for i in range(count)]


def _is_integer_like(value: float, *, tol: float = 1e-9) -> bool:
    return math.isclose(value, round(value), abs_tol=tol)


def _integer_ticks(min_value: float, max_value: float, *, count: int = 7) -> list[float]:
    low = int(math.floor(min_value))
    high = int(math.ceil(max_value))
    if low == high:
        return [float(low)]
    span = high - low
    if count < 2:
        return [float(low), float(high)]
    step = max(1, math.ceil(span / float(count - 1)))
    ticks = [float(value) for value in range(low, high + 1, step)]
    if ticks[-1] != float(high):
        ticks.append(float(high))
    return ticks


def _format_tick_label(value: float, *, as_integer: bool) -> str:
    if as_integer:
        return str(int(round(value)))
    return f"{value:.2f}"


def build_metric_axis(
    values: list[float],
) -> tuple[float, float, list[float], list[str], bool]:
    if not values:
        y_min = 0.0
        y_max = 1.0
        y_ticks = _linear_ticks(y_min, y_max, count=6)
        y_labels = [f"{tick:.2f}" for tick in y_ticks]
        return y_min, y_max, y_ticks, y_labels, False

    ints_only = all(_is_integer_like(value) for value in values)
    data_min = min(values)
    data_max = max(values)
    if ints_only:
        low = int(math.floor(data_min))
        high = int(math.ceil(data_max))
        if low == high:
            low -= 1
            high += 1
        y_min = float(low) - 0.5
        y_max = float(high) + 0.5
        y_ticks = _integer_ticks(float(low), float(high), count=7)
        y_labels = [_format_tick_label(tick, as_integer=True) for tick in y_ticks]
        return y_min, y_max, y_ticks, y_labels, True

    y_min = data_min
    y_max = data_max
    if math.isclose(y_min, y_max):
        delta = 1.0 if math.isclose(y_min, 0.0) else abs(y_min) * 0.1
        y_min -= delta
        y_max += delta
    else:
        margin = (y_max - y_min) * 0.08
        y_min -= margin
        y_max += margin
    y_ticks = _linear_ticks(y_min, y_max, count=7)
    y_labels = [_format_tick_label(tick, as_integer=False) for tick in y_ticks]
    return y_min, y_max, y_ticks, y_labels, False


def render_weekly_metric_svg_multi(
    series_by_team: dict[str, list[WeeklyMetricPoint]],
    *,
    metric: str,
    out_path: Path,
    title: str | None = None,
) -> None:
    if not series_by_team:
        raise ValueError("No points provided for plotting.")

    width = 980
    legend_rows = len(series_by_team)
    legend_height = 56 + legend_rows * 18
    chart_top = 76 + legend_height
    panel_height = 340
    pad_bottom = 74
    height = int(chart_top + panel_height + pad_bottom)
    pad_left = 80
    pad_right = 80
    chart_w = width - pad_left - pad_right
    max_week = max(point.week for points in series_by_team.values() for point in points)
    x_ticks = _x_ticks(max_week)

    all_values = [
        point.value
        for points in series_by_team.values()
        for point in points
        if point.value is not None
    ]
    has_values = bool(all_values)
    y_min, y_max, y_ticks, y_tick_labels, _ = build_metric_axis(all_values)

    def x_for(week: int) -> float:
        if max_week <= 1:
            return float(pad_left + chart_w // 2)
        return pad_left + (week - 1) * chart_w / (max_week - 1)

    def y_for(value: float) -> float:
        ratio = (value - y_min) / (y_max - y_min)
        return chart_top + (1.0 - ratio) * panel_height

    label = title or f"Weekly {metric}"
    svg_parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect x='0' y='0' width='100%' height='100%' fill='#f8fbff'/>",
        (
            f"<text x='{pad_left}' y='38' font-size='24' font-family='Arial, sans-serif' "
            f"fill='#13293d' font-weight='700'>{_escape_xml(label)}</text>"
        ),
        (
            f"<text x='{pad_left}' y='58' font-size='13' font-family='Arial, sans-serif' "
            f"fill='#4b6783'>Metric: {_escape_xml(metric)}</text>"
        ),
        (
            f"<rect x='{pad_left}' y='{chart_top}' width='{chart_w}' height='{panel_height}' "
            "fill='#ffffff' stroke='#d9e4f0' stroke-width='1'/>"
        ),
    ]

    legend_y = 80
    for idx, (team, points) in enumerate(series_by_team.items()):
        color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
        latest = next((point.value for point in reversed(points) if point.value is not None), None)
        latest_text = "n/a" if latest is None else f"{latest:.2f}"
        svg_parts.append(
            f"<line x1='{pad_left}' y1='{legend_y}' x2='{pad_left + 18}' y2='{legend_y}' "
            f"stroke='{color}' stroke-width='3'/>"
        )
        svg_parts.append(
            f"<text x='{pad_left + 24}' y='{legend_y + 4}' font-size='12' "
            f"font-family='Arial, sans-serif' fill='#2c4661'>"
            f"{_escape_xml(team)}: latest={_escape_xml(latest_text)}</text>"
        )
        legend_y += 18

    for index, tick in enumerate(y_ticks):
        y = y_for(tick)
        label = y_tick_labels[index]
        svg_parts.append(
            f"<line x1='{pad_left}' y1='{y:.2f}' x2='{pad_left + chart_w}' y2='{y:.2f}' "
            "stroke='#e4edf6' stroke-width='1'/>"
        )
        svg_parts.append(
            f"<text x='{pad_left - 14}' y='{y + 4:.2f}' text-anchor='end' "
            "font-size='12' font-family='Arial, sans-serif' fill='#415f7c'>"
            f"{_escape_xml(label)}</text>"
        )
        svg_parts.append(
            f"<text x='{pad_left + chart_w + 14}' y='{y + 4:.2f}' text-anchor='start' "
            "font-size='12' font-family='Arial, sans-serif' fill='#415f7c'>"
            f"{_escape_xml(label)}</text>"
        )

    for week in x_ticks:
        x = x_for(week)
        svg_parts.append(
            f"<line x1='{x:.2f}' y1='{chart_top}' x2='{x:.2f}' y2='{chart_top + panel_height}' "
            "stroke='#eef2f7' stroke-width='1'/>"
        )
        svg_parts.append(
            f"<text x='{x:.2f}' y='{chart_top + panel_height + 24}' text-anchor='middle' "
            "font-size='12' font-family='Arial, sans-serif' fill='#415f7c'>"
            f"W{week}</text>"
        )

    svg_parts.append(
        f"<line x1='{pad_left}' y1='{chart_top + panel_height}' x2='{pad_left + chart_w}' "
        f"y2='{chart_top + panel_height}' stroke='#222' stroke-width='1.4'/>"
    )
    svg_parts.append(
        f"<line x1='{pad_left}' y1='{chart_top}' x2='{pad_left}' y2='{chart_top + panel_height}' "
        "stroke='#222' stroke-width='1.4'/>"
    )
    svg_parts.append(
        f"<line x1='{pad_left + chart_w}' y1='{chart_top}' x2='{pad_left + chart_w}' "
        f"y2='{chart_top + panel_height}' stroke='#222' stroke-width='1.4'/>"
    )

    if has_values:
        for idx, (_team, points) in enumerate(series_by_team.items()):
            color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
            segment: list[str] = []
            for point in points:
                if point.value is None:
                    if len(segment) >= 2:
                        svg_parts.append(
                            f"<polyline points='{' '.join(segment)}' fill='none' stroke='{color}' "
                            "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/>"
                        )
                    segment = []
                    continue
                x = x_for(point.week)
                y = y_for(point.value)
                segment.append(f"{x:.2f},{y:.2f}")
                svg_parts.append(
                    f"<circle cx='{x:.2f}' cy='{y:.2f}' r='2.8' fill='{color}'/>"
                )
            if len(segment) >= 2:
                svg_parts.append(
                    f"<polyline points='{' '.join(segment)}' fill='none' stroke='{color}' "
                    "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/>"
                )
    else:
        svg_parts.append(
            f"<text x='{pad_left + chart_w / 2:.2f}' y='{chart_top + panel_height / 2:.2f}' "
            "text-anchor='middle' font-size='15' font-family='Arial, sans-serif' "
            "fill='#8a5a2b'>No non-missing values for selected metric.</text>"
        )

    svg_parts.append("</svg>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(svg_parts), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plot a weekly line chart for a selected normalized team metric."
    )
    parser.add_argument(
        "--source",
        default="csv",
        choices=["csv", "db", "db-multi"],
        help="Input source mode.",
    )
    parser.add_argument(
        "--csv",
        default="data/football-data.co.uk/E0.csv",
        help="Path to E0.csv for --source csv.",
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
        help="Optional season filters for --source db/db-multi (YYYY-YYYY or YYYYYYYY, comma-delimited).",
    )
    parser.add_argument(
        "--team",
        default="Arsenal",
        help="Team name(s), comma-delimited for multiple teams.",
    )
    parser.add_argument(
        "--side",
        default="both",
        choices=["home", "away", "both"],
        help="Filter matches by venue.",
    )
    parser.add_argument(
        "--metric",
        default="opponent_fouls",
        help="Normalized metric field to plot.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional chart title override.",
    )
    parser.add_argument(
        "--out",
        default="docs/weekly_opponent_fouls.svg",
        help="Output SVG path.",
    )
    args = parser.parse_args()

    teams = parse_teams(args.team)
    season_filter = parse_season_filter(args.seasons)
    if args.source == "db-multi":
        series, season_labels = build_db_multi_season_metric_series(
            teams=teams,
            side=args.side,
            metric=args.metric,
            db_path=args.db,
            competition_code=args.competition,
            seasons=season_filter,
        )
    else:
        series = build_team_metric_series(
            source=args.source,
            teams=teams,
            side=args.side,
            metric=args.metric,
            csv_path=args.csv,
            db_path=args.db,
            competition_code=args.competition,
            seasons=season_filter,
        )
        season_labels = []
    render_weekly_metric_svg_multi(
        series,
        metric=args.metric,
        out_path=Path(args.out),
        title=args.title,
    )

    print(f"Wrote {args.out}")
    print(f"Source: {args.source}")
    print(f"Metric: {args.metric}")
    if args.source == "db-multi":
        print(f"Seasons discovered: {', '.join(season_labels)}")
        print(f"Series plotted: {len(series)}")
    for team in teams:
        matching_keys = [
            key for key in series.keys() if key == team or key.startswith(f"{team} (")
        ]
        for key in matching_keys:
            values = [point.value for point in series[key] if point.value is not None]
            last = "n/a" if not values else f"{values[-1]:.2f}"
            print(
                f"{key}: weeks={len(series[key])}, "
                f"non_missing={len(values)}, latest={last}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
