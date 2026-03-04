from e0_weekly_chart_plan_resolve import _resolve_plan_item


def test_resolve_plan_item_maps_result_form_to_halfwin() -> None:
    item = {
        "id": "C1",
        "priority": "primary",
        "chart_type": "result_form",
        "metrics": [],
    }
    candidates = [
        {"kind": "metric", "metric": "shots", "path": "assets/shots.html"},
        {"kind": "halfwin", "path": "assets/halfwin.html"},
    ]
    resolved = _resolve_plan_item(item, candidates)
    assert resolved["status"] == "mapped"
    assert resolved["kind"] == "halfwin"
    assert resolved["path"] == "assets/halfwin.html"


def test_resolve_plan_item_maps_metric_chart() -> None:
    item = {
        "id": "C2",
        "priority": "secondary",
        "chart_type": "metric_trend",
        "metrics": ["opponent_fouls"],
    }
    candidates = [
        {"kind": "metric", "metric": "opponent_fouls", "path": "assets/opponent_fouls.html"},
    ]
    resolved = _resolve_plan_item(item, candidates)
    assert resolved["status"] == "mapped"
    assert resolved["kind"] == "metric"
    assert resolved["metric"] == "opponent_fouls"
