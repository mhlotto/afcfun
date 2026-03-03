from pathlib import Path

from e0_multi_season import (
    build_multi_season_series,
    discover_season_sources,
    normalize_season_token,
    parse_season_filter,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    header = [
        "Div",
        "Date",
        "Time",
        "HomeTeam",
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row.get(col, "") for col in header))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_normalize_season_token_and_filter() -> None:
    assert normalize_season_token("20212022") == "2021-2022"
    assert normalize_season_token("2021-2022") == "2021-2022"
    parsed = parse_season_filter("20212022, 2025-2026,20212022")
    assert parsed == ["2021-2022", "2025-2026"]


def test_discover_season_sources_with_inferred_current(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "E0-20212022.csv",
        [
            {
                "Div": "E0",
                "Date": "01/08/21",
                "Time": "15:00",
                "HomeTeam": "Arsenal",
                "AwayTeam": "Chelsea",
                "FTHG": "2",
                "FTAG": "1",
                "FTR": "H",
            }
        ],
    )
    _write_csv(
        tmp_path / "E0.csv",
        [
            {
                "Div": "E0",
                "Date": "17/08/25",
                "Time": "15:00",
                "HomeTeam": "Everton",
                "AwayTeam": "Arsenal",
                "FTHG": "0",
                "FTAG": "0",
                "FTR": "D",
            },
            {
                "Div": "E0",
                "Date": "01/02/26",
                "Time": "15:00",
                "HomeTeam": "Arsenal",
                "AwayTeam": "Leeds",
                "FTHG": "1",
                "FTAG": "0",
                "FTR": "H",
            },
        ],
    )

    sources = discover_season_sources(tmp_path)
    labels = [source.label for source in sources]
    assert labels == ["2021-2022", "2025-2026"]
    assert [source.is_current for source in sources] == [False, True]


def test_build_multi_season_series_basic(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "E0-20212022.csv",
        [
            {
                "Div": "E0",
                "Date": "01/08/21",
                "Time": "15:00",
                "HomeTeam": "Arsenal",
                "AwayTeam": "Chelsea",
                "FTHG": "2",
                "FTAG": "1",
                "FTR": "H",
            }
        ],
    )
    _write_csv(
        tmp_path / "E0.csv",
        [
            {
                "Div": "E0",
                "Date": "17/08/25",
                "Time": "15:00",
                "HomeTeam": "Everton",
                "AwayTeam": "Arsenal",
                "FTHG": "0",
                "FTAG": "0",
                "FTR": "D",
            }
        ],
    )

    series, _ = build_multi_season_series(
        data_dir=tmp_path,
        teams=["Arsenal"],
        side="both",
        current_label="2025-2026",
    )

    assert "Arsenal (2021-2022)" in series
    assert "Arsenal (2025-2026)" in series
    assert series["Arsenal (2021-2022)"][0].average == 1.0
    assert series["Arsenal (2025-2026)"][0].average == 0.5
