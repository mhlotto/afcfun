from pathlib import Path

from e0_loader_db import ingest_e0_csv
from e0_weekly_halfwin_plot import build_team_series_from_db
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
    ]
    rows = [
        ["E0", "17/08/2025", "15:00", "Chelsea", "Arsenal", "0", "1", "A", "0", "0", "D", "12", "10", "3", "4"],
        ["E0", "24/08/2025", "15:00", "Arsenal", "Everton", "2", "0", "H", "1", "0", "H", "16", "7", "6", "2"],
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_build_team_series_from_db_reads_expected_points(tmp_path: Path) -> None:
    db_path = tmp_path / "footstat.sqlite3"
    csv_path = tmp_path / "E0-20252026.csv"
    _write_e0_csv(csv_path)

    conn = initialize_db(db_path)
    try:
        ingest_e0_csv(conn, csv_path)
    finally:
        conn.close()

    series = build_team_series_from_db(
        db_path=str(db_path),
        teams=["Arsenal"],
        side="both",
        competition_code="E0",
        seasons=["2025-2026"],
    )
    points = series["Arsenal"]
    assert len(points) == 2
    assert points[0].result == "win"
    assert points[0].average == 1.0
    assert points[1].average == 1.0
    assert points[1].running_league_points == 6.0

