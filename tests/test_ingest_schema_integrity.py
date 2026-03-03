from pathlib import Path
import sqlite3

from e0_loader_db import delete_source_by_key, ingest_e0_csv
from footstat_db import initialize_db


def _write_e0_csv(path: Path, rows: list[list[str]]) -> None:
    header = [
        "Div",
        "Date",
        "Time",
        "HomeTeam",
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
        "HTHG",
        "HTAG",
        "HTR",
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    assert row is not None
    return int(row["c"])


def test_ingest_rerun_same_file_is_idempotent(tmp_path: Path) -> None:
    csv_path = tmp_path / "E0-20252026.csv"
    _write_e0_csv(
        csv_path,
        [["E0", "17/08/2025", "15:00", "Chelsea", "Arsenal", "0", "1", "A", "0", "0", "D"]],
    )
    db_path = tmp_path / "footstat.sqlite3"

    conn = initialize_db(db_path)
    try:
        ingest_e0_csv(conn, csv_path)
        ingest_e0_csv(conn, csv_path)
        assert _table_count(conn, "sources") == 1
        assert _table_count(conn, "raw_rows") == 1
        assert _table_count(conn, "matches") == 1
        assert _table_count(conn, "team_match_stats") == 2
    finally:
        conn.close()


def test_delete_source_cascades_and_keeps_fk_integrity(tmp_path: Path) -> None:
    csv_path = tmp_path / "E0-20252026.csv"
    _write_e0_csv(
        csv_path,
        [
            ["E0", "17/08/2025", "15:00", "Chelsea", "Arsenal", "0", "1", "A", "0", "0", "D"],
            ["E0", "24/08/2025", "15:00", "Arsenal", "Everton", "2", "0", "H", "1", "0", "H"],
        ],
    )
    db_path = tmp_path / "footstat.sqlite3"

    conn = initialize_db(db_path)
    try:
        ingest_e0_csv(conn, csv_path)
        assert _table_count(conn, "sources") == 1
        assert _table_count(conn, "raw_rows") == 2
        assert _table_count(conn, "matches") == 2
        assert _table_count(conn, "team_match_stats") == 4

        deleted = delete_source_by_key(
            conn,
            loader_name="football-data-e0",
            source_key="E0:2025-2026",
        )
        assert deleted > 0

        assert _table_count(conn, "sources") == 0
        assert _table_count(conn, "raw_rows") == 0
        assert _table_count(conn, "matches") == 0
        assert _table_count(conn, "team_match_stats") == 0

        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not fk_rows
    finally:
        conn.close()


def test_schema_constraints_reject_invalid_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    conn = initialize_db(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO competitions(code, name) VALUES(?, ?)",
                ("E0", "Premier League"),
            )
            competition_id = int(
                conn.execute("SELECT id FROM competitions WHERE code='E0'").fetchone()["id"]
            )
            conn.execute(
                (
                    "INSERT INTO seasons(competition_id, start_year, end_year, label) "
                    "VALUES(?, ?, ?, ?)"
                ),
                (competition_id, 2025, 2026, "2025-2026"),
            )
            season_id = int(conn.execute("SELECT id FROM seasons").fetchone()["id"])
            conn.execute(
                (
                    "INSERT INTO sources(loader_name, source_key, row_count, ingested_at_utc) "
                    "VALUES(?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
                ),
                ("test-loader", "E0:2025-2026", 0),
            )
            source_id = int(conn.execute("SELECT id FROM sources").fetchone()["id"])
            conn.execute("INSERT INTO teams(canonical_name) VALUES(?)", ("Arsenal",))
            team_id = int(conn.execute("SELECT id FROM teams").fetchone()["id"])

        invalid_match_failed = False
        try:
            with conn:
                conn.execute(
                    (
                        "INSERT INTO matches("
                        "source_id, competition_id, season_id, match_date, "
                        "home_team_id, away_team_id"
                        ") VALUES(?, ?, ?, ?, ?, ?)"
                    ),
                    (source_id, competition_id, season_id, "17/08/2025", team_id, team_id),
                )
        except sqlite3.IntegrityError:
            invalid_match_failed = True
        assert invalid_match_failed

        with conn:
            conn.execute("INSERT INTO teams(canonical_name) VALUES(?)", ("Chelsea",))
            opponent_id = int(
                conn.execute("SELECT id FROM teams WHERE canonical_name='Chelsea'").fetchone()["id"]
            )
            conn.execute(
                (
                    "INSERT INTO matches("
                    "source_id, competition_id, season_id, match_date, "
                    "home_team_id, away_team_id"
                    ") VALUES(?, ?, ?, ?, ?, ?)"
                ),
                (source_id, competition_id, season_id, "18/08/2025", team_id, opponent_id),
            )
            match_id = int(conn.execute("SELECT id FROM matches").fetchone()["id"])

        invalid_stats_failed = False
        try:
            with conn:
                conn.execute(
                    (
                        "INSERT INTO team_match_stats("
                        "match_id, source_id, competition_id, season_id, match_date, "
                        "team_id, opponent_team_id, venue"
                        ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (match_id, source_id, competition_id, season_id, "18/08/2025", team_id, team_id, "home"),
                )
        except sqlite3.IntegrityError:
            invalid_stats_failed = True
        assert invalid_stats_failed

        fk_failed = False
        try:
            with conn:
                conn.execute(
                    (
                        "INSERT INTO team_match_stats("
                        "match_id, source_id, competition_id, season_id, match_date, "
                        "team_id, opponent_team_id, venue"
                        ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (99999, source_id, competition_id, season_id, "18/08/2025", team_id, opponent_id, "home"),
                )
        except sqlite3.IntegrityError:
            fk_failed = True
        assert fk_failed
    finally:
        conn.close()

