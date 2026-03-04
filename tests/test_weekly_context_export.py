from pathlib import Path

from e0_weekly_context_export import build_weekly_context, default_context_path


def _sample_report() -> dict[str, object]:
    return {
        "report_date": "2026-02-26",
        "input": {
            "competition_code": "E0",
            "db_path": "data/footstat.sqlite3",
            "metrics": ["shots", "opponent_fouls"],
        },
        "teams": [
            {
                "team": "Arsenal",
                "seasons": [
                    {
                        "season": "2025-2026",
                        "weekly_rows": [
                            {
                                "week": 1,
                                "opponent": "A",
                                "result": "win",
                                "venue": "home",
                                "goals_for": 2,
                                "goals_against": 0,
                                "shots": 10,
                                "opponent_fouls": 8,
                                "goal_diff": 2,
                            },
                            {
                                "week": 2,
                                "opponent": "B",
                                "result": "draw",
                                "venue": "away",
                                "goals_for": 1,
                                "goals_against": 1,
                                "shots": 12,
                                "opponent_fouls": 9,
                                "goal_diff": 0,
                                "annotation": {
                                    "type": "tactical",
                                    "title": "Press tweak",
                                },
                            },
                            {
                                "week": 3,
                                "opponent": "C",
                                "result": "loss",
                                "venue": "home",
                                "goals_for": 0,
                                "goals_against": 1,
                                "shots": 8,
                                "opponent_fouls": 12,
                                "goal_diff": -1,
                            },
                        ],
                        "findings": [
                            {
                                "kind": "metric_outlier_zscore",
                                "summary": "Week 2 outlier",
                                "severity": "info",
                                "weeks": [2],
                            }
                        ],
                    }
                ],
            },
            {
                "team": "Fulham",
                "seasons": [
                    {
                        "season": "2025-2026",
                        "weekly_rows": [
                            {
                                "week": 1,
                                "opponent": "X",
                                "result": "loss",
                                "venue": "away",
                                "goals_for": 0,
                                "goals_against": 2,
                                "shots": 7,
                                "opponent_fouls": 11,
                                "goal_diff": -2,
                            },
                            {
                                "week": 2,
                                "opponent": "Y",
                                "result": "win",
                                "venue": "home",
                                "goals_for": 2,
                                "goals_against": 0,
                                "shots": 9,
                                "opponent_fouls": 7,
                                "goal_diff": 2,
                            },
                            {
                                "week": 3,
                                "opponent": "Z",
                                "result": "draw",
                                "venue": "away",
                                "goals_for": 1,
                                "goals_against": 1,
                                "shots": 11,
                                "opponent_fouls": 10,
                                "goal_diff": 0,
                            },
                        ],
                        "findings": [],
                    }
                ],
            },
        ],
    }


def _sample_report_with_league_context() -> dict[str, object]:
    report = _sample_report()
    arsenal_only = {
        **report,
        "teams": [report["teams"][0]],
        "league_context": {
            "scope": "competition-season",
            "competition_code": "E0",
            "side": "both",
            "seasons": ["2025-2026"],
            "team_count": 2,
            "teams": report["teams"],
        },
    }
    return arsenal_only


