from pathlib import Path

from e0_weekly_blog_packet import default_blog_output_path, default_packet_path


def test_default_packet_path() -> None:
    path = default_packet_path(team="Arsenal", season="2025-2026", week=27)
    assert path == Path("exports/weekly-blog-packet-arsenal-20252026-w27.md")


def test_default_blog_output_path() -> None:
    path = default_blog_output_path(team="Arsenal", season="2025-2026", week=27)
    assert path == Path("docs/reports/weekly-post-arsenal-20252026-w27.md")
