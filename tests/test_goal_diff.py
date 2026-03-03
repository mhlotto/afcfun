from e0_inspect import _target_value, normalize_by_team


def test_goal_diff_home_and_away() -> None:
    home_row = {
        "HomeTeam": "Arsenal",
        "AwayTeam": "Chelsea",
        "FTHG": "2",
        "FTAG": "1",
        "HTHG": "1",
        "HTAG": "0",
    }
    away_row = {
        "HomeTeam": "Everton",
        "AwayTeam": "Arsenal",
        "FTHG": "3",
        "FTAG": "1",
        "HTHG": "2",
        "HTAG": "1",
    }

    normalized = normalize_by_team([home_row, away_row], extract_team="Arsenal")

    home_norm = normalized[0]
    away_norm = normalized[1]

    assert _target_value(
        home_norm,
        "goal_diff",
        result_key="result",
        result_map=None,
    ) == 1.0
    assert _target_value(
        away_norm,
        "goal_diff",
        result_key="result",
        result_map=None,
    ) == -2.0
