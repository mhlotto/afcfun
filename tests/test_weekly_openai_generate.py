from pathlib import Path

from e0_weekly_blog_generate import default_blog_output_path
from e0_weekly_ideate_generate import default_ideation_output_path


def test_default_ideation_output_path() -> None:
    context_path = Path("docs/reports/weekly-context-arsenal-20252026-w27-2026-02-28.json")
    out_path = default_ideation_output_path(context_json=context_path, week=27)
    assert out_path == Path("docs/reports/weekly-chatgpt-ideate-w27.json")


def test_default_blog_output_path() -> None:
    out_path = default_blog_output_path(team="Arsenal", season="2025-2026", week=27)
    assert out_path == Path("docs/reports/weekly-post-arsenal-20252026-w27.md")
