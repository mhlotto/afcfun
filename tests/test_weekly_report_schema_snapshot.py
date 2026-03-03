from __future__ import annotations

import json
from pathlib import Path

import e0_weekly_report_data
from e0_weekly_report_data import build_weekly_report
from e0_weekly_report_schema import validate_weekly_report_schema


def _fixture_normalized_rows() -> list[dict[str, object]]:
    return [
        {
            "season": "2025-2026",
            "Date": "10/08/2025",
            "Time": "15:00",
            "result": "win",
            "opponent": "Team A",
            "venue": "home",
            "total_goals": 2,
            "opponent_total_goals": 0,
            "shots": 14,
            "shots_on_target": 6,
            "corners": 5,
            "fouls": 10,
            "yellow_cards": 1,
            "red_cards": 0,
            "opponent_shots": 8,
            "opponent_shots_on_target": 2,
            "opponent_corners": 4,
            "opponent_fouls": 12,
            "opponent_yellow_cards": 2,
            "opponent_red_cards": 0,
            "bookings_points": None,
            "opponent_bookings_points": None,
            "Referee": "Ref 1",
            "Attendance": 60000,
        },
        {
            "season": "2025-2026",
            "Date": "17/08/2025",
            "Time": "15:00",
            "result": "draw",
            "opponent": "Team B",
            "venue": "away",
            "total_goals": 1,
            "opponent_total_goals": 1,
            "shots": 10,
            "shots_on_target": 4,
            "corners": 4,
            "fouls": 9,
            "yellow_cards": 2,
            "red_cards": 0,
            "opponent_shots": 9,
            "opponent_shots_on_target": 3,
            "opponent_corners": 5,
            "opponent_fouls": 11,
            "opponent_yellow_cards": 1,
            "opponent_red_cards": 0,
            "bookings_points": None,
            "opponent_bookings_points": None,
            "Referee": "Ref 2",
            "Attendance": 50000,
        },
        {
            "season": "2025-2026",
            "Date": "24/08/2025",
            "Time": "15:00",
            "result": "loss",
            "opponent": "Team C",
            "venue": "home",
            "total_goals": 0,
            "opponent_total_goals": 1,
            "shots": 9,
            "shots_on_target": 3,
            "corners": 6,
            "fouls": 12,
            "yellow_cards": 3,
            "red_cards": 0,
            "opponent_shots": 11,
            "opponent_shots_on_target": 4,
            "opponent_corners": 3,
            "opponent_fouls": 10,
            "opponent_yellow_cards": 2,
            "opponent_red_cards": 0,
            "bookings_points": None,
            "opponent_bookings_points": None,
            "Referee": "Ref 3",
            "Attendance": 62000,
        },
        {
            "season": "2025-2026",
            "Date": "31/08/2025",
            "Time": "15:00",
            "result": "win",
            "opponent": "Team D",
            "venue": "away",
            "total_goals": 3,
            "opponent_total_goals": 1,
            "shots": 15,
            "shots_on_target": 7,
            "corners": 7,
            "fouls": 8,
            "yellow_cards": 1,
            "red_cards": 0,
            "opponent_shots": 10,
            "opponent_shots_on_target": 3,
            "opponent_corners": 4,
            "opponent_fouls": 9,
            "opponent_yellow_cards": 2,
            "opponent_red_cards": 0,
            "bookings_points": None,
            "opponent_bookings_points": None,
            "Referee": "Ref 4",
            "Attendance": 54000,
        },
    ]


def test_validate_weekly_report_schema_reports_errors() -> None:
    errors = validate_weekly_report_schema({"schema_version": "weekly-report.v1"})
    assert errors
    assert any("missing key" in error for error in errors)


def test_weekly_report_snapshot_arsenal_2025_2026(monkeypatch) -> None:
    fixture_rows = _fixture_normalized_rows()

    def _fake_load_normalized_team_rows(*args, **kwargs):
        return list(fixture_rows)

    monkeypatch.setattr(
        e0_weekly_report_data,
        "load_normalized_team_rows",
        _fake_load_normalized_team_rows,
    )

    report = build_weekly_report(
        db_path="data/footstat.sqlite3",
        competition_code="E0",
        teams=["Arsenal"],
        side="both",
        seasons=["2025-2026"],
        metrics=["shots", "opponent_fouls"],
        report_date="2026-02-25",
        z_threshold=2.0,
        regime_effect_threshold=0.8,
    )
    report["generated_at"] = "__GENERATED_AT__"

    expected_path = (
        Path(__file__).parent / "golden" / "weekly_report_arsenal_2025_2026.json"
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert report == expected


def test_build_weekly_report_includes_league_context_when_enabled(monkeypatch) -> None:
    fixture_rows = _fixture_normalized_rows()

    def _fake_load_normalized_team_rows(*args, **kwargs):
        team = kwargs.get("team")
        if team == "Fulham":
            rows = list(fixture_rows)
            rows[0] = {**rows[0], "shots": 8, "opponent_fouls": 14}
            rows[1] = {**rows[1], "shots": 11, "opponent_fouls": 9}
            rows[2] = {**rows[2], "shots": 12, "opponent_fouls": 8}
            rows[3] = {**rows[3], "shots": 10, "opponent_fouls": 13}
            return rows
        return list(fixture_rows)

    monkeypatch.setattr(
        e0_weekly_report_data,
        "load_normalized_team_rows",
        _fake_load_normalized_team_rows,
    )
    monkeypatch.setattr(
        e0_weekly_report_data,
        "_load_competition_teams",
        lambda **kwargs: ["Arsenal", "Fulham"],
    )

    report = build_weekly_report(
        db_path="data/footstat.sqlite3",
        competition_code="E0",
        teams=["Arsenal"],
        side="both",
        seasons=["2025-2026"],
        metrics=["shots", "opponent_fouls"],
        report_date="2026-02-25",
        z_threshold=2.0,
        regime_effect_threshold=0.8,
        include_league_context=True,
    )

    assert "league_context" in report
    assert report["league_context"]["team_count"] == 2
    assert len(report["league_context"]["teams"]) == 2
    assert validate_weekly_report_schema(report) == []


def test_build_weekly_report_truncates_at_through_week(monkeypatch) -> None:
    fixture_rows = _fixture_normalized_rows()

    def _fake_load_normalized_team_rows(*args, **kwargs):
        return list(fixture_rows)

    monkeypatch.setattr(
        e0_weekly_report_data,
        "load_normalized_team_rows",
        _fake_load_normalized_team_rows,
    )

    report = build_weekly_report(
        db_path="data/footstat.sqlite3",
        competition_code="E0",
        teams=["Arsenal"],
        side="both",
        seasons=["2025-2026"],
        metrics=["shots", "opponent_fouls"],
        report_date="2026-02-25",
        through_week=2,
    )

    season_block = report["teams"][0]["seasons"][0]
    assert report["input"]["through_week"] == 2
    assert season_block["summary"]["matches"] == 2
    assert len(season_block["weekly_rows"]) == 2
    assert season_block["weekly_rows"][-1]["week"] == 2
