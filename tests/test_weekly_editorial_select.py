from pathlib import Path

from e0_weekly_editorial_select import (
    build_editorial_selection,
    default_editorial_selection_path,
)


def _sample_context() -> dict[str, object]:
    return {
        "meta": {
            "team": "Arsenal",
            "season": "2025-2026",
            "week": 27,
            "report_date": "2026-02-28",
        }
    }


def _sample_ideation() -> dict[str, object]:
    return {
        "story_candidates": [
            {"id": "S1", "title": "Main story"},
            {"id": "S2", "title": "Secondary story"},
            {"id": "S3", "title": "Rejected story"},
        ],
        "recommended_story": {"story_id": "S1"},
    }


def test_build_editorial_selection() -> None:
    selection = build_editorial_selection(
        ideation=_sample_ideation(),
        context=_sample_context(),
        ideation_file="docs/reports/weekly-chatgptresponse-arsenal.json",
        context_file="docs/reports/weekly-context-arsenal.json",
        selected_story_id="S1",
        secondary_story_ids=["S2"],
        rejected_story_ids=["S3"],
        selection_reason="Best match-specific lead.",
        notes=["Fresh session gave the best result."],
    )

    assert selection["team"] == "Arsenal"
    assert selection["week"] == 27
    assert selection["selected_story_title"] == "Main story"
    assert selection["recommended_matches_selection"] is True
    assert selection["secondary_story_ids"] == ["S2"]
    assert selection["rejected_story_ids"] == ["S3"]


def test_default_editorial_selection_path() -> None:
    path = default_editorial_selection_path(
        context_path=Path("docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json"),
        team="Arsenal",
        season="2025-2026",
        week=27,
        report_date="2026-02-28",
    )
    assert path.name == "editorial-selection-arsenal-20252026-w27-2026-02-28.json"


def test_build_editorial_selection_supports_s1_default_choice() -> None:
    selection = build_editorial_selection(
        ideation=_sample_ideation(),
        context=_sample_context(),
        ideation_file="docs/reports/weekly-chatgpt-ideate-w27.json",
        context_file="docs/reports/weekly-context-arsenal.json",
        selected_story_id="S1",
        secondary_story_ids=[],
        rejected_story_ids=[],
        selection_reason="Auto-selected S1.",
        notes=[],
        selection_mode="auto-s1",
    )

    assert selection["selected_story_id"] == "S1"
    assert selection["selection_mode"] == "auto-s1"
    assert selection["selection_reason"] == "Auto-selected S1."
