from pathlib import Path
import sqlite3

from e0_ingest_db import main as ingest_main
from footstat_db import initialize_db


def _write_csv(path: Path, rows: list[list[str]]) -> None:
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


def _counts(db_path: Path) -> dict[str, int]:
    conn = initialize_db(db_path)
    try:
        names = ["sources", "raw_rows", "matches", "team_match_stats"]
        out: dict[str, int] = {}
        for name in names:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()
            out[name] = int(row["c"])
        return out
    finally:
        conn.close()


def test_ingest_cli_dry_run_does_not_write_db(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "E0-20252026.csv"
    _write_csv(
        csv_path,
        [
            ["E0", "17/08/2025", "15:00", "Chelsea", "Arsenal", "0", "1", "A", "0", "0", "D"]
        ],
    )
    db_path = tmp_path / "footstat.sqlite3"

    rc = ingest_main(
        [
            "--db",
            str(db_path),
            "--data-dir",
            str(data_dir),
            "--dry-run",
        ]
    )
    assert rc == 0
    assert not db_path.exists()


def test_ingest_cli_glob_ingests_multiple_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_csv(
        data_dir / "E0-20242025.csv",
        [
            ["E0", "10/08/2024", "15:00", "Arsenal", "Chelsea", "2", "1", "H", "1", "1", "D"]
        ],
    )
    _write_csv(
        data_dir / "E0.csv",
        [
            ["E0", "17/08/2025", "15:00", "Chelsea", "Arsenal", "0", "1", "A", "0", "0", "D"]
        ],
    )
    _write_csv(
        data_dir / "ignore.csv",
        [
            ["E0", "17/08/2025", "15:00", "A", "B", "0", "0", "D", "0", "0", "D"]
        ],
    )
    db_path = tmp_path / "footstat.sqlite3"

    rc = ingest_main(
        [
            "--db",
            str(db_path),
            "--data-dir",
            str(data_dir),
        ]
    )
    assert rc == 0
    counts = _counts(db_path)
    assert counts["sources"] == 2
    assert counts["matches"] == 2
    assert counts["team_match_stats"] == 4


def test_ingest_cli_replace_source_removes_stale_rows(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "E0.csv"
    _write_csv(
        csv_path,
        [
            ["E0", "17/08/2025", "15:00", "Chelsea", "Arsenal", "0", "1", "A", "0", "0", "D"],
            ["E0", "24/08/2025", "15:00", "Arsenal", "Everton", "2", "0", "H", "1", "0", "H"],
        ],
    )
    db_path = tmp_path / "footstat.sqlite3"

    assert ingest_main(["--db", str(db_path), "--data-dir", str(data_dir)]) == 0
    first_counts = _counts(db_path)
    assert first_counts["matches"] == 2

    # Shrink the source file to one match.
    _write_csv(
        csv_path,
        [
            ["E0", "17/08/2025", "15:00", "Chelsea", "Arsenal", "0", "1", "A", "0", "0", "D"]
        ],
    )
    assert ingest_main(["--db", str(db_path), "--data-dir", str(data_dir)]) == 0
    second_counts = _counts(db_path)
    assert second_counts["matches"] == 2

    assert (
        ingest_main(
            [
                "--db",
                str(db_path),
                "--data-dir",
                str(data_dir),
                "--replace-source",
            ]
        )
        == 0
    )
    third_counts = _counts(db_path)
    assert third_counts["matches"] == 1
    assert third_counts["raw_rows"] == 1
    assert third_counts["team_match_stats"] == 2

