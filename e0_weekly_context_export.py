#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


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


def _slug(text: str) -> str:
    out = []
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


def _result_short(value: str) -> str:
    key = value.strip().lower()
    if key == "win":
        return "W"
    if key == "draw":
        return "D"
    if key == "loss":
        return "L"
    return key.upper()[:1] or "?"


def _result_points(value: str) -> int:
    key = value.strip().lower()
    if key == "win":
        return 3
    if key == "draw":
        return 1
    return 0


def _result_halfwin(value: str) -> float:
    key = value.strip().lower()
    if key == "win":
        return 1.0
    if key == "draw":
        return 0.5
    return 0.0


def _resolve_schedule_path(
    *,
    explicit_schedule_json: str | None,
    team: str,
    season: str,
) -> Path | None:
    if explicit_schedule_json:
        path = Path(explicit_schedule_json).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    team_slug = _slug(team)
    candidates = [
        Path(f"data/{team_slug}-epl/{team_slug}-schedule-{season}.normalized.json"),
        Path(f"data/{team_slug}-epl/{team_slug}-schedule-{season}.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _load_schedule_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("rows", [])
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _extract_next_fixture(
    *,
    schedule_rows: list[dict[str, Any]],
    current_week: int,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for row in schedule_rows:
        matchday = _as_float(row.get("matchday"))
        if matchday is None:
            continue
        week = int(matchday)
        if week <= current_week:
            continue
        candidates.append(row)
    if not candidates:
        return None
    next_row = sorted(candidates, key=lambda item: int(_as_float(item.get("matchday")) or 0))[0]
    return {
        "matchday": int(_as_float(next_row.get("matchday")) or 0),
        "opponent": str(next_row.get("opponent") or next_row.get("opponent_canonical_name") or ""),
        "opponent_canonical_name": str(next_row.get("opponent_canonical_name") or ""),
        "venue": str(next_row.get("home_away") or ""),
        "kickoff_utc": str(next_row.get("kickoff_utc") or ""),
        "stadium": str(next_row.get("venue") or ""),
    }


def _find_team_block_by_name(report: dict[str, Any], team_name: str) -> dict[str, Any] | None:
    needle = team_name.strip().lower()
    if not needle:
        return None
    for block in _all_team_blocks(report):
        block_name = str(block.get("team", "")).strip().lower()
        if block_name == needle:
            return block
    return None


def _find_season_block(team_block: dict[str, Any], season: str) -> dict[str, Any] | None:
    seasons = team_block.get("seasons", [])
    if not isinstance(seasons, list):
        return None
    for block in seasons:
        if not isinstance(block, dict):
            continue
        if str(block.get("season", "")).strip() == season:
            return block
    return None


def _build_opponent_last_week_context(
    *,
    report: dict[str, Any],
    season: str,
    opponent_name: str,
    current_week: int,
) -> dict[str, Any] | None:
    opponent_block = _find_team_block_by_name(report, opponent_name)
    if opponent_block is None:
        return None
    opponent_season = _find_season_block(opponent_block, season)
    if opponent_season is None:
        return None
    rows = opponent_season.get("weekly_rows")
    if not isinstance(rows, list) or not rows:
        return None

    candidate_rows = [
        row for row in rows
        if isinstance(row, dict) and int(row.get("week", 0) or 0) <= current_week
    ]
    if not candidate_rows:
        return None
    row = sorted(candidate_rows, key=lambda item: int(item.get("week", 0) or 0))[-1]

    goals_for = _as_float(row.get("goals_for"))
    goals_against = _as_float(row.get("goals_against"))
    score = None
    if goals_for is not None and goals_against is not None:
        score = f"{int(goals_for)}-{int(goals_against)}"

    metrics = [
        "shots",
        "shots_on_target",
        "corners",
        "fouls",
        "opponent_shots",
        "opponent_shots_on_target",
        "opponent_corners",
        "opponent_fouls",
    ]
    deltas = _compute_deltas(rows=rows, current_row=row, metrics=metrics)
    directional = _summarize_directional_deltas(deltas, limit=2)

    return {
        "team": str(opponent_block.get("team", opponent_name)),
        "week": int(row.get("week", 0) or 0),
        "result": _result_short(str(row.get("result", ""))),
        "score": score,
        "venue": str(row.get("venue", "")),
        "opponent": str(row.get("opponent", "")),
        "largest_upward_deltas": directional["largest_upward_deltas"],
        "largest_downward_deltas": directional["largest_downward_deltas"],
    }


def _recent_rows(
    *,
    rows: list[dict[str, Any]],
    current_week: int,
    window: int,
) -> list[dict[str, Any]]:
    eligible = [
        row
        for row in rows
        if isinstance(row, dict) and int(row.get("week", 0) or 0) <= current_week
    ]
    if not eligible:
        return []
    eligible = sorted(eligible, key=lambda item: int(item.get("week", 0) or 0))
    return eligible[-window:]


def _mean(values: list[float | None]) -> float:
    clean = [value for value in values if value is not None]
    if not clean:
        return 0.0
    return round(sum(clean) / len(clean), 4)


def _build_recent_form_summary(
    *,
    rows: list[dict[str, Any]],
    current_week: int,
    window: int,
) -> dict[str, Any] | None:
    recent = _recent_rows(rows=rows, current_week=current_week, window=window)
    if not recent:
        return None
    w = d = l = 0
    points_total = 0
    halfwin_total = 0.0
    goal_diff_total = 0.0
    goals_for_total = 0.0
    goals_against_total = 0.0

    for row in recent:
        result = str(row.get("result", ""))
        key = result.strip().lower()
        if key == "win":
            w += 1
        elif key == "draw":
            d += 1
        else:
            l += 1
        points_total += _result_points(result)
        halfwin_total += _result_halfwin(result)
        gf = _as_float(row.get("goals_for")) or 0.0
        ga = _as_float(row.get("goals_against")) or 0.0
        goals_for_total += gf
        goals_against_total += ga
        goal_diff_total += (gf - ga)

    count = len(recent)
    metric_keys = [
        "shots",
        "shots_on_target",
        "corners",
        "fouls",
        "opponent_shots",
        "opponent_shots_on_target",
        "opponent_corners",
        "opponent_fouls",
    ]
    per_match = {
        "points_per_match": round(points_total / count, 4),
        "goals_for_per_match": round(goals_for_total / count, 4),
        "goals_against_per_match": round(goals_against_total / count, 4),
        "goal_diff_per_match": round(goal_diff_total / count, 4),
    }
    for metric in metric_keys:
        per_match[f"{metric}_per_match"] = _mean([_as_float(row.get(metric)) for row in recent])

    return {
        "window": count,
        "from_week": int(recent[0].get("week", 0) or 0),
        "to_week": int(recent[-1].get("week", 0) or 0),
        "wdl": {"w": w, "d": d, "l": l},
        "points_total": points_total,
        "halfwin_average": round(halfwin_total / count, 4),
        "goal_diff_total": round(goal_diff_total, 4),
        **per_match,
    }


def _build_next_week_matchup_lens(
    *,
    team_form: dict[str, Any],
    opponent_form: dict[str, Any],
) -> dict[str, Any]:
    keys = [
        "points_per_match",
        "goals_for_per_match",
        "goals_against_per_match",
        "shots_per_match",
        "shots_on_target_per_match",
        "opponent_shots_per_match",
        "opponent_shots_on_target_per_match",
        "corners_per_match",
        "opponent_corners_per_match",
    ]
    deltas: dict[str, float] = {}
    for key in keys:
        a = _as_float(team_form.get(key))
        b = _as_float(opponent_form.get(key))
        if a is None or b is None:
            continue
        deltas[key] = round(a - b, 4)
    
    higher_is_better = {
        "points_per_match",
        "goals_for_per_match",
        "goal_diff_per_match",
        "shots_per_match",
        "shots_on_target_per_match",
        "corners_per_match",
    }
    lower_is_better = {
        "goals_against_per_match",
        "opponent_shots_per_match",
        "opponent_shots_on_target_per_match",
        "opponent_corners_per_match",
        "fouls_per_match",
    }
    metric_labels = {
        "points_per_match": "points per match",
        "goals_for_per_match": "goals scored per match",
        "goals_against_per_match": "goals conceded per match",
        "goal_diff_per_match": "goal difference per match",
        "shots_per_match": "shots per match",
        "shots_on_target_per_match": "shots on target per match",
        "opponent_shots_per_match": "shots allowed per match",
        "opponent_shots_on_target_per_match": "shots on target allowed per match",
        "corners_per_match": "corners per match",
        "opponent_corners_per_match": "corners conceded per match",
    }

    beneficial: list[dict[str, Any]] = []
    harmful: list[dict[str, Any]] = []
    for key, delta in deltas.items():
        if delta == 0:
            continue
        if key in higher_is_better:
            direction = "beneficial" if delta > 0 else "harmful"
        elif key in lower_is_better:
            direction = "harmful" if delta > 0 else "beneficial"
        else:
            direction = "beneficial" if delta > 0 else "harmful"
        item = {
            "metric": key,
            "label": metric_labels.get(key, key),
            "delta": round(delta, 4),
            "direction_for_team": direction,
        }
        if direction == "beneficial":
            beneficial.append(item)
        else:
            harmful.append(item)

    beneficial = sorted(beneficial, key=lambda item: abs(float(item.get("delta", 0.0))), reverse=True)
    harmful = sorted(harmful, key=lambda item: abs(float(item.get("delta", 0.0))), reverse=True)
    return {
        "window": int(team_form.get("window", 0) or 0),
        "team_minus_opponent": deltas,
        "top_beneficial": beneficial[:2],
        "top_harmful": harmful[:2],
    }


def _parse_metrics(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return list(fallback)
    metrics = [part.strip() for part in value.split(",") if part.strip()]
    if not metrics:
        return list(fallback)
    seen: set[str] = set()
    out: list[str] = []
    for metric in metrics:
        if metric in seen:
            continue
        seen.add(metric)
        out.append(metric)
    return out


def _select_team_block(report: dict[str, Any], team: str | None) -> dict[str, Any]:
    blocks = report.get("teams", [])
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("Report has no teams block.")
    if team is None:
        block = blocks[0]
        if not isinstance(block, dict):
            raise ValueError("Invalid team block in report.")
        return block
    needle = team.strip().lower()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if str(block.get("team", "")).strip().lower() == needle:
            return block
    raise ValueError(f"Team {team!r} not found in report.")


def _all_team_blocks(report: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    report_teams = report.get("teams", [])
    if isinstance(report_teams, list):
        blocks.extend(block for block in report_teams if isinstance(block, dict))
    league_context = report.get("league_context")
    if isinstance(league_context, dict):
        league_teams = league_context.get("teams", [])
        if isinstance(league_teams, list):
            blocks.extend(block for block in league_teams if isinstance(block, dict))
    return blocks


def _select_season_block(team_block: dict[str, Any], season: str | None) -> dict[str, Any]:
    seasons = team_block.get("seasons", [])
    if not isinstance(seasons, list) or not seasons:
        raise ValueError("Selected team has no seasons in report.")
    if season is None:
        block = seasons[-1]
        if not isinstance(block, dict):
            raise ValueError("Invalid season block in report.")
        return block
    needle = season.strip()
    for block in seasons:
        if not isinstance(block, dict):
            continue
        if str(block.get("season", "")).strip() == needle:
            return block
    raise ValueError(f"Season {season!r} not found for selected team.")


def _select_week_row(weekly_rows: list[dict[str, Any]], week: int | None) -> dict[str, Any]:
    if not weekly_rows:
        raise ValueError("Season has no weekly rows.")
    if week is None:
        return weekly_rows[-1]
    for row in weekly_rows:
        if int(row.get("week", -1)) == week:
            return row
    raise ValueError(f"Week {week} not found in selected season.")


def _compute_deltas(
    *,
    rows: list[dict[str, Any]],
    current_row: dict[str, Any],
    metrics: list[str],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for metric in metrics:
        curr = _as_float(current_row.get(metric))
        if curr is None:
            continue
        values = [_as_float(row.get(metric)) for row in rows]
        values = [value for value in values if value is not None]
        if not values:
            continue
        avg = sum(values) / len(values)
        out[metric] = round(curr - avg, 4)
    return out


def _delta_direction_for_team(metric: str, delta: float) -> str:
    metric_key = metric.strip().lower()
    # Explicit exceptions where an increase for opponent_* can still benefit the team.
    opponent_higher_is_beneficial = {
        "opponent_fouls",
        "opponent_yellow_cards",
        "opponent_red_cards",
        "opponent_bookings_points",
        "opponent_free_kicks_conceded",
        "opponent_offsides",
    }
    own_higher_is_harmful = {
        "goals_against",
        "opponent_total_goals",
        "opponent_halftime_goals",
        "fouls",
        "yellow_cards",
        "red_cards",
        "bookings_points",
        "free_kicks_conceded",
        "offsides",
    }

    if metric_key in opponent_higher_is_beneficial:
        return "beneficial" if delta > 0 else "harmful"
    if metric_key.startswith("opponent_"):
        return "harmful" if delta > 0 else "beneficial"
    if metric_key in own_higher_is_harmful:
        return "harmful" if delta > 0 else "beneficial"
    return "beneficial" if delta > 0 else "harmful"


def _summarize_directional_deltas(
    deltas: dict[str, float],
    *,
    limit: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    items = sorted(deltas.items(), key=lambda item: item[1], reverse=True)
    upward = []
    downward = []
    for metric, delta in items:
        if delta > 0:
            upward.append(
                {
                    "metric": metric,
                    "delta": round(delta, 4),
                    "direction_for_team": _delta_direction_for_team(metric, delta),
                }
            )
    for metric, delta in sorted(deltas.items(), key=lambda item: item[1]):
        if delta < 0:
            downward.append(
                {
                    "metric": metric,
                    "delta": round(delta, 4),
                    "direction_for_team": _delta_direction_for_team(metric, delta),
                }
            )
    return {
        "largest_upward_deltas": upward[:limit],
        "largest_downward_deltas": downward[:limit],
    }


def _compute_context_window(
    *,
    rows: list[dict[str, Any]],
    current_week: int,
    window: int,
) -> dict[str, Any]:
    bounded = _window_rows(rows=rows, current_week=current_week, window=window)
    w = d = l = points = 0
    matches: list[dict[str, Any]] = []
    for row in bounded:
        result = str(row.get("result", ""))
        short = _result_short(result)
        if short == "W":
            w += 1
        elif short == "D":
            d += 1
        elif short == "L":
            l += 1
        points += _result_points(result)
        matches.append(
            {
                "week": int(row.get("week")),
                "opponent": str(row.get("opponent", "")),
                "result": short,
                "goal_diff": row.get("goal_diff"),
            }
        )
    return {
        "window": len(bounded),
        "last_n_wdl": {"w": w, "d": d, "l": l},
        "last_n_points": points,
        "last_n_matches": matches,
    }


def _window_rows(
    *,
    rows: list[dict[str, Any]],
    current_week: int,
    window: int,
) -> list[dict[str, Any]]:
    bounded = [row for row in rows if int(row.get("week", -1)) <= current_week]
    return bounded[-max(1, window) :]


def _compute_form_snapshot(
    *,
    rows: list[dict[str, Any]],
    current_week: int,
    window: int,
) -> dict[str, Any]:
    bounded = _window_rows(rows=rows, current_week=current_week, window=window)
    w = d = l = points = 0
    halfwin_total = 0.0
    goal_diff_total = 0.0
    goals_for_total = 0.0
    goals_against_total = 0.0

    for row in bounded:
        result = str(row.get("result", ""))
        short = _result_short(result)
        if short == "W":
            w += 1
        elif short == "D":
            d += 1
        elif short == "L":
            l += 1
        points += _result_points(result)
        halfwin_total += _result_halfwin(result)
        goal_diff_total += _as_float(row.get("goal_diff")) or 0.0
        goals_for_total += _as_float(row.get("goals_for")) or 0.0
        goals_against_total += _as_float(row.get("goals_against")) or 0.0

    matches = len(bounded)
    return {
        "window": matches,
        "wdl": {"w": w, "d": d, "l": l},
        "points": points,
        "halfwin_average": round(halfwin_total / matches, 4) if matches else None,
        "goal_diff_total": round(goal_diff_total, 4),
        "goals_for_total": round(goals_for_total, 4),
        "goals_against_total": round(goals_against_total, 4),
    }


def _all_numeric_metrics(
    *,
    rows: list[dict[str, Any]],
    metrics: list[str],
) -> list[str]:
    ignore = {
        "week",
        "opponent",
        "result",
        "venue",
        "annotation",
    }
    preferred = list(metrics)
    for extra in ("goals_for", "goals_against", "goal_diff"):
        if extra not in preferred:
            preferred.append(extra)
    seen: set[str] = set()
    out: list[str] = []
    for metric in preferred:
        if metric in ignore or metric in seen:
            continue
        if any(_as_float(row.get(metric)) is not None for row in rows):
            seen.add(metric)
            out.append(metric)
    for row in rows:
        for key, value in row.items():
            if key in ignore or key in seen:
                continue
            if _as_float(value) is None:
                continue
            seen.add(key)
            out.append(key)
    return out


def _linear_slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    return numerator / denominator


def _trend_direction(*, slope: float, values: list[float]) -> str:
    spread = max(values) - min(values) if values else 0.0
    threshold = max(0.05, spread * 0.05)
    if abs(slope) < threshold:
        return "flat"
    return "up" if slope > 0 else "down"


def _compute_trend_summary(
    *,
    rows: list[dict[str, Any]],
    current_week: int,
    window: int,
    metrics: list[str],
) -> dict[str, dict[str, Any]]:
    bounded = _window_rows(rows=rows, current_week=current_week, window=window)
    out: dict[str, dict[str, Any]] = {}
    for metric in _all_numeric_metrics(rows=rows, metrics=metrics):
        points: list[tuple[float, float]] = []
        values: list[float] = []
        for row in bounded:
            week_value = _as_float(row.get("week"))
            metric_value = _as_float(row.get(metric))
            if week_value is None or metric_value is None:
                continue
            points.append((week_value, metric_value))
            values.append(metric_value)
        slope = _linear_slope(points)
        if slope is None or len(values) < 2:
            continue
        out[metric] = {
            "window": len(values),
            "direction": _trend_direction(slope=slope, values=values),
            "slope_per_week": round(slope, 4),
            "current_value": round(values[-1], 4),
        }
    return out


def _ordinal(rank: int) -> str:
    if 10 <= (rank % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"


def _describe_extreme(metric: str, direction: str, rank_in_season: int) -> str:
    if rank_in_season == 1:
        adjective = "highest" if direction == "high" else "lowest"
    else:
        adjective = f"{_ordinal(rank_in_season)}-highest" if direction == "high" else f"{_ordinal(rank_in_season)}-lowest"
    return f"{adjective} {metric} in season"


def _compute_week_extremes(
    *,
    rows: list[dict[str, Any]],
    current_row: dict[str, Any],
    metrics: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for metric in _all_numeric_metrics(rows=rows, metrics=metrics):
        current_value = _as_float(current_row.get(metric))
        if current_value is None:
            continue
        values = [_as_float(row.get(metric)) for row in rows]
        numeric_values = [value for value in values if value is not None]
        if len(numeric_values) < 3:
            continue
        rank_high = 1 + sum(1 for value in numeric_values if value > current_value)
        rank_low = 1 + sum(1 for value in numeric_values if value < current_value)
        if rank_high <= rank_low:
            direction = "high"
            rank = rank_high
        else:
            direction = "low"
            rank = rank_low
        if rank > 3:
            continue
        out.append(
            {
                "metric": metric,
                "direction": direction,
                "rank_in_season": rank,
                "sample": len(numeric_values),
                "value": round(current_value, 4),
                "label": _describe_extreme(metric, direction, rank),
            }
        )
    out.sort(key=lambda item: (int(item["rank_in_season"]), str(item["metric"])))
    return out


def _compute_week_flags(
    *,
    weekly_rows: list[dict[str, Any]],
    current_row: dict[str, Any],
    metrics: list[str],
    deltas: dict[str, float],
) -> list[str]:
    flags: list[str] = []
    extremes = _compute_week_extremes(
        rows=weekly_rows,
        current_row=current_row,
        metrics=metrics,
    )
    for item in extremes[:3]:
        flags.append(str(item["label"]))
    sortable_deltas = [
        (metric, delta) for metric, delta in deltas.items() if metric not in {"goals_for", "goals_against"}
    ]
    if sortable_deltas:
        top_metric, top_delta = max(sortable_deltas, key=lambda item: item[1])
        low_metric, low_delta = min(sortable_deltas, key=lambda item: item[1])
        if top_delta > 0:
            flags.append(f"{top_metric} is {top_delta:+.2f} vs season average")
        if low_delta < 0 and low_metric != top_metric:
            flags.append(f"{low_metric} is {low_delta:+.2f} vs season average")
    return flags[:5]


def _compute_season_rankings(
    *,
    rows: list[dict[str, Any]],
    current_row: dict[str, Any],
    metrics: list[str],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for metric in _all_numeric_metrics(rows=rows, metrics=metrics):
        current_value = _as_float(current_row.get(metric))
        if current_value is None:
            continue
        values = [_as_float(row.get(metric)) for row in rows]
        numeric_values = [value for value in values if value is not None]
        if len(numeric_values) < 2:
            continue
        high_rank = 1 + sum(1 for value in numeric_values if value > current_value)
        low_rank = 1 + sum(1 for value in numeric_values if value < current_value)
        percentile_high = sum(1 for value in numeric_values if value <= current_value) / len(
            numeric_values
        )
        out[metric] = {
            "current_value": round(current_value, 4),
            "high_rank": high_rank,
            "low_rank": low_rank,
            "sample": len(numeric_values),
            "percentile_high": round(percentile_high, 4),
        }
    return out


def _season_rows_for_team(
    *,
    report: dict[str, Any],
    team_name: str,
    season: str,
) -> list[dict[str, Any]] | None:
    for block in _all_team_blocks(report):
        if str(block.get("team", "")).strip() != team_name:
            continue
        for season_block in block.get("seasons", []):
            if not isinstance(season_block, dict):
                continue
            if str(season_block.get("season", "")).strip() != season:
                continue
            weekly_rows = season_block.get("weekly_rows")
            if isinstance(weekly_rows, list):
                return [row for row in weekly_rows if isinstance(row, dict)]
    return None


def _week_row_for_team_season(
    *,
    report: dict[str, Any],
    team_name: str,
    season: str,
    week: int,
) -> dict[str, Any] | None:
    rows = _season_rows_for_team(report=report, team_name=team_name, season=season)
    if rows is None:
        return None
    for row in rows:
        if int(row.get("week", -1)) == week:
            return row
    return None


def _compute_league_relative(
    *,
    report: dict[str, Any],
    team: str,
    season: str,
    current_week: int,
    current_row: dict[str, Any],
    metrics: list[str],
    window: int,
    data_gaps: list[str],
) -> dict[str, Any]:
    teams = _all_team_blocks(report)
    if not teams:
        data_gaps.append("league_relative unavailable: report has no team blocks")
        return {}

    peer_rows: list[tuple[str, dict[str, Any]]] = []
    seen_teams: set[str] = set()
    for block in teams:
        team_name = str(block.get("team", "")).strip()
        if not team_name or team_name in seen_teams:
            continue
        seen_teams.add(team_name)
        week_row = _week_row_for_team_season(
            report=report,
            team_name=team_name,
            season=season,
            week=current_week,
        )
        if week_row is not None:
            peer_rows.append((team_name, week_row))

    if len(peer_rows) < 2:
        data_gaps.append(
            f"league_relative unavailable: need at least 2 teams with season {season} week {current_week} in report or league_context"
        )
        return {}

    comparisons: dict[str, dict[str, Any]] = {}
    season_to_date_metrics: dict[str, dict[str, Any]] = {}
    percentile_trends: dict[str, dict[str, Any]] = {}
    current_team_found = any(name == team for name, _ in peer_rows)
    if not current_team_found:
        data_gaps.append(
            f"league_relative unavailable: selected team {team} missing from peer set for season {season} week {current_week}"
        )
        return {}

    peer_season_rows: list[tuple[str, list[dict[str, Any]]]] = []
    for team_name, _ in peer_rows:
        season_rows = _season_rows_for_team(
            report=report,
            team_name=team_name,
            season=season,
        )
        if season_rows:
            peer_season_rows.append((team_name, season_rows))

    for metric in _all_numeric_metrics(rows=[row for _, row in peer_rows], metrics=metrics):
        current_value = _as_float(current_row.get(metric))
        if current_value is None:
            continue
        values = []
        for team_name, row in peer_rows:
            value = _as_float(row.get(metric))
            if value is None:
                continue
            values.append((team_name, value))
        if len(values) < 2:
            continue
        numeric_values = [value for _, value in values]
        avg = sum(numeric_values) / len(numeric_values)
        high_rank = 1 + sum(1 for value in numeric_values if value > current_value)
        low_rank = 1 + sum(1 for value in numeric_values if value < current_value)
        comparisons[metric] = {
            "current_value": round(current_value, 4),
            "report_week_avg": round(avg, 4),
            "delta_vs_report_week_avg": round(current_value - avg, 4),
            "high_rank": high_rank,
            "low_rank": low_rank,
            "teams_with_value": len(values),
        }

        cumulative_values: list[tuple[str, float]] = []
        for team_name, season_rows in peer_season_rows:
            window_rows = [
                row for row in season_rows if int(row.get("week", -1)) <= current_week
            ]
            metric_values = [
                _as_float(row.get(metric))
                for row in window_rows
                if _as_float(row.get(metric)) is not None
            ]
            if not metric_values:
                continue
            cumulative_values.append((team_name, sum(metric_values) / len(metric_values)))
        if len(cumulative_values) >= 2:
            current_cumulative = next(
                (value for team_name, value in cumulative_values if team_name == team),
                None,
            )
            if current_cumulative is not None:
                peer_cumulative = [value for _, value in cumulative_values]
                cumulative_avg = sum(peer_cumulative) / len(peer_cumulative)
                season_to_date_metrics[metric] = {
                    "current_value": round(current_cumulative, 4),
                    "peer_avg": round(cumulative_avg, 4),
                    "delta_vs_peer_avg": round(current_cumulative - cumulative_avg, 4),
                    "high_rank": 1
                    + sum(1 for value in peer_cumulative if value > current_cumulative),
                    "low_rank": 1
                    + sum(1 for value in peer_cumulative if value < current_cumulative),
                    "teams_with_value": len(cumulative_values),
                    "percentile_high": round(
                        sum(1 for value in peer_cumulative if value <= current_cumulative)
                        / len(peer_cumulative),
                        4,
                    ),
                }

        percentile_points: list[tuple[float, float]] = []
        for week_value in range(max(1, current_week - (max(1, window) - 1)), current_week + 1):
            week_peer_values: list[float] = []
            current_week_value: float | None = None
            for team_name, season_rows in peer_season_rows:
                row = next(
                    (item for item in season_rows if int(item.get("week", -1)) == week_value),
                    None,
                )
                if row is None:
                    continue
                metric_value = _as_float(row.get(metric))
                if metric_value is None:
                    continue
                week_peer_values.append(metric_value)
                if team_name == team:
                    current_week_value = metric_value
            if current_week_value is None or len(week_peer_values) < 2:
                continue
            percentile = sum(
                1 for value in week_peer_values if value <= current_week_value
            ) / len(week_peer_values)
            percentile_points.append((float(week_value), percentile))
        if len(percentile_points) >= 2:
            percentile_values = [value for _, value in percentile_points]
            slope = _linear_slope(percentile_points)
            if slope is not None:
                current_percentile = percentile_values[-1]
                avg_percentile = sum(percentile_values) / len(percentile_values)
                percentile_trends[metric] = {
                    "window": len(percentile_points),
                    "current_percentile_high": round(current_percentile, 4),
                    "window_avg_percentile_high": round(avg_percentile, 4),
                    "delta_vs_window_avg": round(current_percentile - avg_percentile, 4),
                    "slope_per_week": round(slope, 4),
                    "direction": _trend_direction(
                        slope=slope,
                        values=percentile_values,
                    ),
                }

    if not comparisons:
        data_gaps.append(
            f"league_relative unavailable: no shared numeric metrics across report teams for season {season} week {current_week}"
        )
        return {}

    return {
        "scope": "league_context_same_season_week"
        if isinstance(report.get("league_context"), dict)
        else "report_teams_same_season_week",
        "season": season,
        "week": current_week,
        "team_count": len(peer_rows),
        "metrics": comparisons,
        "season_to_date_metrics": season_to_date_metrics,
        "percentile_trends": percentile_trends,
        "top_percentile_movers": _summarize_percentile_movers(percentile_trends),
    }


def _metric_label(metric: str) -> str:
    return metric.replace("_", " ")


def _summarize_percentile_movers(
    percentile_trends: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = [
        (metric, trend)
        for metric, trend in percentile_trends.items()
        if _as_float(trend.get("slope_per_week")) is not None
    ]
    rising = sorted(
        (
            (metric, trend)
            for metric, trend in items
            if str(trend.get("direction", "")).strip() == "up"
        ),
        key=lambda item: float(item[1]["slope_per_week"]),
        reverse=True,
    )
    falling = sorted(
        (
            (metric, trend)
            for metric, trend in items
            if str(trend.get("direction", "")).strip() == "down"
        ),
        key=lambda item: float(item[1]["slope_per_week"]),
    )

    def _pack(metric: str, trend: dict[str, Any]) -> dict[str, Any]:
        return {
            "metric": metric,
            "direction": str(trend.get("direction", "")),
            "slope_per_week": round(float(trend["slope_per_week"]), 4),
            "current_percentile_high": round(
                float(trend.get("current_percentile_high", 0.0)),
                4,
            ),
            "delta_vs_window_avg": round(
                float(trend.get("delta_vs_window_avg", 0.0)),
                4,
            ),
        }

    return {
        "rising": [_pack(metric, trend) for metric, trend in rising[:3]],
        "falling": [_pack(metric, trend) for metric, trend in falling[:3]],
    }


def _build_percentile_mover_flags(
    movers: dict[str, list[dict[str, Any]]],
) -> list[str]:
    flags: list[str] = []
    rising = movers.get("rising", [])
    falling = movers.get("falling", [])
    if rising:
        top = rising[0]
        flags.append(
            f"{top['metric']} peer percentile is rising ({top['slope_per_week']:+.3f}/week)"
        )
    if falling:
        top = falling[0]
        flags.append(
            f"{top['metric']} peer percentile is falling ({top['slope_per_week']:+.3f}/week)"
        )
    return flags


def _compute_context_quality(
    *,
    metric_list: list[str],
    trend_summary: dict[str, dict[str, Any]],
    season_rankings: dict[str, dict[str, Any]],
    league_relative: dict[str, Any],
    data_gaps: list[str],
    window: int,
) -> dict[str, Any]:
    small_sample_metrics: list[str] = []
    flat_signal_metrics: list[str] = []
    missing_metric_sections: list[str] = []
    notes: list[str] = []

    peer_context_available = bool(league_relative)
    peer_team_count = int(_as_float(league_relative.get("team_count")) or 0)

    for metric in metric_list:
        metric_sections_missing: list[str] = []
        trend = trend_summary.get(metric)
        season_rank = season_rankings.get(metric)
        peer_metric = (
            league_relative.get("metrics", {}).get(metric)
            if isinstance(league_relative.get("metrics"), dict)
            else None
        )

        if trend is None:
            metric_sections_missing.append("trend_summary")
        if season_rank is None:
            metric_sections_missing.append("season_rankings")
        if peer_context_available and peer_metric is None:
            metric_sections_missing.append("league_relative.metrics")
        for section in metric_sections_missing:
            missing_metric_sections.append(f"{section}:{metric}")

        season_sample = int(_as_float((season_rank or {}).get("sample")) or 0)
        trend_window = int(_as_float((trend or {}).get("window")) or 0)
        peer_sample = int(_as_float((peer_metric or {}).get("teams_with_value")) or 0)
        if (
            (season_sample and season_sample < 5)
            or (trend_window and trend_window < 3)
            or (peer_context_available and peer_sample and peer_sample < 3)
        ):
            if metric not in small_sample_metrics:
                small_sample_metrics.append(metric)

        if isinstance(trend, dict) and str(trend.get("direction", "")) == "flat":
            flat_signal_metrics.append(metric)

    if not peer_context_available:
        notes.append("Peer context unavailable; peer-relative claims should be treated cautiously.")
    elif peer_team_count < 3:
        notes.append(
            f"Peer context is based on only {peer_team_count} teams; peer-relative ranks are unstable."
        )
    if window < 3:
        notes.append(
            f"Trend window is only {window} match{'es' if window != 1 else ''}; recent trend reads are fragile."
        )
    if small_sample_metrics:
        notes.append(
            "Small-sample metrics: " + ", ".join(sorted(small_sample_metrics))
        )
    if flat_signal_metrics:
        notes.append(
            "Flat-signal metrics: " + ", ".join(sorted(flat_signal_metrics))
        )
    notes.extend(data_gaps)

    confidence_score = 2
    if not peer_context_available or peer_team_count < 3:
        confidence_score -= 1
    if window < 3:
        confidence_score -= 1
    if len(small_sample_metrics) >= max(1, len(metric_list) // 2):
        confidence_score -= 1
    if data_gaps:
        confidence_score -= 1
    if confidence_score <= 0:
        overall_confidence = "low"
    elif confidence_score == 1:
        overall_confidence = "medium"
    else:
        overall_confidence = "high"

    return {
        "overall_confidence": overall_confidence,
        "peer_context_available": peer_context_available,
        "peer_team_count": peer_team_count,
        "trend_window_size": window,
        "small_sample_metrics": sorted(small_sample_metrics),
        "flat_signal_metrics": sorted(flat_signal_metrics),
        "missing_metric_sections": sorted(missing_metric_sections),
        "notes": notes,
    }


def _build_chart_hooks(
    *,
    current_week: int,
    form_snapshot: dict[str, Any],
    deltas: dict[str, float],
    trend_summary: dict[str, dict[str, Any]],
    week_extremes: list[dict[str, Any]],
    league_relative: dict[str, Any],
) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    if week_extremes:
        top_extreme = week_extremes[0]
        hooks.append(
            {
                "id": f"season-extreme-{top_extreme['metric']}",
                "type": "season-line-highlight",
                "metrics": [top_extreme["metric"]],
                "focus_week": current_week,
                "why": str(top_extreme["label"]),
            }
        )

    if deltas:
        metric, delta = max(deltas.items(), key=lambda item: abs(item[1]))
        hooks.append(
            {
                "id": f"current-vs-season-avg-{metric}",
                "type": "current-vs-average-bar",
                "metrics": [metric],
                "focus_week": current_week,
                "why": f"{_metric_label(metric)} moved {delta:+.2f} vs season average",
            }
        )

    if trend_summary:
        metric, trend = max(
            trend_summary.items(),
            key=lambda item: abs(float(item[1].get("slope_per_week", 0.0))),
        )
        hooks.append(
            {
                "id": f"trend-{metric}",
                "type": "recent-trend-line",
                "metrics": [metric],
                "window": int(trend.get("window", 0)),
                "focus_week": current_week,
                "why": f"{_metric_label(metric)} trend is {trend['direction']} over the recent window",
            }
        )

    if "goal_diff_total" in form_snapshot:
        hooks.append(
            {
                "id": "form-vs-goal-diff",
                "type": "form-window-summary",
                "metrics": ["goal_diff", "points"],
                "window": int(form_snapshot.get("window", 0) or 0),
                "focus_week": current_week,
                "why": "Recent results can be read against aggregate goal difference and points",
            }
        )

    percentile_movers = league_relative.get("top_percentile_movers", {})
    if isinstance(percentile_movers, dict):
        falling = percentile_movers.get("falling", [])
        if isinstance(falling, list) and falling:
            top = falling[0]
            metric = str(top.get("metric", "")).strip()
            if metric:
                hooks.append(
                    {
                        "id": f"peer-percentile-falling-{metric}",
                        "type": "peer-percentile-trend-line",
                        "metrics": [metric],
                        "focus_week": current_week,
                        "why": (
                            f"{_metric_label(metric)} is losing peer standing "
                            f"({float(top.get('slope_per_week', 0.0)):+.3f}/week)"
                        ),
                    }
                )
        rising = percentile_movers.get("rising", [])
        if isinstance(rising, list) and rising:
            top = rising[0]
            metric = str(top.get("metric", "")).strip()
            if metric:
                hooks.append(
                    {
                        "id": f"peer-percentile-rising-{metric}",
                        "type": "peer-percentile-trend-line",
                        "metrics": [metric],
                        "focus_week": current_week,
                        "why": (
                            f"{_metric_label(metric)} is gaining peer standing "
                            f"({float(top.get('slope_per_week', 0.0)):+.3f}/week)"
                        ),
                    }
                )

    season_to_date = league_relative.get("season_to_date_metrics", {})
    if isinstance(season_to_date, dict) and season_to_date:
        ranked = sorted(
            (
                (metric, values)
                for metric, values in season_to_date.items()
                if isinstance(values, dict)
                and _as_float(values.get("delta_vs_peer_avg")) is not None
                and _as_float(values.get("high_rank")) is not None
            ),
            key=lambda item: (
                int(float(item[1]["high_rank"])),
                -abs(float(item[1]["delta_vs_peer_avg"])),
            ),
        )
        if ranked:
            metric, values = ranked[0]
            hooks.append(
                {
                    "id": f"season-to-date-rank-{metric}",
                    "type": "peer-rank-shift-summary",
                    "metrics": [metric],
                    "focus_week": current_week,
                    "why": (
                        f"{_metric_label(metric)} sits {int(float(values['high_rank']))}"
                        f"/{int(float(values['teams_with_value']))} on season-to-date peer average"
                    ),
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hook in hooks:
        hook_id = str(hook.get("id", ""))
        if not hook_id or hook_id in seen:
            continue
        seen.add(hook_id)
        deduped.append(hook)
    return deduped[:6]


def _find_chart_hooks_for_metric(
    *,
    chart_hooks: list[dict[str, Any]],
    metric: str,
) -> list[str]:
    hook_ids: list[str] = []
    for hook in chart_hooks:
        metrics = hook.get("metrics")
        if not isinstance(metrics, list):
            continue
        if metric in {str(value) for value in metrics}:
            hook_id = str(hook.get("id", "")).strip()
            if hook_id:
                hook_ids.append(hook_id)
    return hook_ids


def _clamp_story_confidence(
    base_confidence: str,
    *,
    degrade: int = 0,
) -> str:
    order = ["low", "medium", "high"]
    try:
        idx = order.index(base_confidence)
    except ValueError:
        idx = 1
    idx = max(0, idx - degrade)
    return order[idx]


def _build_story_pegs(
    *,
    week_extremes: list[dict[str, Any]],
    deltas: dict[str, float],
    league_relative: dict[str, Any],
    anomalies: list[dict[str, Any]],
    chart_hooks: list[dict[str, Any]],
    context_quality: dict[str, Any],
    week_flags: list[str],
) -> list[dict[str, Any]]:
    pegs: list[dict[str, Any]] = []
    base_confidence = str(context_quality.get("overall_confidence", "medium"))

    if anomalies:
        anomaly = anomalies[0]
        pegs.append(
            {
                "id": f"anomaly-{str(anomaly.get('kind', 'story')).replace('_', '-')}",
                "title": str(anomaly.get("kind", "Anomaly")).replace("_", " ").title(),
                "peg_type": "anomaly",
                "summary": str(anomaly.get("description", "")),
                "evidence_metrics": [],
                "evidence_notes": [str(anomaly.get("severity", "info"))],
                "confidence": _clamp_story_confidence(base_confidence),
                "chart_hook_ids": [],
            }
        )

    if week_extremes:
        top = week_extremes[0]
        metric = str(top.get("metric", ""))
        pegs.append(
            {
                "id": f"season-extreme-{metric}",
                "title": f"{_metric_label(metric).title()} season extreme",
                "peg_type": "week-spike",
                "summary": str(top.get("label", "")),
                "evidence_metrics": [metric],
                "evidence_notes": week_flags[:2],
                "confidence": _clamp_story_confidence(base_confidence),
                "chart_hook_ids": _find_chart_hooks_for_metric(
                    chart_hooks=chart_hooks,
                    metric=metric,
                ),
            }
        )

    if deltas:
        metric, delta = max(deltas.items(), key=lambda item: abs(item[1]))
        pegs.append(
            {
                "id": f"team-delta-{metric}",
                "title": f"{_metric_label(metric).title()} diverged from baseline",
                "peg_type": "season-trend",
                "summary": f"{_metric_label(metric)} moved {delta:+.2f} vs season average.",
                "evidence_metrics": [metric],
                "evidence_notes": [
                    flag for flag in week_flags if metric in flag
                ][:2],
                "confidence": _clamp_story_confidence(base_confidence),
                "chart_hook_ids": _find_chart_hooks_for_metric(
                    chart_hooks=chart_hooks,
                    metric=metric,
                ),
            }
        )

    top_movers = league_relative.get("top_percentile_movers", {})
    if isinstance(top_movers, dict):
        for direction in ("falling", "rising"):
            movers = top_movers.get(direction, [])
            if not isinstance(movers, list) or not movers:
                continue
            mover = movers[0]
            metric = str(mover.get("metric", "")).strip()
            if not metric:
                continue
            verb = "losing" if direction == "falling" else "gaining"
            pegs.append(
                {
                    "id": f"peer-shift-{direction}-{metric}",
                    "title": f"{_metric_label(metric).title()} peer standing is {direction}",
                    "peg_type": "peer-shift",
                    "summary": (
                        f"{_metric_label(metric)} is {verb} peer percentile at "
                        f"{float(mover.get('slope_per_week', 0.0)):+.3f} per week."
                    ),
                    "evidence_metrics": [metric],
                    "evidence_notes": [
                        flag for flag in week_flags if metric in flag
                    ][:2],
                    "confidence": _clamp_story_confidence(base_confidence, degrade=1),
                    "chart_hook_ids": _find_chart_hooks_for_metric(
                        chart_hooks=chart_hooks,
                        metric=metric,
                    ),
                }
            )

    season_to_date = league_relative.get("season_to_date_metrics", {})
    if isinstance(season_to_date, dict) and season_to_date:
        ranked = sorted(
            (
                (metric, values)
                for metric, values in season_to_date.items()
                if isinstance(values, dict)
                and _as_float(values.get("high_rank")) is not None
                and _as_float(values.get("teams_with_value")) is not None
            ),
            key=lambda item: (
                int(float(item[1]["high_rank"])),
                -abs(float(item[1].get("delta_vs_peer_avg", 0.0))),
            ),
        )
        if ranked:
            metric, values = ranked[0]
            pegs.append(
                {
                    "id": f"season-peer-rank-{metric}",
                    "title": f"{_metric_label(metric).title()} season-to-date peer rank",
                    "peg_type": "season-trend",
                    "summary": (
                        f"{_metric_label(metric)} ranks "
                        f"{int(float(values['high_rank']))}/{int(float(values['teams_with_value']))} "
                        "on season-to-date peer average."
                    ),
                    "evidence_metrics": [metric],
                    "evidence_notes": [],
                    "confidence": _clamp_story_confidence(base_confidence, degrade=1),
                    "chart_hook_ids": _find_chart_hooks_for_metric(
                        chart_hooks=chart_hooks,
                        metric=metric,
                    ),
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for peg in pegs:
        peg_id = str(peg.get("id", "")).strip()
        if not peg_id or peg_id in seen:
            continue
        seen.add(peg_id)
        deduped.append(peg)
    return deduped[:8]


def _extract_anomalies(
    *,
    findings: list[dict[str, Any]],
    week: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        weeks = finding.get("weeks") or []
        scope = "season"
        include = not weeks
        if weeks:
            include = week in {int(value) for value in weeks if str(value).isdigit()}
            if include:
                scope = "week"
        if not include:
            continue
        out.append(
            {
                "kind": str(finding.get("kind", "")),
                "description": str(finding.get("summary", "")),
                "severity": str(finding.get("severity", "info")),
                "scope": scope,
            }
        )
    return out


def _load_extra_context(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("--extra-json must be a JSON object.")
    return loaded


def _merge_extra_context(
    context: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    out = dict(context)
    if not extra:
        return out
    if isinstance(extra.get("meta"), dict):
        merged = dict(out.get("meta", {}))
        merged.update(extra["meta"])
        out["meta"] = merged
    if isinstance(extra.get("match"), dict):
        merged = dict(out.get("match", {}))
        merged.update(extra["match"])
        out["match"] = merged
    if isinstance(extra.get("deltas_vs_season_avg"), dict):
        merged = dict(out.get("deltas_vs_season_avg", {}))
        merged.update(extra["deltas_vs_season_avg"])
        out["deltas_vs_season_avg"] = merged
    if isinstance(extra.get("largest_upward_deltas"), list):
        out["largest_upward_deltas"] = list(extra["largest_upward_deltas"])
    if isinstance(extra.get("largest_downward_deltas"), list):
        out["largest_downward_deltas"] = list(extra["largest_downward_deltas"])
    if isinstance(extra.get("season_rankings"), dict):
        merged = dict(out.get("season_rankings", {}))
        merged.update(extra["season_rankings"])
        out["season_rankings"] = merged
    if isinstance(extra.get("league_relative"), dict):
        merged = dict(out.get("league_relative", {}))
        merged.update(extra["league_relative"])
        out["league_relative"] = merged
    if isinstance(extra.get("context_quality"), dict):
        merged = dict(out.get("context_quality", {}))
        merged.update(extra["context_quality"])
        out["context_quality"] = merged
    if isinstance(extra.get("rankings"), dict):
        merged = dict(out.get("rankings", {}))
        merged.update(extra["rankings"])
        out["rankings"] = merged
    if isinstance(extra.get("chart_hooks"), list):
        hooks = list(out.get("chart_hooks", []))
        hooks.extend(extra["chart_hooks"])
        out["chart_hooks"] = hooks
    if isinstance(extra.get("story_pegs"), list):
        pegs = list(out.get("story_pegs", []))
        pegs.extend(extra["story_pegs"])
        out["story_pegs"] = pegs
    if isinstance(extra.get("context_window"), dict):
        merged = dict(out.get("context_window", {}))
        merged.update(extra["context_window"])
        out["context_window"] = merged
    if isinstance(extra.get("provenance"), dict):
        merged = dict(out.get("provenance", {}))
        merged.update(extra["provenance"])
        out["provenance"] = merged
    if isinstance(extra.get("anomalies"), list):
        anomalies = list(out.get("anomalies", []))
        anomalies.extend(extra["anomalies"])
        out["anomalies"] = anomalies
    if isinstance(extra.get("data_gaps"), list):
        data_gaps = list(out.get("data_gaps", []))
        data_gaps.extend(str(value) for value in extra["data_gaps"])
        out["data_gaps"] = data_gaps
    if isinstance(extra.get("notes"), list):
        out["notes"] = list(extra["notes"])
    return out


def default_context_path(
    *,
    report_path: Path,
    team: str,
    season: str,
    week: int,
    report_date: str,
) -> Path:
    base = (
        f"weekly-context-{_slug(team)}-{season.replace('-', '')}-w{week}-{report_date}.json"
    )
    return report_path.parent / base


def build_weekly_context(
    *,
    report: dict[str, Any],
    team: str | None = None,
    season: str | None = None,
    week: int | None = None,
    metrics: list[str] | None = None,
    window: int = 5,
    schedule_json: str | None = None,
) -> dict[str, Any]:
    team_block = _select_team_block(report, team)
    season_block = _select_season_block(team_block, season)
    weekly_rows = season_block.get("weekly_rows")
    if not isinstance(weekly_rows, list):
        raise ValueError("Season block missing weekly_rows.")
    if not weekly_rows:
        raise ValueError("Selected season has empty weekly_rows.")

    current = _select_week_row(weekly_rows, week)
    selected_team = str(team_block.get("team", ""))
    selected_season = str(season_block.get("season", ""))
    current_week = int(current["week"])

    input_block = report.get("input", {})
    report_metrics = input_block.get("metrics", [])
    fallback_metrics = (
        [str(value) for value in report_metrics if str(value).strip()]
        if isinstance(report_metrics, list)
        else []
    )
    metric_list = metrics if metrics is not None else fallback_metrics

    goal_for = _as_float(current.get("goals_for"))
    goal_against = _as_float(current.get("goals_against"))
    score = None
    if goal_for is not None and goal_against is not None:
        score = f"{int(goal_for)}-{int(goal_against)}"

    deltas = _compute_deltas(
        rows=weekly_rows,
        current_row=current,
        metrics=metric_list,
    )
    week_extremes = _compute_week_extremes(
        rows=weekly_rows,
        current_row=current,
        metrics=metric_list,
    )
    directional_deltas = _summarize_directional_deltas(deltas)
    form_snapshot = _compute_form_snapshot(
        rows=weekly_rows,
        current_week=current_week,
        window=window,
    )
    trend_summary = _compute_trend_summary(
        rows=weekly_rows,
        current_week=current_week,
        window=window,
        metrics=metric_list,
    )
    data_gaps: list[str] = []
    season_rankings = _compute_season_rankings(
        rows=weekly_rows,
        current_row=current,
        metrics=metric_list,
    )
    league_relative = _compute_league_relative(
        report=report,
        team=selected_team,
        season=selected_season,
        current_week=current_week,
        current_row=current,
        metrics=metric_list,
        window=window,
        data_gaps=data_gaps,
    )
    context_quality = _compute_context_quality(
        metric_list=metric_list,
        trend_summary=trend_summary,
        season_rankings=season_rankings,
        league_relative=league_relative,
        data_gaps=data_gaps,
        window=window,
    )
    week_flags = _compute_week_flags(
        weekly_rows=weekly_rows,
        current_row=current,
        metrics=metric_list,
        deltas=deltas,
    )
    if isinstance(league_relative, dict):
        movers = league_relative.get("top_percentile_movers")
        if isinstance(movers, dict):
            week_flags.extend(_build_percentile_mover_flags(movers))
    deduped_week_flags: list[str] = []
    seen_week_flags: set[str] = set()
    for flag in week_flags:
        if flag in seen_week_flags:
            continue
        seen_week_flags.add(flag)
        deduped_week_flags.append(flag)
    week_flags = deduped_week_flags[:7]
    anomalies = _extract_anomalies(
        findings=list(season_block.get("findings", [])),
        week=current_week,
    )
    chart_hooks = _build_chart_hooks(
        current_week=current_week,
        form_snapshot=form_snapshot,
        deltas=deltas,
        trend_summary=trend_summary,
        week_extremes=week_extremes,
        league_relative=league_relative,
    )
    story_pegs = _build_story_pegs(
        week_extremes=week_extremes,
        deltas=deltas,
        league_relative=league_relative,
        anomalies=anomalies,
        chart_hooks=chart_hooks,
        context_quality=context_quality,
        week_flags=week_flags,
    )

    context = {
        "meta": {
            "team": selected_team,
            "season": selected_season,
            "week": current_week,
            "report_date": str(report.get("report_date", "")),
            "competition": str(input_block.get("competition_code", "")),
        },
        "match": {
            "opponent": str(current.get("opponent", "")),
            "result": _result_short(str(current.get("result", ""))),
            "score": score,
            "venue": str(current.get("venue", "")),
        },
        "form_snapshot": form_snapshot,
        "deltas_vs_season_avg": deltas,
        "largest_upward_deltas": directional_deltas["largest_upward_deltas"],
        "largest_downward_deltas": directional_deltas["largest_downward_deltas"],
        "trend_summary": trend_summary,
        "week_flags": week_flags,
        "week_extremes": week_extremes,
        "season_rankings": season_rankings,
        "league_relative": league_relative,
        "context_quality": context_quality,
        "rankings": {},
        "anomalies": anomalies,
        "context_window": _compute_context_window(
            rows=weekly_rows,
            current_week=current_week,
            window=window,
        ),
        "chart_hooks": chart_hooks,
        "story_pegs": story_pegs,
        "available_metrics": metric_list,
        "data_gaps": data_gaps,
        "provenance": {
            "source": str(input_block.get("db_path", "")),
            "generated_by": "e0_weekly_context_export.py",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "report_json": "",
        },
    }
    schedule_path = _resolve_schedule_path(
        explicit_schedule_json=schedule_json,
        team=selected_team,
        season=selected_season,
    )
    if schedule_path is not None and schedule_path.exists():
        schedule_rows = _load_schedule_rows(schedule_path)
        next_fixture = _extract_next_fixture(
            schedule_rows=schedule_rows,
            current_week=current_week,
        )
        if next_fixture is not None:
            context["next_fixture"] = next_fixture
            context["provenance"]["schedule_json"] = str(schedule_path)
            opponent_lookup_name = str(
                next_fixture.get("opponent_canonical_name")
                or next_fixture.get("opponent")
                or ""
            )
            opponent_last_week = _build_opponent_last_week_context(
                report=report,
                season=selected_season,
                opponent_name=opponent_lookup_name,
                current_week=current_week,
            )
            if opponent_last_week is not None:
                context["next_opponent_last_week"] = opponent_last_week
            opponent_block = _find_team_block_by_name(report, opponent_lookup_name)
            if opponent_block is not None:
                opponent_season = _find_season_block(opponent_block, selected_season)
                if opponent_season is not None:
                    opponent_rows = opponent_season.get("weekly_rows")
                    if isinstance(opponent_rows, list) and opponent_rows:
                        opponent_recent_form = _build_recent_form_summary(
                            rows=opponent_rows,
                            current_week=current_week,
                            window=window,
                        )
                        if opponent_recent_form is not None:
                            context["next_opponent_recent_form"] = {
                                "team": str(opponent_block.get("team", opponent_lookup_name)),
                                **opponent_recent_form,
                            }
                            team_recent_form = _build_recent_form_summary(
                                rows=weekly_rows,
                                current_week=current_week,
                                window=window,
                            )
                            if team_recent_form is not None:
                                context["next_week_matchup_lens"] = _build_next_week_matchup_lens(
                                    team_form=team_recent_form,
                                    opponent_form=opponent_recent_form,
                                )
        else:
            context["data_gaps"].append(
                "No upcoming fixture found in schedule after selected week."
            )
    else:
        context["data_gaps"].append("No schedule file found for next-fixture context.")
    if isinstance(current.get("annotation"), dict):
        context["annotations_for_week"] = [dict(current["annotation"])]
    return context


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export compact 'this week' context JSON for LLM ideation."
    )
    parser.add_argument(
        "--report-json",
        required=True,
        help="Input weekly report JSON from e0_weekly_report_data/run.",
    )
    parser.add_argument(
        "--team",
        default=None,
        help="Optional team override. Defaults to first team in report.",
    )
    parser.add_argument(
        "--season",
        default=None,
        help="Optional season override. Defaults to latest season for selected team.",
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="Optional target week. Defaults to latest available week in selected season.",
    )
    parser.add_argument(
        "--metrics",
        default=None,
        help="Optional comma-delimited metrics for delta calculation.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=5,
        help="Recent-form window size (last N matches up to selected week).",
    )
    parser.add_argument(
        "--schedule-json",
        default="",
        help=(
            "Optional schedule JSON path for next-fixture enrichment. "
            "If omitted, auto-detects data/<team>-epl/<team>-schedule-<season>.normalized.json."
        ),
    )
    parser.add_argument(
        "--extra-json",
        default=None,
        help="Optional JSON object merged into context (rankings/deltas/anomalies/etc).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path. Defaults near report-json as weekly-context-...json.",
    )
    parser.add_argument(
        "--compact",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write compact JSON (default pretty).",
    )
    args = parser.parse_args()
    if args.window <= 0:
        raise ValueError("--window must be > 0")

    report_path = Path(args.report_json)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    input_block = report.get("input", {})
    report_metrics = (
        [str(value) for value in input_block.get("metrics", []) if str(value).strip()]
        if isinstance(input_block.get("metrics"), list)
        else []
    )
    selected_metrics = _parse_metrics(args.metrics, fallback=report_metrics)

    context = build_weekly_context(
        report=report,
        team=args.team,
        season=args.season,
        week=args.week,
        metrics=selected_metrics,
        window=args.window,
        schedule_json=args.schedule_json or None,
    )
    context["provenance"]["report_json"] = str(report_path)
    extra = _load_extra_context(args.extra_json)
    context = _merge_extra_context(context, extra)

    meta = context["meta"]
    out_path = (
        Path(args.out)
        if args.out
        else default_context_path(
            report_path=report_path,
            team=str(meta["team"]),
            season=str(meta["season"]),
            week=int(meta["week"]),
            report_date=str(meta["report_date"]),
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(context, separators=(",", ":"))
        if args.compact
        else json.dumps(context, indent=2)
    )
    out_path.write_text(text + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Team: {meta['team']}")
    print(f"Season: {meta['season']}")
    print(f"Week: {meta['week']}")
    print(f"Metrics: {', '.join(selected_metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
