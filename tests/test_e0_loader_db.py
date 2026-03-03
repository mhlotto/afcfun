from pathlib import Path

from e0_loader_db import ingest_e0_csv
from footstat_db import initialize_db
from footstat_repo import FootstatRepo


def _write_e0_csv(path: Path) -> None:
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
        "HS",
        "AS",
        "HST",
        "AST",
        "HC",
        "AC",
        "HF",
        "AF",
        "HY",
        "AY",
        "HR",
        "AR",
        "Attendance",
        "Referee",
    ]
    rows = [
        [
            "E0",
            "17/08/2025",
            "15:00",
            "Chelsea",
            "Arsenal",
            "0",
            "1",
            "A",
            "0",
            "0",
            "D",
            "12",
            "10",
            "3",
            "4",
            "5",
            "3",
            "11",
            "9",
            "3",
            "2",
            "0",
            "0",
            "61000",
            "Ref A",
        ],
        [
            "E0",
            "24/08/2025",
            "15:00",
            "Arsenal",
            "Everton",
            "2",
            "0",
            "H",
            "1",
            "0",
            "H",
            "16",
            "7",
            "6",
            "2",
            "8",
            "4",
            "6",
            "14",
            "1",
            "2",
            "0",
            "0",
            "60200",
            "Ref B",
        ],
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_ingest_e0_csv_populates_tables_and_repo_reads(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    csv_path = tmp_path / "E0-20252026.csv"
    _write_e0_csv(csv_path)

    conn = initialize_db(db_path)
    try:
        summary = ingest_e0_csv(conn, csv_path)
        repo = FootstatRepo(conn)
        arsenal_rows = repo.fetch_normalized_team_rows(
            "Arsenal",
            competition_code="E0",
            seasons=["2025-2026"],
        )
        counts = {
            "sources": int(conn.execute("SELECT COUNT(*) AS c FROM sources").fetchone()["c"]),
            "raw_rows": int(conn.execute("SELECT COUNT(*) AS c FROM raw_rows").fetchone()["c"]),
            "matches": int(conn.execute("SELECT COUNT(*) AS c FROM matches").fetchone()["c"]),
            "team_match_stats": int(
                conn.execute("SELECT COUNT(*) AS c FROM team_match_stats").fetchone()["c"]
            ),
            "teams": int(conn.execute("SELECT COUNT(*) AS c FROM teams").fetchone()["c"]),
        }
    finally:
        conn.close()

    assert summary.competition_code == "E0"
    assert summary.season_label == "2025-2026"
    assert summary.rows_processed == 2
    assert summary.matches_upserted == 2
    assert summary.team_stats_upserted == 4
    assert counts == {
        "sources": 1,
        "raw_rows": 2,
        "matches": 2,
        "team_match_stats": 4,
        "teams": 3,
    }
    assert len(arsenal_rows) == 2
    assert arsenal_rows[0]["venue"] == "away"
    assert arsenal_rows[0]["total_goals"] == 1
    assert arsenal_rows[0]["opponent_total_goals"] == 0
    assert arsenal_rows[1]["venue"] == "home"
    assert arsenal_rows[1]["shots"] == 16
    assert arsenal_rows[1]["result"] == "win"


def test_ingest_e0_csv_is_idempotent_for_reruns(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    csv_path = tmp_path / "E0-20252026.csv"
    _write_e0_csv(csv_path)

    conn = initialize_db(db_path)
    try:
        first = ingest_e0_csv(conn, csv_path)
        second = ingest_e0_csv(conn, csv_path)
        source_count = int(conn.execute("SELECT COUNT(*) AS c FROM sources").fetchone()["c"])
        raw_count = int(conn.execute("SELECT COUNT(*) AS c FROM raw_rows").fetchone()["c"])
        match_count = int(conn.execute("SELECT COUNT(*) AS c FROM matches").fetchone()["c"])
        stats_count = int(
            conn.execute("SELECT COUNT(*) AS c FROM team_match_stats").fetchone()["c"]
        )
    finally:
        conn.close()

    assert first.source_id == second.source_id
    assert source_count == 1
    assert raw_count == 2
    assert match_count == 2
    assert stats_count == 4


def test_ingest_e0_csv_infers_season_for_e0_dot_csv(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    csv_path = tmp_path / "E0.csv"
    _write_e0_csv(csv_path)

    conn = initialize_db(db_path)
    try:
        summary = ingest_e0_csv(conn, csv_path)
    finally:
        conn.close()

    assert summary.season_label == "2025-2026"
    assert summary.source_key == "E0:2025-2026"