def test_build_weekly_context_picks_latest_week_and_computes_deltas() -> None:
    context = build_weekly_context(report=_sample_report(), window=2)
    assert context["meta"]["week"] == 3
    assert context["match"]["opponent"] == "C"
    assert context["match"]["result"] == "L"
    # shots mean is (10+12+8)/3 = 10, week-3 value 8, delta -2
    assert context["deltas_vs_season_avg"]["shots"] == -2.0
    assert context["largest_upward_deltas"][0] == {
        "metric": "opponent_fouls",
        "delta": 2.3333,
        "direction_for_team": "beneficial",
    }
    assert context["largest_downward_deltas"][0] == {
        "metric": "shots",
        "delta": -2.0,
        "direction_for_team": "harmful",
    }
    assert context["context_window"]["window"] == 2
    assert context["context_window"]["last_n_points"] == 1
    assert context["form_snapshot"]["window"] == 2
    assert context["form_snapshot"]["wdl"] == {"w": 0, "d": 1, "l": 1}
    assert context["form_snapshot"]["halfwin_average"] == 0.25
    assert context["form_snapshot"]["goal_diff_total"] == -1.0
    assert context["trend_summary"]["shots"]["direction"] == "down"
    assert context["trend_summary"]["shots"]["window"] == 2
    assert context["season_rankings"]["shots"]["high_rank"] == 3
    assert context["league_relative"]["scope"] == "report_teams_same_season_week"
    assert context["league_relative"]["metrics"]["shots"]["delta_vs_report_week_avg"] == -1.5
    assert context["league_relative"]["season_to_date_metrics"]["shots"]["current_value"] == 10.0
    assert context["league_relative"]["season_to_date_metrics"]["shots"]["peer_avg"] == 9.5
    assert context["league_relative"]["season_to_date_metrics"]["shots"]["high_rank"] == 1
    assert context["league_relative"]["percentile_trends"]["shots"]["window"] == 2
    assert context["league_relative"]["percentile_trends"]["shots"]["current_percentile_high"] == 0.5
    assert context["league_relative"]["percentile_trends"]["shots"]["delta_vs_window_avg"] == -0.25
    assert context["league_relative"]["percentile_trends"]["shots"]["direction"] == "down"
    assert context["league_relative"]["top_percentile_movers"]["falling"][0]["metric"] == "shots"
    assert "shots peer percentile is falling (-0.500/week)" in context["week_flags"]
    assert context["league_relative"]["top_percentile_movers"]["rising"] == []
    assert context["context_quality"]["overall_confidence"] == "low"
    assert context["context_quality"]["peer_context_available"] is True
    assert context["context_quality"]["peer_team_count"] == 2
    assert context["context_quality"]["trend_window_size"] == 2
    assert "shots" in context["context_quality"]["small_sample_metrics"]
    assert context["context_quality"]["flat_signal_metrics"] == []
    assert context["context_quality"]["missing_metric_sections"] == []
    assert any("Peer context is based on only 2 teams" in note for note in context["context_quality"]["notes"])
    assert context["data_gaps"] == []
    assert len(context["chart_hooks"]) >= 1
    hook_ids = {hook["id"] for hook in context["chart_hooks"]}
    assert "peer-percentile-falling-shots" in hook_ids
    assert "season-to-date-rank-shots" in hook_ids
    peer_hook = next(
        hook for hook in context["chart_hooks"] if hook["id"] == "peer-percentile-falling-shots"
    )
    assert peer_hook["type"] == "peer-percentile-trend-line"
    rank_hook = next(
        hook for hook in context["chart_hooks"] if hook["id"] == "season-to-date-rank-shots"
    )
    assert rank_hook["type"] == "peer-rank-shift-summary"
    peg_ids = {peg["id"] for peg in context["story_pegs"]}
    assert "season-extreme-goal_diff" in peg_ids
    assert "team-delta-opponent_fouls" in peg_ids
    assert "peer-shift-falling-shots" in peg_ids
    assert "season-peer-rank-shots" in peg_ids
    falling_peg = next(
        peg for peg in context["story_pegs"] if peg["id"] == "peer-shift-falling-shots"
    )
    assert falling_peg["peg_type"] == "peer-shift"
    assert falling_peg["confidence"] == "low"
    assert "peer-percentile-falling-shots" in falling_peg["chart_hook_ids"]


def test_build_weekly_context_includes_week_annotation_and_anomaly() -> None:
    context = build_weekly_context(report=_sample_report(), week=2, window=2)
    assert context["meta"]["week"] == 2
    assert context["annotations_for_week"][0]["title"] == "Press tweak"
    assert context["anomalies"][0]["kind"] == "metric_outlier_zscore"
    assert context["story_pegs"][0]["id"].startswith("anomaly-")
    shots_extreme = next(
        item for item in context["week_extremes"] if item["metric"] == "shots"
    )
    assert shots_extreme["direction"] == "high"
    assert shots_extreme["rank_in_season"] == 1
    assert "highest shots in season" in context["week_flags"]


def test_build_weekly_context_reports_gap_when_no_peer_teams_available() -> None:
    report = _sample_report()
    report["teams"] = [report["teams"][0]]

    context = build_weekly_context(report=report, week=2, window=2)

    assert context["league_relative"] == {}
    assert "league_relative unavailable" in context["data_gaps"][0]
    assert context["context_quality"]["overall_confidence"] == "low"
    assert context["context_quality"]["peer_context_available"] is False
    assert any(
        "Peer context unavailable" in note for note in context["context_quality"]["notes"]
    )


def test_build_weekly_context_uses_league_context_peers_when_present() -> None:
    context = build_weekly_context(report=_sample_report_with_league_context(), window=2)

    assert context["league_relative"]["scope"] == "league_context_same_season_week"
    assert context["league_relative"]["team_count"] == 2
    assert context["league_relative"]["metrics"]["shots"]["delta_vs_report_week_avg"] == -1.5
    assert context["league_relative"]["season_to_date_metrics"]["shots"]["peer_avg"] == 9.5
    assert context["league_relative"]["top_percentile_movers"]["falling"][0]["metric"] == "shots"
    assert any(
        hook["id"] == "peer-percentile-falling-shots"
        for hook in context["chart_hooks"]
    )


def test_build_weekly_context_marks_flat_signal_metrics() -> None:
    report = _sample_report()
    for team_block in report["teams"]:
        for season_block in team_block["seasons"]:
            for row in season_block["weekly_rows"]:
                row["steady_metric"] = 5

    context = build_weekly_context(
        report=report,
        metrics=["steady_metric"],
        window=3,
    )

    assert context["trend_summary"]["steady_metric"]["direction"] == "flat"
    assert context["context_quality"]["flat_signal_metrics"] == ["steady_metric"]


def test_default_context_path() -> None:
    path = default_context_path(
        report_path=Path("docs/reports/weekly-report-arsenal.json"),
        team="Arsenal",
        season="2025-2026",
        week=28,
        report_date="2026-02-26",
    )
    assert path.name == "weekly-context-arsenal-20252026-w28-2026-02-26.json"
