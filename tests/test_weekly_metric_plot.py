from e0_weekly_metric_plot import build_metric_axis, build_weekly_metric_series


def test_build_weekly_metric_series_orders_and_extracts_values() -> None:
    normalized = [
        {
            "Date": "24/08/2025",
            "Time": "15:00",
            "opponent": "Everton",
            "venue": "home",
            "result": "win",
            "opponent_free_kicks_conceded": None,
        },
        {
            "Date": "17/08/2025",
            "Time": "15:00",
            "opponent": "Chelsea",
            "venue": "away",
            "result": "win",
            "opponent_free_kicks_conceded": "7",
        },
        {
            "Date": "31/08/2025",
            "Time": "15:00",
            "opponent": "Liverpool",
            "venue": "away",
            "result": "draw",
            "opponent_free_kicks_conceded": 3,
        },
    ]

    points = build_weekly_metric_series(
        normalized,
        metric="opponent_free_kicks_conceded",
    )

    assert [point.week for point in points] == [1, 2, 3]
    assert [point.opponent for point in points] == ["Chelsea", "Everton", "Liverpool"]
    assert points[0].value == 7.0
    assert points[1].value is None
    assert points[2].value == 3.0


def test_build_metric_axis_uses_integer_labels_for_integer_values() -> None:
    y_min, y_max, y_ticks, y_labels, is_integer_axis = build_metric_axis(
        [4.0, 10.0, 17.0]
    )

    assert is_integer_axis is True
    assert y_min < min([4.0, 10.0, 17.0])
    assert y_max > max([4.0, 10.0, 17.0])
    assert len(y_ticks) == len(y_labels)
    assert all("." not in label for label in y_labels)
