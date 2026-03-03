from pathlib import Path

from e0_inspect import correlation_for_team, load_normalized_team_rows
from e0_loader_db import ingest_e0_csv
from footstat_db import initialize_db


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
    lines.extend(",".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_normalized_team_rows_csv_and_db_have_matching_core_values(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "E0-20252026.csv"
    _write_e0_csv(csv_path)
    db_path = tmp_path / "footstat.sqlite3"
    conn = initialize_db(db_path)
    try:
        ingest_e0_csv(conn, csv_path)
    finally:
        conn.close()

    csv_rows = load_normalized_team_rows(
        source="csv",
        team="Arsenal",
        side="both",
        csv_path=csv_path,
    )
    db_rows = load_normalized_team_rows(
        source="db",
        team="Arsenal",
        side="both",
        db_path=db_path,
        competition_code="E0",
        seasons=["2025-2026"],
    )

    assert len(csv_rows) == 2
    assert len(db_rows) == 2
    for csv_row, db_row in zip(csv_rows, db_rows, strict=True):
        assert csv_row["Date"] == db_row["Date"]
        assert csv_row["team"] == db_row["team"]
        assert csv_row["opponent"] == db_row["opponent"]
        assert csv_row["venue"] == db_row["venue"]
        assert csv_row["result"] == db_row["result"]
        assert csv_row["total_goals"] == db_row["total_goals"]
        assert csv_row["opponent_total_goals"] == db_row["opponent_total_goals"]
        assert csv_row["shots"] == db_row["shots"]
        assert csv_row["opponent_shots"] == db_row["opponent_shots"]


def test_correlation_for_team_works_with_db_source(tmp_path: Path) -> None:
    csv_path = tmp_path / "E0-20252026.csv"
    _write_e0_csv(csv_path)
    db_path = tmp_path / "footstat.sqlite3"
    conn = initialize_db(db_path)
    try:
        ingest_e0_csv(conn, csv_path)
    finally:
        conn.close()

    results = correlation_for_team(
        source="db",
        team="Arsenal",
        side="both",
        db_path=db_path,
        competition_code="E0",
        seasons=["2025-2026"],
        method="pearson",
        target="points",
        feature_set="base",
        min_pairs=2,
        ci_method="none",
    )

    assert results
    by_field = {item.field: item for item in results}
    assert "total_goals" in by_field
    assert by_field["total_goals"].n == 2

