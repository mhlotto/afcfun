from e0_weekly_report_data import (
    default_report_basename,
    detect_control_without_result,
    detect_discipline_tax,
    detect_metric_outliers_zscore,
    detect_regime_shift,
)


def test_default_report_basename_is_deterministic() -> None:
    value = default_report_basename(
        teams=["Arsenal", "Fulham"],
        seasons=["2024-2025", "2025-2026"],
        report_date="2026-02-25",
    )
    assert value == "weekly-report-arsenal-fulham-20242025-20252026-2026-02-25"


def test_detect_control_without_result_flags_high_control_non_wins() -> None:
    rows = [
        {
            "week": 1,
            "date": "01/01/2026",
            "opponent": "A",
            "result": "draw",
            "shots": 20,
            "opponent_shots": 8,
            "shots_on_target": 7,
            "opponent_shots_on_target": 3,
        },
        {
            "week": 2,
            "date": "08/01/2026",
            "opponent": "B",
            "result": "win",
            "shots": 12,
            "opponent_shots": 11,
            "shots_on_target": 4,
            "opponent_shots_on_target": 3,
        },
    ]
    findings = detect_control_without_result(
        team="Arsenal",
        season="2025-2026",
        weekly_rows=rows,
    )
    assert len(findings) == 1
    assert findings[0]["kind"] == "control_without_result"
    assert findings[0]["weeks"] == [1]


def test_detect_discipline_tax_uses_bookings_vs_points_signal() -> None:
    rows = [
        {"result": "loss", "bookings_points": 18},
        {"result": "loss", "bookings_points": 15},
        {"result": "draw", "bookings_points": 12},
        {"result": "win", "bookings_points": 8},
        {"result": "win", "bookings_points": 6},
        {"result": "win", "bookings_points": 5},
    ]
    findings = detect_discipline_tax(
        team="Arsenal",
        season="2025-2026",
        weekly_rows=rows,
    )
    assert findings
    assert findings[0]["kind"] == "discipline_tax"
    assert findings[0]["evidence"]["pearson_r"] < 0


def test_detect_metric_outliers_zscore_flags_extreme_week() -> None:
    weekly_rows = [
        {"week": 1, "date": "01/01/2026", "opponent": "A"},
        {"week": 2, "date": "08/01/2026", "opponent": "B"},
        {"week": 3, "date": "15/01/2026", "opponent": "C"},
        {"week": 4, "date": "22/01/2026", "opponent": "D"},
        {"week": 5, "date": "29/01/2026", "opponent": "E"},
        {"week": 6, "date": "05/02/2026", "opponent": "F"},
    ]
    metric_series = {
        "shots": [10.0, 11.0, 9.0, 10.0, 10.0, 30.0],
    }
    findings = detect_metric_outliers_zscore(
        team="Arsenal",
        season="2025-2026",
        weekly_rows=weekly_rows,
        metric_series=metric_series,
        z_threshold=1.8,
    )
    assert findings
    assert findings[0]["kind"] == "metric_outlier_zscore"
    assert 6 in findings[0]["weeks"]


def test_detect_regime_shift_flags_split_half_change() -> None:
    metric_series = {
        "shots_on_target": [2.0, 3.0, 2.0, 3.0, 7.0, 8.0, 7.0, 8.0],
    }
    findings = detect_regime_shift(
        team="Arsenal",
        season="2025-2026",
        metric_series=metric_series,
        effect_threshold=0.8,
    )
    assert findings
    assert findings[0]["kind"] == "regime_shift"
    top = findings[0]["evidence"]["top_shifts"][0]
    assert top["metric"] == "shots_on_target"
