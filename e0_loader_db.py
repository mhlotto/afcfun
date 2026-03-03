#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from e0_multi_season import infer_season_label
from e0_season_utils import normalize_season_token


_HISTORIC_E0_RE = re.compile(r"^E0-(\d{4})(\d{4})\.csv$")
_COMPETITION_NAMES = {"E0": "Premier League"}


@dataclass(frozen=True)
class E0IngestSummary:
    source_id: int
    competition_code: str
    season_label: str
    source_key: str
    csv_path: str
    rows_processed: int
    matches_upserted: int
    team_stats_upserted: int


@dataclass(frozen=True)
class E0SourcePlan:
    csv_path: str
    competition_code: str
    season_label: str
    source_key: str
    row_count: int
    checksum_sha256: str
    file_mtime_utc: str


def discover_e0_csv_files(
    data_dir: str | Path,
    *,
    pattern: str = "E0*.csv",
) -> list[Path]:
    root = Path(data_dir)
    if not root.exists():
        raise ValueError(f"Data directory does not exist: {root}")
    files = sorted(path for path in root.glob(pattern) if path.is_file())
    filtered = [
        path
        for path in files
        if path.name == "E0.csv" or _HISTORIC_E0_RE.match(path.name)
    ]
    return filtered


def plan_e0_csv(
    csv_path: str | Path,
    *,
    season_label_override: str | None = None,
    source_key_override: str | None = None,
) -> E0SourcePlan:
    path = Path(csv_path)
    rows = _read_rows(path)
    if not rows:
        raise ValueError(f"No CSV rows found in {path}")
    competition_code = _competition_code_from_rows(rows)
    season_label = _season_label_from_path_or_data(path, season_label_override)
    source_key = source_key_override or f"{competition_code}:{season_label}"
    return E0SourcePlan(
        csv_path=str(path),
        competition_code=competition_code,
        season_label=season_label,
        source_key=source_key,
        row_count=len(rows),
        checksum_sha256=_sha256_file(path),
        file_mtime_utc=_file_mtime_utc(path),
    )


def delete_source_by_key(
    conn: sqlite3.Connection,
    *,
    loader_name: str,
    source_key: str,
) -> int:
    row = conn.execute(
        "SELECT id FROM sources WHERE loader_name = ? AND source_key = ?",
        (loader_name, source_key),
    ).fetchone()
    if row is None:
        return 0
    source_id = int(row["id"])
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    return source_id


def ingest_e0_paths(
    conn: sqlite3.Connection,
    csv_paths: Iterable[str | Path],
    *,
    loader_name: str = "football-data-e0",
    source_scope: str = "football-data.co.uk",
    season_label_override: str | None = None,
    replace_source: bool = False,
) -> list[E0IngestSummary]:
    summaries: list[E0IngestSummary] = []
    for csv_path in csv_paths:
        summary = ingest_e0_csv(
            conn,
            csv_path,
            loader_name=loader_name,
            source_scope=source_scope,
            season_label_override=season_label_override,
            replace_source=replace_source,
        )
        summaries.append(summary)
    return summaries


