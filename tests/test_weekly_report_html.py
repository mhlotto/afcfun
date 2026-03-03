from pathlib import Path

from e0_weekly_report_html import default_report_html_path, render_report_html


def test_default_report_html_path_swaps_suffix() -> None:
    assert default_report_html_path(Path("docs/reports/sample.json")) == Path(
        "docs/reports/sample.html"
    )


def test_render_report_html_includes_embedded_iframe(tmp_path: Path) -> None:
    report = {
        "schema_version": "weekly-report.v1",
        "generated_at": "__X__",
        "input": {"teams": ["Arsenal"], "seasons": ["2025-2026"], "competition_code": "E0"},
        "teams": [
            {
                "team": "Arsenal",
                "seasons": [
                    {
                        "season": "2025-2026",
                        "summary": {"matches": 1, "wins": 1, "draws": 0, "losses": 0, "findings_count": 0},
                        "weekly_rows": [
                            {
                                "week": 1,
                                "date": "01/01/2026",
                                "opponent": "A",
                                "venue": "home",
                                "result": "win",
                                "half_win_average": 1.0,
                                "running_league_points": 3.0,
                                "annotation": {"title": "Header note", "type": "tactical"},
                            }
                        ],
                        "metric_series": {},
                        "findings": [
                            {
                                "kind": "control_without_result",
                                "season": "2025-2026",
                                "team": "Arsenal",
                                "severity": "warning",
                                "title": "Control without result",
                                "summary": "One match stood out.",
                                "evidence": {},
                                "weeks": [1],
                            }
                        ],
                    }
                ],
            }
        ],
        "artifacts": {
            "embedded_animations": [
                {
                    "team": "Arsenal",
                    "season": "2025-2026",
                    "kind": "halfwin",
                    "path": "assets/arsenal-halfwin.html",
                }
            ]
        },
    }
    out_path = tmp_path / "report.html"
    render_report_html(report, out_path=out_path)
    html = out_path.read_text(encoding="utf-8")
    assert "Embedded animations" in html
    assert "assets/arsenal-halfwin.html" in html
    assert "iframe title='halfwin animation'" in html
    assert "Event/media annotations" in html
    assert "Header note" in html
    assert "Annotation</th>" in html
    assert "Matched annotations" in html
    assert "Type: tactical" in html
    assert "ann-type-chip ann-type-tactical" in html


def test_render_report_html_supports_cinematic_style(tmp_path: Path) -> None:
    report = {
        "schema_version": "weekly-report.v1",
        "generated_at": "__X__",
        "input": {"teams": ["Arsenal"], "seasons": ["2025-2026"], "competition_code": "E0"},
        "teams": [
            {
                "team": "Arsenal",
                "seasons": [
                    {
                        "season": "2025-2026",
                        "summary": {"matches": 0, "wins": 0, "draws": 0, "losses": 0, "findings_count": 0},
                        "weekly_rows": [],
                        "metric_series": {},
                        "findings": [],
                    }
                ],
            }
        ],
    }
    out_path = tmp_path / "report_cinematic.html"
    render_report_html(report, out_path=out_path, style="cinematic")
    html = out_path.read_text(encoding="utf-8")
    assert "--accent:#b15b1d;" in html


def test_render_report_html_converts_local_absolute_links_to_relative(
    tmp_path: Path,
) -> None:
    media_path = tmp_path / "assets" / "clip.html"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_text("<html></html>", encoding="utf-8")

    report = {
        "schema_version": "weekly-report.v1",
        "generated_at": "__X__",
        "input": {"teams": ["Arsenal"], "seasons": ["2025-2026"], "competition_code": "E0"},
        "teams": [
            {
                "team": "Arsenal",
                "seasons": [
                    {
                        "season": "2025-2026",
                        "summary": {"matches": 1, "wins": 1, "draws": 0, "losses": 0, "findings_count": 1},
                        "weekly_rows": [
                            {
                                "week": 1,
                                "date": "01/01/2026",
                                "opponent": "A",
                                "venue": "home",
                                "result": "win",
                                "half_win_average": 1.0,
                                "running_league_points": 3.0,
                                "annotation": {
                                    "title": "Clip",
                                    "media_url": str(media_path),
                                },
                            }
                        ],
                        "metric_series": {},
                        "findings": [
                            {
                                "kind": "metric_outlier_zscore",
                                "season": "2025-2026",
                                "team": "Arsenal",
                                "severity": "info",
                                "title": "Outlier",
                                "summary": "One match",
                                "evidence": {},
                                "weeks": [1],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    out_path = tmp_path / "report_rel.html"
    render_report_html(report, out_path=out_path)
    html = out_path.read_text(encoding="utf-8")
    assert "assets/clip.html" in html
    assert str(media_path) not in html


def test_render_report_html_converts_http_links_to_relative_path(
    tmp_path: Path,
) -> None:
    report = {
        "schema_version": "weekly-report.v1",
        "generated_at": "__X__",
        "input": {"teams": ["Arsenal"], "seasons": ["2025-2026"], "competition_code": "E0"},
        "teams": [
            {
                "team": "Arsenal",
                "seasons": [
                    {
                        "season": "2025-2026",
                        "summary": {"matches": 1, "wins": 0, "draws": 0, "losses": 1, "findings_count": 1},
                        "weekly_rows": [
                            {
                                "week": 1,
                                "date": "01/01/2026",
                                "opponent": "A",
                                "venue": "home",
                                "result": "loss",
                                "half_win_average": 0.0,
                                "running_league_points": 0.0,
                                "annotation": {
                                    "type": "media",
                                    "title": "Clip",
                                    "media_url": "https://example.com/highlights?x=1",
                                },
                            }
                        ],
                        "metric_series": {},
                        "findings": [
                            {
                                "kind": "metric_outlier_zscore",
                                "season": "2025-2026",
                                "team": "Arsenal",
                                "severity": "info",
                                "title": "Outlier",
                                "summary": "one",
                                "evidence": {},
                                "weeks": [1],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    out_path = tmp_path / "report_http_rel.html"
    render_report_html(report, out_path=out_path)
    html = out_path.read_text(encoding="utf-8")
    assert "href='highlights?x=1'" in html
    assert "example.com" not in html
