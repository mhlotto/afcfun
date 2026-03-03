#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


_SEASON_RE = re.compile(r"^(\d{4})[-_/]?(\d{4})$")


def _team_key(team: str) -> str:
    return " ".join(team.strip().lower().split())


def _normalize_season(value: object) -> str:
    if value is None:
        return "*"
    text = str(value).strip()
    if not text:
        return "*"
    match = _SEASON_RE.match(text)
    if not match:
        return text
    return f"{int(match.group(1)):04d}-{int(match.group(2)):04d}"


def _normalize_week(value: object) -> int:
    try:
        week = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid annotation week value: {value!r}") from exc
    if week <= 0:
        raise ValueError("Annotation week must be a positive integer.")
    return week


def _normalize_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Annotation payload must be an object.")
    out: dict[str, str] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, (str, int, float, bool)):
            out[str(key)] = str(item)
        else:
            out[str(key)] = json.dumps(item, separators=(",", ":"))
    return out


def load_weekly_annotations(
    path: str | None,
) -> dict[tuple[str, str, int], dict[str, str]]:
    if not path:
        return {}
    raw = Path(path).read_text(encoding="utf-8")
    loaded = json.loads(raw)
    out: dict[tuple[str, str, int], dict[str, str]] = {}

    def add_entry(team: object, season: object, week: object, payload: object) -> None:
        team_text = str(team).strip()
        if not team_text:
            raise ValueError("Annotation entry requires non-empty team.")
        season_norm = _normalize_season(season)
        week_num = _normalize_week(week)
        out[(_team_key(team_text), season_norm, week_num)] = _normalize_payload(payload)

    if isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
        for item in loaded["entries"]:
            if not isinstance(item, dict):
                raise ValueError("Each annotation entry must be an object.")
            payload = dict(item)
            team = payload.pop("team", None)
            season = payload.pop("season", None)
            week = payload.pop("week", None)
            add_entry(team, season, week, payload)
        return out

    if isinstance(loaded, list):
        for item in loaded:
            if not isinstance(item, dict):
                raise ValueError("Each annotation entry must be an object.")
            payload = dict(item)
            team = payload.pop("team", None)
            season = payload.pop("season", None)
            week = payload.pop("week", None)
            add_entry(team, season, week, payload)
        return out

    if isinstance(loaded, dict):
        for team, by_key in loaded.items():
            if not isinstance(by_key, dict):
                raise ValueError("Annotation mapping must use object values.")
            looks_like_season_map = any(
                _SEASON_RE.match(str(key).strip()) for key in by_key.keys()
            )
            if looks_like_season_map:
                for season, by_week in by_key.items():
                    if not isinstance(by_week, dict):
                        raise ValueError("Season annotation block must be an object.")
                    for week, payload in by_week.items():
                        add_entry(team, season, week, payload)
            else:
                for week, payload in by_key.items():
                    add_entry(team, "*", week, payload)
        return out

    raise ValueError(
        "Annotations config must be a list, object with 'entries', "
        "or team->(season->week|week)->payload mapping."
    )


def apply_weekly_annotations(
    report: dict[str, object],
    annotations: dict[tuple[str, str, int], dict[str, str]],
) -> int:
    if not annotations:
        return 0
    applied = 0
    applied_entries: list[dict[str, object]] = []
    teams = report.get("teams")
    if not isinstance(teams, list):
        return 0

    for team_block in teams:
        if not isinstance(team_block, dict):
            continue
        team = str(team_block.get("team", "")).strip()
        if not team:
            continue
        team_norm = _team_key(team)
        seasons = team_block.get("seasons")
        if not isinstance(seasons, list):
            continue
        for season_block in seasons:
            if not isinstance(season_block, dict):
                continue
            season = str(season_block.get("season", "")).strip()
            weekly_rows = season_block.get("weekly_rows")
            if not isinstance(weekly_rows, list):
                continue
            for row in weekly_rows:
                if not isinstance(row, dict):
                    continue
                week_raw = row.get("week")
                try:
                    week = int(week_raw)
                except (TypeError, ValueError):
                    continue
                payload = annotations.get((team_norm, season, week))
                if payload is None:
                    payload = annotations.get((team_norm, "*", week))
                if payload is None:
                    continue
                row["annotation"] = dict(payload)
                applied += 1
                applied_entries.append(
                    {
                        "team": team,
                        "season": season,
                        "week": week,
                        "payload": dict(payload),
                    }
                )
    if applied_entries:
        report["annotations"] = applied_entries
    return applied
