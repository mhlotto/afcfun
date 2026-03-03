from pathlib import Path

from e0_weekly_halfwin_animate import _load_media_config


def test_load_media_config_entries_shape(tmp_path: Path) -> None:
    config = tmp_path / "media.json"
    config.write_text(
        (
            '{"entries":[{"team":"Arsenal","week":"3","title":"W3",'
            '"text":"Recap","priority":5}]}'
        ),
        encoding="utf-8",
    )

    loaded = _load_media_config(str(config))

    assert ("arsenal", 3) in loaded
    payload = loaded[("arsenal", 3)]
    assert payload["title"] == "W3"
    assert payload["text"] == "Recap"
    assert payload["priority"] == "5"


def test_load_media_config_team_week_shape(tmp_path: Path) -> None:
    config = tmp_path / "media.json"
    config.write_text(
        '{"Arsenal":{"2":{"text":"Week two"},"3":{"video":"match.mp4"}}}',
        encoding="utf-8",
    )

    loaded = _load_media_config(str(config))

    assert loaded[("arsenal", 2)]["text"] == "Week two"
    assert loaded[("arsenal", 3)]["video"] == "match.mp4"


def test_load_media_config_invalid_week(tmp_path: Path) -> None:
    config = tmp_path / "media.json"
    config.write_text(
        '{"entries":[{"team":"Arsenal","week":"bad","text":"x"}]}',
        encoding="utf-8",
    )

    try:
        _load_media_config(str(config))
    except ValueError as exc:
        assert "week must be a positive integer" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid week")
