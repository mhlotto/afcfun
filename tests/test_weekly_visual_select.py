from e0_weekly_visual_select import build_visual_selection


def test_build_visual_selection_prefers_metric_match() -> None:
    selection = {
        "team": "Arsenal",
        "season": "2025-2026",
        "week": 27,
        "report_date": "2026-02-28",
        "selected_story_id": "S1",
    }
    context = {
        "largest_upward_deltas": [{"metric": "shots", "delta": 2.0}],
        "largest_downward_deltas": [],
    }
    ideation = {
        "story_candidates": [
            {
                "id": "S1",
                "charts": [
                    {"type": "line", "metric_or_fields": ["shots"], "why": "Show shots trend."}
                ],
            }
        ]
    }
    report = {
        "artifacts": {
            "embedded_animations": [
                {
                    "team": "Arsenal",
                    "season": "2025-2026",
                    "kind": "halfwin",
                    "path": "assets/halfwin.html",
                },
                {
                    "team": "Arsenal",
                    "season": "2025-2026",
                    "kind": "metric",
                    "metric": "shots",
                    "path": "assets/shots.html",
                },
            ]
        }
    }

    visual = build_visual_selection(
        selection=selection,
        context=context,
        ideation=ideation,
        report=report,
        report_json_file="docs/reports/weekly-report.json",
        editorial_selection_file="docs/reports/editorial-selection.json",
    )

    assert visual["selected_visual_kind"] == "metric"
    assert visual["selected_visual_metric"] == "shots"
    assert visual["selected_visual_path"] == "assets/shots.html"


def test_build_visual_selection_respects_chart_plan_result_form() -> None:
    selection = {
        "team": "Arsenal",
        "season": "2025-2026",
        "week": 27,
        "report_date": "2026-02-28",
        "selected_story_id": "S1",
    }
    context = {
        "largest_upward_deltas": [],
        "largest_downward_deltas": [],
    }
    ideation = {
        "story_candidates": [
            {
                "id": "S1",
                "charts": [
                    {"type": "line", "metric_or_fields": ["shots"], "why": "Show shots trend."}
                ],
            }
        ],
        "chart_plan": [
            {
                "id": "C1",
                "title": "Form arc",
                "priority": "primary",
                "chart_type": "result_form",
                "metrics": [],
                "target": "main",
                "why": "Show trajectory of results.",
            }
        ],
    }
    report = {
        "artifacts": {
            "embedded_animations": [
                {
                    "team": "Arsenal",
                    "season": "2025-2026",
                    "kind": "halfwin",
                    "path": "assets/halfwin.html",
                },
                {
                    "team": "Arsenal",
                    "season": "2025-2026",
                    "kind": "metric",
                    "metric": "shots",
                    "path": "assets/shots.html",
                },
            ]
        }
    }

    visual = build_visual_selection(
        selection=selection,
        context=context,
        ideation=ideation,
        report=report,
        report_json_file="docs/reports/weekly-report.json",
        editorial_selection_file="docs/reports/editorial-selection.json",
    )

    assert visual["selected_visual_kind"] == "halfwin"
    assert visual["selected_visual_path"] == "assets/halfwin.html"
