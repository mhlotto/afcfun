from e0_weekly_report_annotations import apply_weekly_annotations


def test_apply_weekly_annotations_sets_row_annotation_and_top_level_list() -> None:
    report = {
        "teams": [
            {
                "team": "Arsenal",
                "seasons": [
                    {
                        "season": "2025-2026",
                        "weekly_rows": [
                            {"week": 1, "result": "win"},
                            {"week": 2, "result": "draw"},
                        ],
                    }
                ],
            }
        ]
    }
    annotations = {
        ("arsenal", "2025-2026", 2): {
            "title": "Late equalizer",
            "media_url": "https://example.com/clip",
        }
    }
    count = apply_weekly_annotations(report, annotations)
    assert count == 1
    row = report["teams"][0]["seasons"][0]["weekly_rows"][1]
    assert row["annotation"]["title"] == "Late equalizer"
    assert report["annotations"][0]["week"] == 2
