from pathlib import Path

from e0_site_build import build_site


def test_build_site_writes_index_and_week_pages(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    context_path = reports_dir / "weekly-context-arsenal-20252026-w1-2026-02-28.json"
    context_path.write_text(
        """
{
  "meta": {
    "team": "Arsenal",
    "season": "2025-2026",
    "week": 1,
    "report_date": "2026-02-28"
  },
  "match": {
    "opponent": "United",
    "result": "W",
    "score": "1-0",
    "venue": "away"
  },
  "form_snapshot": {
    "window": 1,
    "points": 3,
    "halfwin_average": 1.0,
    "wdl": {"w": 1, "d": 0, "l": 0}
  },
  "largest_upward_deltas": [
    {"metric": "shots", "delta": 2.0, "direction_for_team": "beneficial"}
  ],
  "largest_downward_deltas": [
    {"metric": "opponent_shots", "delta": -2.0, "direction_for_team": "beneficial"}
  ],
  "week_flags": ["lowest opponent_shots in season"],
  "context_quality": {
    "overall_confidence": "high",
    "peer_team_count": 20,
    "trend_window_size": 5,
    "flat_signal_metrics": [],
    "notes": []
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    ideation_path = reports_dir / "weekly-chatgpt-ideate-w1.json"
    ideation_path.write_text(
        """
{
  "executive_summary": {
    "headline": "Big start",
    "why_now": "Week 1 started well.",
    "confidence": "high",
    "confidence_rationale": "Enough support."
  },
  "state_snapshot": {
    "peer_context_takeaway": "Good peer week.",
    "season_vs_week_tension": "No tension yet."
  },
  "story_candidates": [
    {
      "id": "S1",
      "title": "Fast opening week",
      "angle": "Strong control and a clean sheet.",
      "audience_value": "Good opener.",
      "peer_signal": "Peer support.",
      "season_to_date_signal": "Too early but positive.",
      "signal_strength": "strong",
      "risks_or_caveats": ["Week 1 only."],
      "charts": [{"type": "bar", "why": "Show the shot edge."}]
    }
  ],
  "recommended_story": {
    "story_id": "S1",
    "draft_subheading": "Good opener."
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    selection_path = reports_dir / "editorial-selection-arsenal-20252026-w1-2026-02-28.json"
    selection_path.write_text(
        f"""
{{
  "team": "Arsenal",
  "season": "2025-2026",
  "week": 1,
  "report_date": "2026-02-28",
  "weekly_context_file": "{context_path}",
  "ideation_file": "{ideation_path}",
  "selected_story_id": "S1",
  "selected_story_title": "Fast opening week",
  "secondary_story_ids": [],
  "rejected_story_ids": [],
  "recommended_story_id": "S1",
  "recommended_matches_selection": true,
  "selection_reason": "Simple test selection.",
  "selection_mode": "manual",
  "notes": []
}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    blog_path = reports_dir / "weekly-post-arsenal-20252026-w1.md"
    blog_path.write_text(
        (
            "1) Title\n"
            "Arsenal open with control\n\n"
            "2) One-paragraph thesis\n"
            "Arsenal started well and looked composed.\n\n"
            "3) What happened this week\n"
            "- first point\n"
            "- second point\n\n"
            "8) Data appendix\n"
            "metric.a: 1\n"
        ),
        encoding="utf-8",
    )

    notes_path = reports_dir / "publication-notes-arsenal-20252026-w1.md"
    notes_path.write_text(
        "## Publish notes\n\nHold this one for later.\n",
        encoding="utf-8",
    )

    asset_dir = reports_dir / "weekly-report-arsenal-20252026-through-w1-2026-02-28_assets"
    asset_dir.mkdir()
    (asset_dir / "arsenal-2025-2026-halfwin.html").write_text(
        "<html><body>halfwin</body></html>\n",
        encoding="utf-8",
    )
    report_json_path = reports_dir / "weekly-report-arsenal-20252026-through-w1-2026-02-28.json"
    report_json_path.write_text(
        """
{
  "artifacts": {
    "embedded_animations": [
      {
        "team": "Arsenal",
        "season": "2025-2026",
        "kind": "halfwin",
        "path": "weekly-report-arsenal-20252026-through-w1-2026-02-28_assets/arsenal-2025-2026-halfwin.html"
      }
    ]
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    visual_selection_path = reports_dir / "visual-selection-arsenal-20252026-w1-2026-02-28.json"
    visual_selection_path.write_text(
        f"""
{{
  "team": "Arsenal",
  "season": "2025-2026",
  "week": 1,
  "report_date": "2026-02-28",
  "editorial_selection_file": "{selection_path}",
  "report_json_file": "{report_json_path}",
  "selected_visual_id": "halfwin",
  "selected_visual_title": "Half-win animation",
  "selected_visual_kind": "halfwin",
  "selected_visual_metric": "",
  "selected_visual_path": "weekly-report-arsenal-20252026-through-w1-2026-02-28_assets/arsenal-2025-2026-halfwin.html",
  "selection_mode": "auto-v1",
  "selection_reason": "Auto-selected halfwin."
}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "site"
    written = build_site(
        reports_dir=reports_dir,
        out_dir=out_dir,
        team="Arsenal",
        season="2025-2026",
    )

    assert out_dir.joinpath("index.html") in written
    assert out_dir.joinpath("arsenal/2025-2026/index.html") in written
    week_page = out_dir / "arsenal/2025-2026/week-1.html"
    sources_page = out_dir / "arsenal/2025-2026/week-1-sources.html"
    assert week_page in written
    assert sources_page in written

    html = week_page.read_text(encoding="utf-8")
    assert "Arsenal open with control" in html
    assert "Simple test selection." not in html
    assert "../../../reports/weekly-context-arsenal-20252026-w1-2026-02-28.json" not in html
    assert "Sources &amp; caveats" in html
    assert "Draft post" not in html
    assert "What happened this week" in html
    assert "Publication notes" in html
    assert "Half-win animation" in html
    assert "Suggested visuals" not in html
    assert "arsenal-2025-2026-halfwin.html" in html

    sources_html = sources_page.read_text(encoding="utf-8")
    assert "Simple test selection." in sources_html
    assert "../../../reports/weekly-context-arsenal-20252026-w1-2026-02-28.json" in sources_html
    assert "Confidence and caveats" in sources_html
    assert "Visual selection" in sources_html
    assert "Suggested visuals" in sources_html
    assert "Data appendix" in sources_html
