#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _expect_keys(
    obj: dict[str, Any],
    required: list[str],
    *,
    path: str,
    errors: list[str],
) -> None:
    for key in required:
        if key not in obj:
            errors.append(f"{path}: missing key {key!r}")


def validate_weekly_report_schema(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report: expected object"]

    _expect_keys(
        report,
        [
            "schema_version",
            "tool_version",
            "generated_at",
            "report_date",
            "input",
            "teams",
        ],
        path="report",
        errors=errors,
    )

    if not isinstance(report.get("schema_version"), str):
        errors.append("report.schema_version: expected string")
    if not isinstance(report.get("tool_version"), str):
        errors.append("report.tool_version: expected string")
    if not isinstance(report.get("generated_at"), str):
        errors.append("report.generated_at: expected string")
    if not isinstance(report.get("report_date"), str):
        errors.append("report.report_date: expected string")

    input_obj = report.get("input")
    if not isinstance(input_obj, dict):
        errors.append("report.input: expected object")
    else:
        _expect_keys(
            input_obj,
            [
                "source",
                "db_path",
                "competition_code",
                "teams",
                "side",
                "seasons",
                "metrics",
            ],
            path="report.input",
            errors=errors,
        )
        if input_obj.get("source") != "db":
            errors.append("report.input.source: expected 'db'")
        if not isinstance(input_obj.get("teams"), list):
            errors.append("report.input.teams: expected list")
        if not isinstance(input_obj.get("seasons"), list):
            errors.append("report.input.seasons: expected list")
        if not isinstance(input_obj.get("metrics"), list):
            errors.append("report.input.metrics: expected list")

    teams = report.get("teams")
    if not isinstance(teams, list):
        errors.append("report.teams: expected list")
        return errors

    def _validate_team_blocks(team_blocks: list[Any], *, path: str) -> None:
        for team_idx, team_obj in enumerate(team_blocks):
            base_path = f"{path}[{team_idx}]"
            if not isinstance(team_obj, dict):
                errors.append(f"{base_path}: expected object")
                continue
            _expect_keys(team_obj, ["team", "seasons"], path=base_path, errors=errors)
            if not isinstance(team_obj.get("team"), str):
                errors.append(f"{base_path}.team: expected string")
            seasons = team_obj.get("seasons")
            if not isinstance(seasons, list):
                errors.append(f"{base_path}.seasons: expected list")
                continue

            for season_idx, season_obj in enumerate(seasons):
                season_path = f"{base_path}.seasons[{season_idx}]"
                if not isinstance(season_obj, dict):
                    errors.append(f"{season_path}: expected object")
                    continue
                _expect_keys(
                    season_obj,
                    ["season", "summary", "weekly_rows", "metric_series", "findings"],
                    path=season_path,
                    errors=errors,
                )
                if not isinstance(season_obj.get("season"), str):
                    errors.append(f"{season_path}.season: expected string")
                summary = season_obj.get("summary")
                if not isinstance(summary, dict):
                    errors.append(f"{season_path}.summary: expected object")
                else:
                    for key in ["matches", "wins", "draws", "losses", "findings_count"]:
                        if key not in summary:
                            errors.append(f"{season_path}.summary: missing key {key!r}")

                weekly_rows = season_obj.get("weekly_rows")
                if not isinstance(weekly_rows, list):
                    errors.append(f"{season_path}.weekly_rows: expected list")
                    weekly_rows = []
                else:
                    for row_idx, row in enumerate(weekly_rows):
                        row_path = f"{season_path}.weekly_rows[{row_idx}]"
                        if not isinstance(row, dict):
                            errors.append(f"{row_path}: expected object")
                            continue
                        _expect_keys(
                            row,
                            [
                                "week",
                                "date",
                                "opponent",
                                "venue",
                                "result",
                                "half_win_average",
                                "running_league_points",
                            ],
                            path=row_path,
                            errors=errors,
                        )
                        if not _is_number(row.get("week")):
                            errors.append(f"{row_path}.week: expected number")
                        for key in ["date", "opponent", "venue", "result"]:
                            if not isinstance(row.get(key), str):
                                errors.append(f"{row_path}.{key}: expected string")
                        if not _is_number(row.get("half_win_average")):
                            errors.append(f"{row_path}.half_win_average: expected number")
                        if not _is_number(row.get("running_league_points")):
                            errors.append(
                                f"{row_path}.running_league_points: expected number"
                            )
                        annotation = row.get("annotation")
                        if annotation is not None and not isinstance(annotation, dict):
                            errors.append(f"{row_path}.annotation: expected object when provided")

                metric_series = season_obj.get("metric_series")
                if not isinstance(metric_series, dict):
                    errors.append(f"{season_path}.metric_series: expected object")
                else:
                    expected_len = len(weekly_rows)
                    for metric, values in metric_series.items():
                        if not isinstance(metric, str):
                            errors.append(f"{season_path}.metric_series: metric key must be str")
                        if not isinstance(values, list):
                            errors.append(
                                f"{season_path}.metric_series[{metric!r}]: expected list"
                            )
                            continue
                        if len(values) != expected_len:
                            errors.append(
                                f"{season_path}.metric_series[{metric!r}]: length "
                                f"{len(values)} != weekly_rows length {expected_len}"
                            )
                        for value_idx, value in enumerate(values):
                            if value is None:
                                continue
                            if not _is_number(value):
                                errors.append(
                                    f"{season_path}.metric_series[{metric!r}][{value_idx}]: "
                                    "expected number or null"
                                )

                findings = season_obj.get("findings")
                if not isinstance(findings, list):
                    errors.append(f"{season_path}.findings: expected list")
                else:
                    for find_idx, finding in enumerate(findings):
                        find_path = f"{season_path}.findings[{find_idx}]"
                        if not isinstance(finding, dict):
                            errors.append(f"{find_path}: expected object")
                            continue
                        _expect_keys(
                            finding,
                            ["kind", "season", "team", "severity", "title", "summary", "evidence", "weeks"],
                            path=find_path,
                            errors=errors,
                        )
                        for key in ["kind", "season", "team", "severity", "title", "summary"]:
                            if not isinstance(finding.get(key), str):
                                errors.append(f"{find_path}.{key}: expected string")
                        if not isinstance(finding.get("evidence"), dict):
                            errors.append(f"{find_path}.evidence: expected object")
                        if not isinstance(finding.get("weeks"), list):
                            errors.append(f"{find_path}.weeks: expected list")

    artifacts = report.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, dict):
            errors.append("report.artifacts: expected object when provided")
        else:
            embedded = artifacts.get("embedded_animations")
            if embedded is not None:
                if not isinstance(embedded, list):
                    errors.append("report.artifacts.embedded_animations: expected list")
                else:
                    for idx, item in enumerate(embedded):
                        item_path = f"report.artifacts.embedded_animations[{idx}]"
                        if not isinstance(item, dict):
                            errors.append(f"{item_path}: expected object")
                            continue
                        for key in ["team", "season", "kind", "path"]:
                            if key not in item:
                                errors.append(f"{item_path}: missing key {key!r}")
                            elif not isinstance(item.get(key), str):
                                errors.append(f"{item_path}.{key}: expected string")

    annotations = report.get("annotations")
    if annotations is not None:
        if not isinstance(annotations, list):
            errors.append("report.annotations: expected list when provided")
        else:
            for idx, item in enumerate(annotations):
                item_path = f"report.annotations[{idx}]"
                if not isinstance(item, dict):
                    errors.append(f"{item_path}: expected object")
                    continue
                _expect_keys(
                    item,
                    ["team", "season", "week", "payload"],
                    path=item_path,
                    errors=errors,
                )
                if not isinstance(item.get("team"), str):
                    errors.append(f"{item_path}.team: expected string")
                if not isinstance(item.get("season"), str):
                    errors.append(f"{item_path}.season: expected string")
                if not _is_number(item.get("week")):
                    errors.append(f"{item_path}.week: expected number")
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    errors.append(f"{item_path}.payload: expected object")

    _validate_team_blocks(teams, path="report.teams")

    league_context = report.get("league_context")
    if league_context is not None:
        if not isinstance(league_context, dict):
            errors.append("report.league_context: expected object when provided")
        else:
            _expect_keys(
                league_context,
                ["scope", "competition_code", "side", "seasons", "team_count", "teams"],
                path="report.league_context",
                errors=errors,
            )
            for key in ["scope", "competition_code", "side"]:
                if not isinstance(league_context.get(key), str):
                    errors.append(f"report.league_context.{key}: expected string")
            if not isinstance(league_context.get("seasons"), list):
                errors.append("report.league_context.seasons: expected list")
            if not _is_number(league_context.get("team_count")):
                errors.append("report.league_context.team_count: expected number")
            league_teams = league_context.get("teams")
            if not isinstance(league_teams, list):
                errors.append("report.league_context.teams: expected list")
            else:
                _validate_team_blocks(league_teams, path="report.league_context.teams")

    return errors


def assert_valid_weekly_report_schema(report: dict[str, Any]) -> None:
    errors = validate_weekly_report_schema(report)
    if errors:
        raise ValueError(
            "weekly-report.v1 validation failed:\n- " + "\n- ".join(errors)
        )
