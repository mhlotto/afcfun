from pathlib import Path

from footstat_db import initialize_db
from footstat_repo import FootstatRepo, normalize_team_text


def _seed(conn) -> None:
    with conn:
        conn.execute(
            (
                "INSERT INTO sources(loader_name, source_key, file_path, row_count) "
                "VALUES(?, ?, ?, ?)"
            ),
            ("football-data-e0", "E0-2025-2026", "data/football-data.co.uk/E0.csv", 2),
        )
        source_id = int(conn.execute("SELECT id FROM sources").fetchone()["id"])
        conn.execute(
            "INSERT INTO competitions(code, name) VALUES(?, ?)",
            ("E0", "Premier League"),
        )
        competition_id = int(
            conn.execute("SELECT id FROM competitions WHERE code = 'E0'").fetchone()["id"]
        )
        conn.execute(
            (
                "INSERT INTO seasons(competition_id, start_year, end_year, label) "
                "VALUES(?, ?, ?, ?)"
            ),
            (competition_id, 2025, 2026, "2025-2026"),
        )
        season_id = int(conn.execute("SELECT id FROM seasons").fetchone()["id"])

        conn.execute("INSERT INTO teams(canonical_name) VALUES(?)", ("Arsenal",))
        conn.execute("INSERT INTO teams(canonical_name) VALUES(?)", ("Chelsea",))
        conn.execute("INSERT INTO teams(canonical_name) VALUES(?)", ("Everton",))
        team_rows = conn.execute(
            "SELECT id, canonical_name FROM teams ORDER BY id"
        ).fetchall()
        team_ids = {str(row["canonical_name"]): int(row["id"]) for row in team_rows}

        conn.execute(
            (
                "INSERT INTO team_aliases(team_id, alias, alias_norm, source_scope, is_primary) "
                "VALUES(?, ?, ?, ?, ?)"
            ),
            (team_ids["Arsenal"], "Arsenal FC", normalize_team_text("Arsenal FC"), "", 1),
        )

        conn.execute(
            (
                "INSERT INTO matches("
                "source_id, competition_id, season_id, match_date, match_time, "
                "home_team_id, away_team_id, referee, attendance, "
                "full_time_home_goals, full_time_away_goals, full_time_result"
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                source_id,
                competition_id,
                season_id,
                "17/08/2025",
                "15:00",
                team_ids["Chelsea"],
                team_ids["Arsenal"],
                "Ref A",
                61000,
                0,
                1,
                "A",
            ),
        )
        first_match_id = int(
            conn.execute("SELECT id FROM matches WHERE match_date='17/08/2025'").fetchone()[
                "id"
            ]
        )
        conn.execute(
            (
                "INSERT INTO matches("
                "source_id, competition_id, season_id, match_date, match_time, "
                "home_team_id, away_team_id, referee, attendance, "
                "full_time_home_goals, full_time_away_goals, full_time_result"
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                source_id,
                competition_id,
                season_id,
                "24/08/2025",
                "15:00",
                team_ids["Arsenal"],
                team_ids["Everton"],
                "Ref B",
                60200,
                2,
                0,
                "H",
            ),
        )
        second_match_id = int(
            conn.execute("SELECT id FROM matches WHERE match_date='24/08/2025'").fetchone()[
                "id"
            ]
        )

        # Arsenal away vs Chelsea
        conn.execute(
            (
                "INSERT INTO team_match_stats("
                "match_id, source_id, competition_id, season_id, match_date, "
                "team_id, opponent_team_id, venue, result, total_goals, opponent_total_goals, "
                "halftime_goals, opponent_halftime_goals, shots, opponent_shots, "
                "shots_on_target, opponent_shots_on_target, corners, opponent_corners, "
                "fouls, opponent_fouls, yellow_cards, opponent_yellow_cards, "
                "red_cards, opponent_red_cards"
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                first_match_id,
                source_id,
                competition_id,
                season_id,
                "17/08/2025",
                team_ids["Arsenal"],
                team_ids["Chelsea"],
                "away",
                "win",
                1,
                0,
                0,
                0,
                10,
                12,
                4,
                3,
                3,
                5,
                9,
                11,
                2,
                3,
                0,
                0,
            ),
        )
        # Arsenal home vs Everton
        conn.execute(
            (
                "INSERT INTO team_match_stats("
                "match_id, source_id, competition_id, season_id, match_date, "
                "team_id, opponent_team_id, venue, result, total_goals, opponent_total_goals, "
                "halftime_goals, opponent_halftime_goals, shots, opponent_shots, "
                "shots_on_target, opponent_shots_on_target, corners, opponent_corners, "
                "fouls, opponent_fouls, yellow_cards, opponent_yellow_cards, "
                "red_cards, opponent_red_cards"
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                second_match_id,
                source_id,
                competition_id,
                season_id,
                "24/08/2025",
                team_ids["Arsenal"],
                team_ids["Everton"],
                "home",
                "win",
                2,
                0,
                1,
                0,
                16,
                7,
                6,
                2,
                8,
                4,
                6,
                14,
                1,
                2,
                0,
                0,
            ),
        )


def test_repo_lists_competitions_and_seasons(tmp_path: Path) -> None:
    conn = initialize_db(tmp_path / "footstat.sqlite3")
    try:
        _seed(conn)
        repo = FootstatRepo(conn)
        competitions = repo.list_competitions()
        seasons = repo.list_seasons(competition_code="E0")
    finally:
        conn.close()

    assert [item["code"] for item in competitions] == ["E0"]
    assert [item["label"] for item in seasons] == ["2025-2026"]


def test_repo_resolves_team_id_by_alias(tmp_path: Path) -> None:
    conn = initialize_db(tmp_path / "footstat.sqlite3")
    try:
        _seed(conn)
        repo = FootstatRepo(conn)
        canonical = repo.resolve_team_id("Arsenal")
        alias = repo.resolve_team_id("Arsenal FC")
    finally:
        conn.close()

    assert canonical == alias


def test_repo_fetches_matches_and_normalized_team_rows(tmp_path: Path) -> None:
    conn = initialize_db(tmp_path / "footstat.sqlite3")
    try:
        _seed(conn)
        repo = FootstatRepo(conn)
        matches = repo.fetch_matches(team="Arsenal", competition_code="E0")
        normalized = repo.fetch_normalized_team_rows(
            "Arsenal",
            side="both",
            competition_code="E0",
            seasons=["2025-2026"],
        )
        home_only = repo.fetch_normalized_team_rows(
            "Arsenal",
            side="home",
            competition_code="E0",
            seasons=["2025-2026"],
        )
    finally:
        conn.close()

    assert len(matches) == 2
    assert matches[0]["home_team"] == "Chelsea"
    assert matches[1]["away_team"] == "Everton"

    assert len(normalized) == 2
    assert normalized[0]["venue"] == "away"
    assert normalized[0]["total_goals"] == 1
    assert normalized[1]["venue"] == "home"
    assert normalized[1]["shots"] == 16
    assert len(home_only) == 1
    assert home_only[0]["venue"] == "home"

