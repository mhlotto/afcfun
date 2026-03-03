import math
from pathlib import Path

from e0_loader_db import ingest_e0_csv
from e0_weekly_halfwin_animate import _build_payload, _build_payload_from_series
from e0_weekly_halfwin_plot import build_team_series, build_team_series_from_db
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
        [
            "E0",
            "31/08/2025",
            "15:00",
            "Liverpool",
            "Arsenal",
            "1",
            "1",
            "D",
            "0",
            "0",
            "D",
            "13",
            "9",
            "5",
            "3",
            "6",
            "4",
            "12",
            "10",
            "2",
            "1",
            "0",
            "0",
            "61500",
            "Ref C",
        ],
    ]
    lines = [",".join(header)]
    lines.extend(",".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_weekly_series_csv_and_db_parity(tmp_path: Path) -> None:
    csv_path = tmp_path / "E0-20252026.csv"
    db_path = tmp_path / "footstat.sqlite3"
    _write_e0_csv(csv_path)

    conn = initialize_db(db_path)
    try:
        ingest_e0_csv(conn, csv_path)
    finally:
        conn.close()

    csv_series = build_team_series(
        csv_path=str(csv_path),
        teams=["Arsenal"],
        side="both",
    )["Arsenal"]
    db_series = build_team_series_from_db(
        db_path=str(db_path),
        teams=["Arsenal"],
        side="both",
        competition_code="E0",
        seasons=["2025-2026"],
    )["Arsenal"]

    assert len(csv_series) == len(db_series) == 3
    for csv_point, db_point in zip(csv_series, db_series, strict=True):
        assert csv_point.week == db_point.week
        assert csv_point.result == db_point.result
        assert csv_point.opponent == db_point.opponent
        assert csv_point.venue == db_point.venue
        assert math.isclose(csv_point.average, db_point.average, rel_tol=1e-12)
        assert math.isclose(
            csv_point.running_league_points,
            db_point.running_league_points,
            rel_tol=1e-12,
        )


def test_weekly_animation_payload_csv_and_db_parity(tmp_path: Path) -> None:
    csv_path = tmp_path / "E0-20252026.csv"
    db_path = tmp_path / "footstat.sqlite3"
    _write_e0_csv(csv_path)

    conn = initialize_db(db_path)
    try:
        ingest_e0_csv(conn, csv_path)
    finally:
        conn.close()

    csv_payload = _build_payload(
        str(csv_path),
        ["Arsenal"],
        "both",
        {},
        style="classic",
    )
    db_series = build_team_series_from_db(
        db_path=str(db_path),
        teams=["Arsenal"],
        side="both",
        competition_code="E0",
        seasons=["2025-2026"],
    )
    db_payload = _build_payload_from_series(
        db_series,
        ["Arsenal"],
        {},
        style="classic",
    )

    assert csv_payload["max_week"] == db_payload["max_week"]
    assert math.isclose(float(csv_payload["max_points"]), float(db_payload["max_points"]))
    assert csv_payload["y_ticks_top"] == db_payload["y_ticks_top"]
    assert csv_payload["y_ticks_bottom"] == db_payload["y_ticks_bottom"]
    csv_points = csv_payload["teams"][0]["points"]
    db_points = db_payload["teams"][0]["points"]
    assert len(csv_points) == len(db_points) == 3
    for csv_item, db_item in zip(csv_points, db_points, strict=True):
        assert csv_item["week"] == db_item["week"]
        assert math.isclose(csv_item["average"], db_item["average"], rel_tol=1e-12)
        assert math.isclose(
            csv_item["running_points"],
            db_item["running_points"],
            rel_tol=1e-12,
        )
        assert csv_item["summary"]["opponent"] == db_item["summary"]["opponent"]
        assert csv_item["summary"]["result"] == db_item["summary"]["result"]

