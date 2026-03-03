#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable


SCHEMA_VERSION = 1


def open_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_db(db_path: str | Path) -> sqlite3.Connection:
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
    except Exception:
        conn.close()
        raise
    return conn


def apply_migrations(conn: sqlite3.Connection) -> None:
    _ensure_schema_version_table(conn)
    current = current_schema_version(conn)
    for version in sorted(_MIGRATIONS):
        if version <= current:
            continue
        with conn:
            _MIGRATIONS[version](conn)
            conn.execute(
                (
                    "INSERT INTO schema_version(version, applied_at_utc) "
                    "VALUES(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
                ),
                (version,),
            )


def current_schema_version(conn: sqlite3.Connection) -> int:
    _ensure_schema_version_table(conn)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_version")
    item = row.fetchone()
    if item is None:
        return 0
    return int(item["version"])


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    return [str(row["name"]) for row in rows.fetchall()]


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version(
            version INTEGER PRIMARY KEY,
            applied_at_utc TEXT NOT NULL
        )
        """
    )


def _migration_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sources(
            id INTEGER PRIMARY KEY,
            loader_name TEXT NOT NULL,
            source_key TEXT NOT NULL,
            file_path TEXT,
            checksum_sha256 TEXT,
            file_mtime_utc TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            ingested_at_utc TEXT NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE(loader_name, source_key)
        );

        CREATE TABLE IF NOT EXISTS raw_rows(
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            row_num INTEGER NOT NULL,
            row_hash TEXT NOT NULL,
            row_json TEXT NOT NULL,
            ingested_at_utc TEXT NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE(source_id, row_num),
            UNIQUE(source_id, row_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_raw_rows_source
            ON raw_rows(source_id, row_num);

        CREATE TABLE IF NOT EXISTS competitions(
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT
        );

        CREATE TABLE IF NOT EXISTS seasons(
            id INTEGER PRIMARY KEY,
            competition_id INTEGER NOT NULL
                REFERENCES competitions(id) ON DELETE RESTRICT,
            start_year INTEGER NOT NULL,
            end_year INTEGER NOT NULL,
            label TEXT NOT NULL,
            UNIQUE(competition_id, start_year, end_year),
            UNIQUE(competition_id, label)
        );

        CREATE INDEX IF NOT EXISTS idx_seasons_competition_years
            ON seasons(competition_id, start_year, end_year);

        CREATE TABLE IF NOT EXISTS teams(
            id INTEGER PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            short_name TEXT,
            country TEXT
        );

        CREATE TABLE IF NOT EXISTS team_aliases(
            id INTEGER PRIMARY KEY,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            alias_norm TEXT NOT NULL,
            source_scope TEXT NOT NULL DEFAULT '',
            is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
            UNIQUE(alias_norm, source_scope)
        );

        CREATE INDEX IF NOT EXISTS idx_team_aliases_team
            ON team_aliases(team_id);

        CREATE TABLE IF NOT EXISTS matches(
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            raw_row_id INTEGER REFERENCES raw_rows(id) ON DELETE SET NULL UNIQUE,
            competition_id INTEGER NOT NULL REFERENCES competitions(id),
            season_id INTEGER NOT NULL REFERENCES seasons(id),
            match_date TEXT NOT NULL,
            match_time TEXT,
            home_team_id INTEGER NOT NULL REFERENCES teams(id),
            away_team_id INTEGER NOT NULL REFERENCES teams(id),
            referee TEXT,
            attendance INTEGER,
            full_time_home_goals INTEGER,
            full_time_away_goals INTEGER,
            full_time_result TEXT,
            half_time_home_goals INTEGER,
            half_time_away_goals INTEGER,
            half_time_result TEXT,
            CHECK (home_team_id <> away_team_id),
            UNIQUE(source_id, season_id, match_date, home_team_id, away_team_id)
        );

        CREATE INDEX IF NOT EXISTS idx_matches_season_date
            ON matches(season_id, match_date);
        CREATE INDEX IF NOT EXISTS idx_matches_home_team
            ON matches(home_team_id, season_id, match_date);
        CREATE INDEX IF NOT EXISTS idx_matches_away_team
            ON matches(away_team_id, season_id, match_date);

        CREATE TABLE IF NOT EXISTS team_match_stats(
            id INTEGER PRIMARY KEY,
            match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
            source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            competition_id INTEGER NOT NULL REFERENCES competitions(id),
            season_id INTEGER NOT NULL REFERENCES seasons(id),
            match_date TEXT NOT NULL,
            team_id INTEGER NOT NULL REFERENCES teams(id),
            opponent_team_id INTEGER NOT NULL REFERENCES teams(id),
            venue TEXT NOT NULL CHECK (venue IN ('home', 'away')),
            result TEXT CHECK (result IN ('win', 'draw', 'loss')),
            total_goals INTEGER,
            opponent_total_goals INTEGER,
            halftime_goals INTEGER,
            opponent_halftime_goals INTEGER,
            shots INTEGER,
            opponent_shots INTEGER,
            shots_on_target INTEGER,
            opponent_shots_on_target INTEGER,
            hit_woodwork INTEGER,
            opponent_hit_woodwork INTEGER,
            corners INTEGER,
            opponent_corners INTEGER,
            fouls INTEGER,
            opponent_fouls INTEGER,
            free_kicks_conceded INTEGER,
            opponent_free_kicks_conceded INTEGER,
            offsides INTEGER,
            opponent_offsides INTEGER,
            yellow_cards INTEGER,
            opponent_yellow_cards INTEGER,
            red_cards INTEGER,
            opponent_red_cards INTEGER,
            bookings_points INTEGER,
            opponent_bookings_points INTEGER,
            UNIQUE(match_id, team_id),
            CHECK (team_id <> opponent_team_id)
        );

        CREATE INDEX IF NOT EXISTS idx_team_match_stats_team_season
            ON team_match_stats(team_id, season_id, match_date);
        CREATE INDEX IF NOT EXISTS idx_team_match_stats_opponent_season
            ON team_match_stats(opponent_team_id, season_id, match_date);
        CREATE INDEX IF NOT EXISTS idx_team_match_stats_result
            ON team_match_stats(result, season_id, team_id);
        """
    )


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migration_v1,
}

