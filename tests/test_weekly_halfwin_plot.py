from e0_weekly_halfwin_plot import build_weekly_half_win_average, parse_teams


def test_build_weekly_half_win_average_orders_by_date_and_scores_draw_half() -> None:
    normalized = [
        {"Date": "08/08/25", "Time": "15:00", "result": "draw", "opponent": "B"},
        {"Date": "15/08/25", "Time": "15:00", "result": "loss", "opponent": "C"},
        {"Date": "01/08/25", "Time": "15:00", "result": "win", "opponent": "A"},
    ]

    points = build_weekly_half_win_average(normalized)

    assert [point.week for point in points] == [1, 2, 3]
    assert [point.result for point in points] == ["win", "draw", "loss"]
    assert points[0].average == 1.0
    assert points[1].average == 0.75
    assert points[2].average == 0.5
    assert points[2].running_points == 1.5
    assert points[2].running_league_points == 4.0
    assert points[2].points_efficiency == (4.0 / 9.0)


def test_parse_teams_supports_comma_delimited_and_dedupes() -> None:
    parsed = parse_teams("Arsenal, Fulham,arsenal,  Spurs ")
    assert parsed == ["Arsenal", "Fulham", "Spurs"]
