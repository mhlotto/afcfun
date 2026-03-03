from pathlib import Path
import sqlite3

from footstat_db import SCHEMA_VERSION, current_schema_version, initialize_db, list_tables


def test_initialize_db_creates_v1_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    conn = initialize_db(db_path)
    try:
        tables = set(list_tables(conn))
        assert current_schema_version(conn) == SCHEMA_VERSION
    finally:
        conn.close()

    expected = {
        "schema_version",
        "sources",
        "raw_rows",
        "competitions",
        "seasons",
        "teams",
        "team_aliases",
        "matches",
        "team_match_stats",
    }
    assert expected.issubset(tables)


def test_initialize_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    conn1 = initialize_db(db_path)
    conn1.close()

    conn2 = initialize_db(db_path)
    try:
        version = current_schema_version(conn2)
        row = conn2.execute("SELECT COUNT(*) AS count FROM schema_version").fetchone()
    finally:
        conn2.close()

    assert version == SCHEMA_VERSION
    assert row is not None
    assert int(row["count"]) == 1


def test_team_aliases_unique_per_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    conn = initialize_db(db_path)
    try:
        with conn:
            conn.execute("INSERT INTO teams(canonical_name) VALUES(?)", ("Arsenal",))
            team_id = int(conn.execute("SELECT id FROM teams").fetchone()["id"])
            conn.execute(
                (
                    "INSERT INTO team_aliases(team_id, alias, alias_norm, source_scope) "
                    "VALUES(?, ?, ?, ?)"
                ),
                (team_id, "Arsenal FC", "arsenal fc", ""),
            )
        error_raised = False
        try:
            with conn:
                conn.execute(
                    (
                        "INSERT INTO team_aliases(team_id, alias, alias_norm, source_scope) "
                        "VALUES(?, ?, ?, ?)"
                    ),
                    (team_id, "Arsenal Football Club", "arsenal fc", ""),
                )
        except sqlite3.IntegrityError:
            error_raised = True
    finally:
        conn.close()

    assert error_raised
