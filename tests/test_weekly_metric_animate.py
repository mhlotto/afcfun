from e0_weekly_metric_animate import _build_payload
from e0_weekly_metric_plot import WeeklyMetricPoint


def test_metric_animation_payload_handles_missing_values() -> None:
    series = {
        "Arsenal": [
            WeeklyMetricPoint(
                week=1,
                value=5.0,
                date="17/08/2025",
                opponent="Chelsea",
                venue="away",
                result="win",
            ),
            WeeklyMetricPoint(
                week=2,
                value=None,
                date="24/08/2025",
                opponent="Everton",
                venue="home",
                result="win",
            ),
        ]
    }

    payload = _build_payload(series, metric="opponent_free_kicks_conceded")

    assert payload["metric"] == "opponent_free_kicks_conceded"
    assert payload["max_week"] == 2
    assert payload["has_values"] is True
    assert payload["y_tick_labels"]
    assert all("." not in label for label in payload["y_tick_labels"])
    points = payload["teams"][0]["points"]
    assert points[0]["value"] == 5.0
    assert points[1]["value"] is None
