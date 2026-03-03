from e0_inspect import _add_diff_features


def test_diff_feature_creation() -> None:
    rows = [
        {
            "shots": 10,
            "opponent_shots": 7,
            "corners": 5,
            "opponent_corners": 6,
        }
    ]
    augmented = _add_diff_features(rows)
    assert "diff_shots" in augmented[0]
    assert augmented[0]["diff_shots"] == 3.0
    assert augmented[0]["diff_corners"] == -1.0