def ingest_e0_csv(
    conn: sqlite3.Connection,
    csv_path: str | Path,
    *,
    loader_name: str = "football-data-e0",
    source_scope: str = "football-data.co.uk",
    season_label_override: str | None = None,
    source_key_override: str | None = None,
    replace_source: bool = False,
) -> E0IngestSummary:
    path = Path(csv_path)
    rows = _read_rows(path)
    if not rows:
        raise ValueError(f"No CSV rows found in {path}")

    plan = plan_e0_csv(
        path,
        season_label_override=season_label_override,
        source_key_override=source_key_override,
    )

    with conn:
        if replace_source:
            delete_source_by_key(
                conn,
                loader_name=loader_name,
                source_key=plan.source_key,
            )
        source_id = _upsert_source(
            conn,
            loader_name=loader_name,
            source_key=plan.source_key,
            file_path=str(path),
            checksum_sha256=plan.checksum_sha256,
            file_mtime_utc=plan.file_mtime_utc,
            row_count=len(rows),
        )
        competition_id = _get_or_create_competition(conn, plan.competition_code)
        season_id = _get_or_create_season(conn, competition_id, plan.season_label)

        for row_num, row in enumerate(rows, start=1):
            row_json = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            row_hash = hashlib.sha256(f"{row_num}|{row_json}".encode("utf-8")).hexdigest()
            raw_row_id = _upsert_raw_row(conn, source_id, row_num, row_hash, row_json)

            home_name = (row.get("HomeTeam") or "").strip()
            away_name = (row.get("AwayTeam") or "").strip()
            if not home_name or not away_name:
                raise ValueError(
                    f"Missing HomeTeam/AwayTeam at {path}:{row_num}"
                )
            home_team_id = _get_or_create_team(conn, home_name)
            away_team_id = _get_or_create_team(conn, away_name)

            match_id = _upsert_match(
                conn,
                source_id=source_id,
                raw_row_id=raw_row_id,
                competition_id=competition_id,
                season_id=season_id,
                row=row,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
            )

            home_stats = _stats_for_team(row, is_home=True)
            away_stats = _stats_for_team(row, is_home=False)

            _upsert_team_match_stats(
                conn,
                match_id=match_id,
                source_id=source_id,
                competition_id=competition_id,
                season_id=season_id,
                row=row,
                team_id=home_team_id,
                opponent_team_id=away_team_id,
                stats=home_stats,
            )
            _upsert_team_match_stats(
                conn,
                match_id=match_id,
                source_id=source_id,
                competition_id=competition_id,
                season_id=season_id,
                row=row,
                team_id=away_team_id,
                opponent_team_id=home_team_id,
                stats=away_stats,
            )

    return E0IngestSummary(
        source_id=source_id,
        competition_code=plan.competition_code,
        season_label=plan.season_label,
        source_key=plan.source_key,
        csv_path=str(path),
        rows_processed=len(rows),
        matches_upserted=len(rows),
        team_stats_upserted=len(rows) * 2,
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _competition_code_from_rows(rows: list[dict[str, str]]) -> str:
    for row in rows:
        value = (row.get("Div") or "").strip()
        if value:
            return value
    return "E0"


def _season_label_from_path_or_data(
    path: Path,
    season_label_override: str | None,
) -> str:
    if season_label_override:
        return normalize_season_token(season_label_override)
    match = _HISTORIC_E0_RE.match(path.name)
    if match:
        return normalize_season_token(match.group(1) + match.group(2))
    return infer_season_label(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _file_mtime_utc(path: Path) -> str:
    timestamp = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _upsert_source(
    conn: sqlite3.Connection,
    *,
    loader_name: str,
    source_key: str,
    file_path: str,
    checksum_sha256: str,
    file_mtime_utc: str,
    row_count: int,
) -> int:
    conn.execute(
        """
        INSERT INTO sources(
            loader_name, source_key, file_path, checksum_sha256,
            file_mtime_utc, row_count, ingested_at_utc
        ) VALUES(
            ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        )
        ON CONFLICT(loader_name, source_key) DO UPDATE SET
            file_path = excluded.file_path,
            checksum_sha256 = excluded.checksum_sha256,
            file_mtime_utc = excluded.file_mtime_utc,
            row_count = excluded.row_count,
            ingested_at_utc = excluded.ingested_at_utc
        """,
        (
            loader_name,
            source_key,
            file_path,
            checksum_sha256,
            file_mtime_utc,
            row_count,
        ),
    )
    row = conn.execute(
        "SELECT id FROM sources WHERE loader_name = ? AND source_key = ?",
        (loader_name, source_key),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert source row.")
    return int(row["id"])


def _upsert_raw_row(
    conn: sqlite3.Connection,
    source_id: int,
    row_num: int,
    row_hash: str,
    row_json: str,
) -> int:
    conn.execute(
        """
        INSERT INTO raw_rows(source_id, row_num, row_hash, row_json, ingested_at_utc)
        VALUES(?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        ON CONFLICT(source_id, row_hash) DO UPDATE SET
            row_num = excluded.row_num,
            row_json = excluded.row_json,
            ingested_at_utc = excluded.ingested_at_utc
        """,
        (source_id, row_num, row_hash, row_json),
    )
    row = conn.execute(
        "SELECT id FROM raw_rows WHERE source_id = ? AND row_hash = ?",
        (source_id, row_hash),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert raw row.")
    return int(row["id"])


def _get_or_create_competition(conn: sqlite3.Connection, code: str) -> int:
    conn.execute(
        """
        INSERT INTO competitions(code, name)
        VALUES(?, ?)
        ON CONFLICT(code) DO UPDATE SET name = COALESCE(competitions.name, excluded.name)
        """,
        (code, _COMPETITION_NAMES.get(code)),
    )
    row = conn.execute(
        "SELECT id FROM competitions WHERE code = ?",
        (code,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to get competition row.")
    return int(row["id"])


def _parse_season_years(label: str) -> tuple[int, int]:
    start = int(label[:4])
    end = int(label[5:])
    return start, end


def _get_or_create_season(
    conn: sqlite3.Connection,
    competition_id: int,
    season_label: str,
) -> int:
    start, end = _parse_season_years(season_label)
    conn.execute(
        """
        INSERT INTO seasons(competition_id, start_year, end_year, label)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(competition_id, label) DO UPDATE SET
            start_year = excluded.start_year,
            end_year = excluded.end_year
        """,
        (competition_id, start, end, season_label),
    )
    row = conn.execute(
        "SELECT id FROM seasons WHERE competition_id = ? AND label = ?",
        (competition_id, season_label),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to get season row.")
    return int(row["id"])


def _get_or_create_team(conn: sqlite3.Connection, canonical_name: str) -> int:
    conn.execute(
        """
        INSERT INTO teams(canonical_name)
        VALUES(?)
        ON CONFLICT(canonical_name) DO NOTHING
        """,
        (canonical_name,),
    )
    row = conn.execute(
        "SELECT id FROM teams WHERE canonical_name = ?",
        (canonical_name,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to get team row.")
    return int(row["id"])


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _expected_result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if away_goals > home_goals:
        return "A"
    return "D"


def _full_time_result(row: dict[str, str]) -> str | None:
    ftr = (row.get("FTR") or "").strip()
    if ftr in {"H", "A", "D"}:
        return ftr
    fthg = _as_int(row.get("FTHG"))
    ftag = _as_int(row.get("FTAG"))
    if fthg is None or ftag is None:
        return None
    return _expected_result(fthg, ftag)


def _half_time_result(row: dict[str, str]) -> str | None:
    htr = (row.get("HTR") or "").strip()
    if htr in {"H", "A", "D"}:
        return htr
    hthg = _as_int(row.get("HTHG"))
    htag = _as_int(row.get("HTAG"))
    if hthg is None or htag is None:
        return None
    return _expected_result(hthg, htag)


def _upsert_match(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    raw_row_id: int,
    competition_id: int,
    season_id: int,
    row: dict[str, str],
    home_team_id: int,
    away_team_id: int,
) -> int:
    match_date = (row.get("Date") or "").strip()
    if not match_date:
        raise ValueError("CSV row is missing Date.")
    match_time = (row.get("Time") or "").strip() or None
    conn.execute(
        """
        INSERT INTO matches(
            source_id, raw_row_id, competition_id, season_id,
            match_date, match_time, home_team_id, away_team_id,
            referee, attendance,
            full_time_home_goals, full_time_away_goals, full_time_result,
            half_time_home_goals, half_time_away_goals, half_time_result
        ) VALUES(
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(source_id, season_id, match_date, home_team_id, away_team_id)
        DO UPDATE SET
            raw_row_id = excluded.raw_row_id,
            competition_id = excluded.competition_id,
            match_time = excluded.match_time,
            referee = excluded.referee,
            attendance = excluded.attendance,
            full_time_home_goals = excluded.full_time_home_goals,
            full_time_away_goals = excluded.full_time_away_goals,
            full_time_result = excluded.full_time_result,
            half_time_home_goals = excluded.half_time_home_goals,
            half_time_away_goals = excluded.half_time_away_goals,
            half_time_result = excluded.half_time_result
        """,
        (
            source_id,
            raw_row_id,
            competition_id,
            season_id,
            match_date,
            match_time,
            home_team_id,
            away_team_id,
            (row.get("Referee") or "").strip() or None,
            _as_int(row.get("Attendance")),
            _as_int(row.get("FTHG")),
            _as_int(row.get("FTAG")),
            _full_time_result(row),
            _as_int(row.get("HTHG")),
            _as_int(row.get("HTAG")),
            _half_time_result(row),
        ),
    )
    item = conn.execute(
        """
        SELECT id
        FROM matches
        WHERE source_id = ?
          AND season_id = ?
          AND match_date = ?
          AND home_team_id = ?
          AND away_team_id = ?
        """,
        (source_id, season_id, match_date, home_team_id, away_team_id),
    ).fetchone()
    if item is None:
        raise RuntimeError("Failed to upsert match row.")
    return int(item["id"])


def _match_result_word(result: str | None, is_home: bool) -> str | None:
    if result not in {"H", "A", "D"}:
        return None
    if result == "D":
        return "draw"
    if is_home:
        return "win" if result == "H" else "loss"
    return "win" if result == "A" else "loss"


def _stats_for_team(row: dict[str, str], *, is_home: bool) -> dict[str, object]:
    if is_home:
        return {
            "venue": "home",
            "result": _match_result_word(_full_time_result(row), is_home=True),
            "total_goals": _as_int(row.get("FTHG")),
            "opponent_total_goals": _as_int(row.get("FTAG")),
            "halftime_goals": _as_int(row.get("HTHG")),
            "opponent_halftime_goals": _as_int(row.get("HTAG")),
            "shots": _as_int(row.get("HS")),
            "opponent_shots": _as_int(row.get("AS")),
            "shots_on_target": _as_int(row.get("HST")),
            "opponent_shots_on_target": _as_int(row.get("AST")),
            "hit_woodwork": _as_int(row.get("HHW")),
            "opponent_hit_woodwork": _as_int(row.get("AHW")),
            "corners": _as_int(row.get("HC")),
            "opponent_corners": _as_int(row.get("AC")),
            "fouls": _as_int(row.get("HF")),
            "opponent_fouls": _as_int(row.get("AF")),
            "free_kicks_conceded": _as_int(row.get("HFKC")),
            "opponent_free_kicks_conceded": _as_int(row.get("AFKC")),
            "offsides": _as_int(row.get("HO")),
            "opponent_offsides": _as_int(row.get("AO")),
            "yellow_cards": _as_int(row.get("HY")),
            "opponent_yellow_cards": _as_int(row.get("AY")),
            "red_cards": _as_int(row.get("HR")),
            "opponent_red_cards": _as_int(row.get("AR")),
            "bookings_points": _as_int(row.get("HBP")),
            "opponent_bookings_points": _as_int(row.get("ABP")),
        }
    return {
        "venue": "away",
        "result": _match_result_word(_full_time_result(row), is_home=False),
        "total_goals": _as_int(row.get("FTAG")),
        "opponent_total_goals": _as_int(row.get("FTHG")),
        "halftime_goals": _as_int(row.get("HTAG")),
        "opponent_halftime_goals": _as_int(row.get("HTHG")),
        "shots": _as_int(row.get("AS")),
        "opponent_shots": _as_int(row.get("HS")),
        "shots_on_target": _as_int(row.get("AST")),
        "opponent_shots_on_target": _as_int(row.get("HST")),
        "hit_woodwork": _as_int(row.get("AHW")),
        "opponent_hit_woodwork": _as_int(row.get("HHW")),
        "corners": _as_int(row.get("AC")),
        "opponent_corners": _as_int(row.get("HC")),
        "fouls": _as_int(row.get("AF")),
        "opponent_fouls": _as_int(row.get("HF")),
        "free_kicks_conceded": _as_int(row.get("AFKC")),
        "opponent_free_kicks_conceded": _as_int(row.get("HFKC")),
        "offsides": _as_int(row.get("AO")),
        "opponent_offsides": _as_int(row.get("HO")),
        "yellow_cards": _as_int(row.get("AY")),
        "opponent_yellow_cards": _as_int(row.get("HY")),
        "red_cards": _as_int(row.get("AR")),
        "opponent_red_cards": _as_int(row.get("HR")),
        "bookings_points": _as_int(row.get("ABP")),
        "opponent_bookings_points": _as_int(row.get("HBP")),
    }


def _upsert_team_match_stats(
    conn: sqlite3.Connection,
    *,
    match_id: int,
    source_id: int,
    competition_id: int,
    season_id: int,
    row: dict[str, str],
    team_id: int,
    opponent_team_id: int,
    stats: dict[str, object],
) -> None:
    match_date = (row.get("Date") or "").strip()
    conn.execute(
        """
        INSERT INTO team_match_stats(
            match_id, source_id, competition_id, season_id, match_date,
            team_id, opponent_team_id, venue, result,
            total_goals, opponent_total_goals,
            halftime_goals, opponent_halftime_goals,
            shots, opponent_shots,
            shots_on_target, opponent_shots_on_target,
            hit_woodwork, opponent_hit_woodwork,
            corners, opponent_corners,
            fouls, opponent_fouls,
            free_kicks_conceded, opponent_free_kicks_conceded,
            offsides, opponent_offsides,
            yellow_cards, opponent_yellow_cards,
            red_cards, opponent_red_cards,
            bookings_points, opponent_bookings_points
        ) VALUES(
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(match_id, team_id) DO UPDATE SET
            source_id = excluded.source_id,
            competition_id = excluded.competition_id,
            season_id = excluded.season_id,
            match_date = excluded.match_date,
            opponent_team_id = excluded.opponent_team_id,
            venue = excluded.venue,
            result = excluded.result,
            total_goals = excluded.total_goals,
            opponent_total_goals = excluded.opponent_total_goals,
            halftime_goals = excluded.halftime_goals,
            opponent_halftime_goals = excluded.opponent_halftime_goals,
            shots = excluded.shots,
            opponent_shots = excluded.opponent_shots,
            shots_on_target = excluded.shots_on_target,
            opponent_shots_on_target = excluded.opponent_shots_on_target,
            hit_woodwork = excluded.hit_woodwork,
            opponent_hit_woodwork = excluded.opponent_hit_woodwork,
            corners = excluded.corners,
            opponent_corners = excluded.opponent_corners,
            fouls = excluded.fouls,
            opponent_fouls = excluded.opponent_fouls,
            free_kicks_conceded = excluded.free_kicks_conceded,
            opponent_free_kicks_conceded = excluded.opponent_free_kicks_conceded,
            offsides = excluded.offsides,
            opponent_offsides = excluded.opponent_offsides,
            yellow_cards = excluded.yellow_cards,
            opponent_yellow_cards = excluded.opponent_yellow_cards,
            red_cards = excluded.red_cards,
            opponent_red_cards = excluded.opponent_red_cards,
            bookings_points = excluded.bookings_points,
            opponent_bookings_points = excluded.opponent_bookings_points
        """,
        (
            match_id,
            source_id,
            competition_id,
            season_id,
            match_date,
            team_id,
            opponent_team_id,
            stats["venue"],
            stats["result"],
            stats["total_goals"],
            stats["opponent_total_goals"],
            stats["halftime_goals"],
            stats["opponent_halftime_goals"],
            stats["shots"],
            stats["opponent_shots"],
            stats["shots_on_target"],
            stats["opponent_shots_on_target"],
            stats["hit_woodwork"],
            stats["opponent_hit_woodwork"],
            stats["corners"],
            stats["opponent_corners"],
            stats["fouls"],
            stats["opponent_fouls"],
            stats["free_kicks_conceded"],
            stats["opponent_free_kicks_conceded"],
            stats["offsides"],
            stats["opponent_offsides"],
            stats["yellow_cards"],
            stats["opponent_yellow_cards"],
            stats["red_cards"],
            stats["opponent_red_cards"],
            stats["bookings_points"],
            stats["opponent_bookings_points"],
        ),
    )
