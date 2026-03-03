#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Iterable

from e0_inspect import load_normalized_team_rows
from e0_season_utils import parse_season_filter
from e0_weekly_halfwin_plot import build_weekly_half_win_average, parse_teams
from e0_weekly_metric_plot import build_weekly_metric_series
from e0_weekly_report_annotations import (
    apply_weekly_annotations,
    load_weekly_annotations,
)
from e0_weekly_report_schema import assert_valid_weekly_report_schema
from footstat_db import initialize_db
from footstat_repo import FootstatRepo


REPORT_SCHEMA_VERSION = "weekly-report.v1"
REPORT_TOOL_VERSION = "0.1.0"
DEFAULT_METRICS = [
    "shots",
    "shots_on_target",
    "corners",
    "fouls",
    "opponent_shots",
    "opponent_shots_on_target",
    "opponent_corners",
    "opponent_fouls",
]


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
    out = "".join(chars).strip("-")
    return out or "value"


def default_report_basename(
    *,
    teams: list[str],
    seasons: list[str],
    report_date: str,
    through_week: int | None = None,
) -> str:
    team_slug = "-".join(_slug(team) for team in teams)[:64]
    season_slug = "all" if not seasons else "-".join(season.replace("-", "") for season in seasons)
    through_suffix = f"-through-w{through_week}" if through_week is not None else ""
    return f"weekly-report-{team_slug}-{season_slug}{through_suffix}-{report_date}"


def default_report_json_path(
    *,
    teams: list[str],
    seasons: list[str],
    report_date: str,
    through_week: int | None = None,
) -> Path:
    return (
        Path("docs/reports")
        / f"{default_report_basename(teams=teams, seasons=seasons, report_date=report_date, through_week=through_week)}.json"
    )


def _parse_match_datetime(row: dict[str, object]) -> dt.datetime:
    raw_date = str(row.get("Date", "")).strip()
    raw_time = str(row.get("Time", "")).strip() or "00:00"
    if not raw_date:
        return dt.datetime(1970, 1, 1)
    for fmt in ("%d/%m/%y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(f"{raw_date} {raw_time}", fmt)
        except ValueError:
            continue
    return dt.datetime(1970, 1, 1)


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _result_points(result: str) -> float:
    key = result.strip().lower()
    if key == "win":
        return 3.0
    if key == "draw":
        return 1.0
    if key == "loss":
        return 0.0
    return 0.0


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = 0.0
    den_x = 0.0
    den_y = 0.0
    for x, y in zip(xs, ys):
        dx = x - mean_x
        dy = y - mean_y
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy
    den = math.sqrt(den_x * den_y)
    if den == 0.0:
        return None
    return num / den


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _stdev_population(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = _mean(values)
    if avg is None:
        return None
    var = sum((value - avg) * (value - avg) for value in values) / len(values)
    return math.sqrt(var)


def _pooled_std(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    mean_a = _mean(a)
    mean_b = _mean(b)
    if mean_a is None or mean_b is None:
        return None
    var_a = sum((value - mean_a) * (value - mean_a) for value in a) / (len(a) - 1)
    var_b = sum((value - mean_b) * (value - mean_b) for value in b) / (len(b) - 1)
    denom = (len(a) - 1) + (len(b) - 1)
    if denom <= 0:
        return None
    pooled_var = (((len(a) - 1) * var_a) + ((len(b) - 1) * var_b)) / denom
    if pooled_var <= 0.0:
        return None
    return math.sqrt(pooled_var)


def detect_referee_fingerprint(
    *,
    team: str,
    season: str,
    weekly_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in weekly_rows:
        referee = str(row.get("referee", "")).strip()
        if not referee:
            continue
        grouped.setdefault(referee, []).append(row)
    if not grouped:
        return []

    overall_ppm = sum(_result_points(str(row.get("result", ""))) for row in weekly_rows) / max(
        len(weekly_rows), 1
    )
    scored: list[tuple[float, str, dict[str, object]]] = []
    for referee, rows in grouped.items():
        if len(rows) < 2:
            continue
        ppm = sum(_result_points(str(row.get("result", ""))) for row in rows) / len(rows)
        delta = ppm - overall_ppm
        scored.append(
            (
                abs(delta),
                referee,
                {
                    "referee": referee,
                    "matches": len(rows),
                    "points_per_match": round(ppm, 4),
                    "overall_points_per_match": round(overall_ppm, 4),
                    "delta_points_per_match": round(delta, 4),
                },
            )
        )
    scored.sort(reverse=True, key=lambda item: item[0])
    findings: list[dict[str, object]] = []
    for _, referee, evidence in scored[:3]:
        if abs(float(evidence["delta_points_per_match"])) < 0.45:
            continue
        findings.append(
            {
                "kind": "referee_fingerprint",
                "season": season,
                "team": team,
                "severity": "info",
                "title": f"Referee split: {referee}",
                "summary": (
                    f"{referee} has a {evidence['delta_points_per_match']:+.2f} "
                    "points-per-match delta vs team baseline."
                ),
                "evidence": evidence,
                "weeks": [],
            }
        )
    return findings


def detect_discipline_tax(
    *,
    team: str,
    season: str,
    weekly_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    xs: list[float] = []
    ys: list[float] = []
    for row in weekly_rows:
        bookings = _as_float(row.get("bookings_points"))
        if bookings is None:
            continue
        xs.append(bookings)
        ys.append(_result_points(str(row.get("result", ""))))
    corr = _pearson(xs, ys)
    if corr is None or abs(corr) < 0.25:
        return []
    direction = "higher bookings linked to fewer points" if corr < 0 else "higher bookings linked to more points"
    return [
        {
            "kind": "discipline_tax",
            "season": season,
            "team": team,
            "severity": "warning" if corr < 0 else "info",
            "title": "Discipline/points link",
            "summary": f"Pearson r={corr:.3f}; {direction}.",
            "evidence": {
                "pearson_r": round(corr, 4),
                "n": len(xs),
                "bookings_points_mean": round(sum(xs) / len(xs), 4),
                "points_mean": round(sum(ys) / len(ys), 4),
            },
            "weeks": [],
        }
    ]


def detect_control_without_result(
    *,
    team: str,
    season: str,
    weekly_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    misses: list[dict[str, object]] = []
    for row in weekly_rows:
        shots = _as_float(row.get("shots"))
        opp_shots = _as_float(row.get("opponent_shots"))
        sot = _as_float(row.get("shots_on_target"))
        opp_sot = _as_float(row.get("opponent_shots_on_target"))
        if shots is None or opp_shots is None or sot is None or opp_sot is None:
            continue
        shot_diff = shots - opp_shots
        sot_diff = sot - opp_sot
        if shot_diff >= 5.0 and sot_diff >= 2.0 and str(row.get("result", "")) != "win":
            misses.append(
                {
                    "week": row.get("week"),
                    "date": row.get("date"),
                    "opponent": row.get("opponent"),
                    "result": row.get("result"),
                    "shot_diff": int(shot_diff),
                    "sot_diff": int(sot_diff),
                }
            )
    if not misses:
        return []
    return [
        {
            "kind": "control_without_result",
            "season": season,
            "team": team,
            "severity": "warning",
            "title": "Control without result",
            "summary": (
                f"{len(misses)} matches had strong shot control "
                "(shots>=+5 and on-target>=+2) but no win."
            ),
            "evidence": {
                "matches": len(misses),
                "examples": misses[:5],
            },
            "weeks": [int(item["week"]) for item in misses if item.get("week") is not None],
        }
    ]


def detect_streak_fragility(
    *,
    team: str,
    season: str,
    weekly_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if len(weekly_rows) < 4:
        return []
    events: list[dict[str, object]] = []
    i = 0
    while i < len(weekly_rows):
        if str(weekly_rows[i].get("result", "")) != "win":
            i += 1
            continue
        start = i
        while i + 1 < len(weekly_rows) and str(weekly_rows[i + 1].get("result", "")) == "win":
            i += 1
        end = i
        streak_len = end - start + 1
        next_idx = end + 1
        if streak_len >= 3 and next_idx < len(weekly_rows):
            next_row = weekly_rows[next_idx]
            if str(next_row.get("result", "")) != "win":
                streak_sot = [
                    _as_float(row.get("shots_on_target"))
                    for row in weekly_rows[start : end + 1]
                ]
                streak_sot = [value for value in streak_sot if value is not None]
                next_sot = _as_float(next_row.get("shots_on_target"))
                if streak_sot and next_sot is not None:
                    avg_sot = sum(streak_sot) / len(streak_sot)
                    drop = avg_sot - next_sot
                    if drop >= 2.0:
                        events.append(
                            {
                                "streak_start_week": int(weekly_rows[start]["week"]),
                                "streak_end_week": int(weekly_rows[end]["week"]),
                                "post_week": int(next_row["week"]),
                                "post_result": str(next_row.get("result", "")),
                                "avg_sot_in_streak": round(avg_sot, 3),
                                "post_sot": round(next_sot, 3),
                                "drop": round(drop, 3),
                            }
                        )
        i += 1
    if not events:
        return []
    best = max(events, key=lambda item: float(item["drop"]))
    return [
        {
            "kind": "streak_fragility",
            "season": season,
            "team": team,
            "severity": "info",
            "title": "Streak fragility signal",
            "summary": (
                f"Largest post-streak on-target drop is {best['drop']:.2f} "
                f"after a win streak ending week {best['streak_end_week']}."
            ),
            "evidence": {"events": events[:5]},
            "weeks": [int(best["post_week"])],
        }
    ]


def detect_metric_outliers_zscore(
    *,
    team: str,
    season: str,
    weekly_rows: list[dict[str, object]],
    metric_series: dict[str, list[float | None]],
    z_threshold: float = 2.0,
) -> list[dict[str, object]]:
    outliers: list[dict[str, object]] = []
    for metric, values in metric_series.items():
        indexed = [
            (idx, value)
            for idx, value in enumerate(values)
            if value is not None and not math.isnan(float(value))
        ]
        numeric = [float(value) for _, value in indexed]
        mean = _mean(numeric)
        stdev = _stdev_population(numeric)
        if mean is None or stdev is None or stdev <= 0.0:
            continue
        for idx, value in indexed:
            z = (float(value) - mean) / stdev
            if abs(z) < z_threshold:
                continue
            week_row = weekly_rows[idx] if idx < len(weekly_rows) else {}
            outliers.append(
                {
                    "metric": metric,
                    "week": week_row.get("week"),
                    "date": week_row.get("date"),
                    "opponent": week_row.get("opponent"),
                    "value": round(float(value), 4),
                    "z_score": round(z, 4),
                    "mean": round(mean, 4),
                    "stdev": round(stdev, 4),
                }
            )
    if not outliers:
        return []
    outliers.sort(key=lambda row: abs(float(row["z_score"])), reverse=True)
    top = outliers[:10]
    weeks = sorted(
        {
            int(item["week"])
            for item in top
            if item.get("week") is not None
        }
    )
    return [
        {
            "kind": "metric_outlier_zscore",
            "season": season,
            "team": team,
            "severity": "info",
            "title": "Metric outlier weeks",
            "summary": (
                f"{len(outliers)} z-score outliers found at |z| >= {z_threshold:.1f}; "
                f"top outlier {top[0]['metric']} week {top[0].get('week')} "
                f"(z={top[0]['z_score']:+.2f})."
            ),
            "evidence": {
                "threshold": z_threshold,
                "count": len(outliers),
                "top_outliers": top,
            },
            "weeks": weeks,
        }
    ]


def detect_regime_shift(
    *,
    team: str,
    season: str,
    metric_series: dict[str, list[float | None]],
    effect_threshold: float = 0.8,
) -> list[dict[str, object]]:
    shifts: list[dict[str, object]] = []
    for metric, values in metric_series.items():
        numeric = [float(value) for value in values if value is not None]
        if len(numeric) < 8:
            continue
        mid = len(numeric) // 2
        left = numeric[:mid]
        right = numeric[mid:]
        if len(left) < 3 or len(right) < 3:
            continue
        mean_left = _mean(left)
        mean_right = _mean(right)
        pooled = _pooled_std(left, right)
        if mean_left is None or mean_right is None or pooled is None:
            continue
        effect = (mean_right - mean_left) / pooled
        if abs(effect) < effect_threshold:
            continue
        shifts.append(
            {
                "metric": metric,
                "first_half_mean": round(mean_left, 4),
                "second_half_mean": round(mean_right, 4),
                "effect_size_d": round(effect, 4),
                "sample_left": len(left),
                "sample_right": len(right),
            }
        )
    if not shifts:
        return []
    shifts.sort(key=lambda row: abs(float(row["effect_size_d"])), reverse=True)
    top = shifts[:5]
    lead = top[0]
    direction = "up" if float(lead["effect_size_d"]) > 0 else "down"
    return [
        {
            "kind": "regime_shift",
            "season": season,
            "team": team,
            "severity": "info",
            "title": "Regime shift signal",
            "summary": (
                f"Strongest split-half shift: {lead['metric']} {direction} "
                f"(d={lead['effect_size_d']:+.2f})."
            ),
            "evidence": {
                "threshold": effect_threshold,
                "count": len(shifts),
                "top_shifts": top,
            },
            "weeks": [],
        }
    ]


def _resolve_default_seasons(
    *,
    db_path: str,
    competition_code: str,
) -> list[str]:
    conn = initialize_db(db_path)
    try:
        repo = FootstatRepo(conn)
        seasons = repo.list_seasons(competition_code=competition_code)
    finally:
        conn.close()
    if not seasons:
        raise ValueError(
            f"No seasons found in DB for competition={competition_code!r}."
        )
    return [str(seasons[-1]["label"])]


def _parse_metrics(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_METRICS)
    metrics = [part.strip() for part in value.split(",") if part.strip()]
    if not metrics:
        return list(DEFAULT_METRICS)
    seen: set[str] = set()
    unique: list[str] = []
    for metric in metrics:
        if metric in seen:
            continue
        unique.append(metric)
        seen.add(metric)
    return unique


def _build_weekly_rows(
    *,
    normalized_rows: list[dict[str, object]],
    metrics: list[str],
) -> tuple[list[dict[str, object]], dict[str, list[float | None]]]:
    season_rows_sorted = sorted(normalized_rows, key=_parse_match_datetime)
    points = build_weekly_half_win_average(season_rows_sorted)
    if len(points) != len(season_rows_sorted):
        raise RuntimeError("Unexpected mismatch between normalized rows and weekly points.")

    metric_points = {
        metric: build_weekly_metric_series(season_rows_sorted, metric=metric)
        for metric in metrics
    }
    metric_series: dict[str, list[float | None]] = {
        metric: [point.value for point in points]
        for metric, points in metric_points.items()
    }

    weekly_rows: list[dict[str, object]] = []
    for point, raw in zip(points, season_rows_sorted):
        weekly_rows.append(
            {
                "week": point.week,
                "date": point.date,
                "opponent": point.opponent,
                "venue": point.venue,
                "result": point.result,
                "half_win_average": round(point.average, 6),
                "running_half_win_points": round(point.running_points, 6),
                "running_league_points": round(point.running_league_points, 6),
                "points_efficiency": round(point.points_efficiency, 6),
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
                "bookings_points": _as_float(raw.get("bookings_points")),
                "opponent_bookings_points": _as_float(raw.get("opponent_bookings_points")),
                "referee": str(raw.get("Referee", "")).strip(),
                "attendance": raw.get("Attendance"),
            }
        )
    return weekly_rows, metric_series


def _load_competition_teams(
    *,
    db_path: str,
    competition_code: str,
    seasons: list[str],
) -> list[str]:
    conn = initialize_db(db_path)
    try:
        repo = FootstatRepo(conn)
        matches = repo.fetch_matches(
            competition_code=competition_code,
            seasons=seasons,
        )
    finally:
        conn.close()
    teams: set[str] = set()
    for row in matches:
        home = str(row.get("home_team", "")).strip()
        away = str(row.get("away_team", "")).strip()
        if home:
            teams.add(home)
        if away:
            teams.add(away)
    return sorted(teams)


def _build_team_report(
    *,
    db_path: str,
    competition_code: str,
    team: str,
    side: str,
    seasons: list[str],
    metrics: list[str],
    z_threshold: float,
    regime_effect_threshold: float,
    include_findings: bool,
    through_week: int | None,
) -> dict[str, object]:
    normalized = load_normalized_team_rows(
        source="db",
        team=team,
        side=side,
        db_path=db_path,
        competition_code=competition_code,
        seasons=seasons,
    )
    if not normalized:
        raise ValueError(
            f"No DB rows found for team={team!r} seasons={','.join(seasons)}."
        )
    by_season: dict[str, list[dict[str, object]]] = {}
    for row in normalized:
        season = str(row.get("season", "")).strip()
        if not season:
            continue
        by_season.setdefault(season, []).append(row)

    season_reports: list[dict[str, object]] = []
    for season in [value for value in seasons if value in by_season]:
        season_rows = list(by_season[season])
        if through_week is not None:
            season_rows = sorted(season_rows, key=_parse_match_datetime)[:through_week]
        if not season_rows:
            continue
        weekly_rows, metric_series = _build_weekly_rows(
            normalized_rows=season_rows,
            metrics=metrics,
        )
        findings: list[dict[str, object]] = []
        if include_findings:
            findings.extend(
                detect_referee_fingerprint(
                    team=team,
                    season=season,
                    weekly_rows=weekly_rows,
                )
            )
            findings.extend(
                detect_discipline_tax(
                    team=team,
                    season=season,
                    weekly_rows=weekly_rows,
                )
            )
            findings.extend(
                detect_control_without_result(
                    team=team,
                    season=season,
                    weekly_rows=weekly_rows,
                )
            )
            findings.extend(
                detect_streak_fragility(
                    team=team,
                    season=season,
                    weekly_rows=weekly_rows,
                )
            )
            findings.extend(
                detect_metric_outliers_zscore(
                    team=team,
                    season=season,
                    weekly_rows=weekly_rows,
                    metric_series=metric_series,
                    z_threshold=z_threshold,
                )
            )
            findings.extend(
                detect_regime_shift(
                    team=team,
                    season=season,
                    metric_series=metric_series,
                    effect_threshold=regime_effect_threshold,
                )
            )

        results = [str(row["result"]) for row in weekly_rows]
        summary = {
            "matches": len(weekly_rows),
            "wins": results.count("win"),
            "draws": results.count("draw"),
            "losses": results.count("loss"),
            "latest_half_win_average": (
                weekly_rows[-1]["half_win_average"] if weekly_rows else None
            ),
            "latest_running_league_points": (
                weekly_rows[-1]["running_league_points"] if weekly_rows else None
            ),
            "findings_count": len(findings),
        }
        season_reports.append(
            {
                "season": season,
                "summary": summary,
                "weekly_rows": weekly_rows,
                "metric_series": metric_series,
                "findings": findings,
            }
        )

    if not season_reports:
        raise ValueError(
            f"No season rows retained for team={team!r}; check --seasons filter."
        )
    return {"team": team, "seasons": season_reports}


def _build_league_context(
    *,
    db_path: str,
    competition_code: str,
    seasons: list[str],
    side: str,
    metrics: list[str],
    z_threshold: float,
    regime_effect_threshold: float,
    through_week: int | None,
) -> dict[str, object]:
    team_names = _load_competition_teams(
        db_path=db_path,
        competition_code=competition_code,
        seasons=seasons,
    )
    team_reports: list[dict[str, object]] = []
    for team_name in team_names:
        team_reports.append(
            _build_team_report(
                db_path=db_path,
                competition_code=competition_code,
                team=team_name,
                side=side,
                seasons=seasons,
                metrics=metrics,
                z_threshold=z_threshold,
                regime_effect_threshold=regime_effect_threshold,
                include_findings=False,
                through_week=through_week,
            )
        )
    return {
        "scope": "competition-season",
        "competition_code": competition_code,
        "side": side,
        "seasons": seasons,
        "team_count": len(team_reports),
        "teams": team_reports,
    }


def build_weekly_report(
    *,
    db_path: str,
    competition_code: str,
    teams: list[str],
    side: str,
    seasons: list[str],
    metrics: list[str],
    report_date: str,
    z_threshold: float = 2.0,
    regime_effect_threshold: float = 0.8,
    include_league_context: bool = False,
    through_week: int | None = None,
) -> dict[str, object]:
    team_reports: list[dict[str, object]] = []
    for team in teams:
        team_reports.append(
            _build_team_report(
                db_path=db_path,
                competition_code=competition_code,
                team=team,
                side=side,
                seasons=seasons,
                metrics=metrics,
                z_threshold=z_threshold,
                regime_effect_threshold=regime_effect_threshold,
                include_findings=True,
                through_week=through_week,
            )
        )

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool_version": REPORT_TOOL_VERSION,
        "generated_at": generated_at,
        "report_date": report_date,
        "input": {
            "source": "db",
            "db_path": db_path,
            "competition_code": competition_code,
            "teams": teams,
            "side": side,
            "seasons": seasons,
            "metrics": metrics,
            "z_threshold": z_threshold,
            "regime_effect_threshold": regime_effect_threshold,
            "include_league_context": include_league_context,
        },
        "teams": team_reports,
    }
    if through_week is not None:
        report["input"]["through_week"] = through_week
    if include_league_context:
        report["league_context"] = _build_league_context(
            db_path=db_path,
            competition_code=competition_code,
            seasons=seasons,
            side=side,
            metrics=metrics,
            z_threshold=z_threshold,
            regime_effect_threshold=regime_effect_threshold,
            through_week=through_week,
        )
    assert_valid_weekly_report_schema(report)
    return report


def write_report_json(
    report: dict[str, object],
    *,
    out_path: Path,
    pretty: bool = True,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        text = json.dumps(report, indent=2, sort_keys=False)
    else:
        text = json.dumps(report, separators=(",", ":"))
    out_path.write_text(text + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a weekly Arsenal-style report JSON from DB data."
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
            "If omitted, uses the latest season in DB for the competition."
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
        "--out",
        default=None,
        help="Output JSON path. Defaults to docs/reports/weekly-report-...json",
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
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write compact JSON (default writes pretty JSON).",
    )
    parser.add_argument(
        "--through-week",
        type=int,
        default=None,
        help="Optional inclusive week cutoff; only include matches up to this week.",
    )
    parser.add_argument(
        "--league-context",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Include same-season peer team context in the report JSON for stronger "
            "league-relative comparisons."
        ),
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
    if annotation_count:
        assert_valid_weekly_report_schema(report)

    out_path = (
        Path(args.out)
        if args.out
        else default_report_json_path(
            teams=teams,
            seasons=seasons,
            report_date=args.report_date,
            through_week=args.through_week,
        )
    )
    write_report_json(report, out_path=out_path, pretty=not args.compact)

    print(f"Wrote {out_path}")
    print(f"Teams: {', '.join(teams)}")
    print(f"Seasons: {', '.join(seasons)}")
    if args.through_week is not None:
        print(f"Through week: {args.through_week}")
    print(f"Metrics: {', '.join(metrics)}")
    print(
        "Detector thresholds: "
        f"z_threshold={args.z_threshold:.3f}, "
        f"regime_effect_threshold={args.regime_effect_threshold:.3f}"
    )
    print(f"League context: {'enabled' if args.league_context else 'disabled'}")
    print(f"Annotations applied: {annotation_count}")
    for team_report in report["teams"]:
        team_name = str(team_report["team"])
        for season_block in team_report["seasons"]:
            season = str(season_block["season"])
            summary = season_block["summary"]
            print(
                f"{team_name} ({season}): matches={summary['matches']}, "
                f"W/D/L={summary['wins']}/{summary['draws']}/{summary['losses']}, "
                f"findings={summary['findings_count']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
