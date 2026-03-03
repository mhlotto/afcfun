"""Inspection helpers for football-data.co.uk E0.csv."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import datetime as dt
import math
import random
import statistics
from typing import Iterable

from e0_expected_schema import COLUMNS as EXPECTED_COLUMNS
from e0_expected_schema import COLUMN_INFO as EXPECTED_COLUMN_INFO
from footstat_db import initialize_db
from footstat_repo import FootstatRepo

try:
    from scipy import stats as _stats
except ImportError:  # pragma: no cover - optional dependency
    _stats = None


@dataclass(frozen=True)
class ColumnInfo:
    code: str
    description: str
    group: str | None = None

    def __str__(self) -> str:
        if self.group:
            return f"{self.code} ({self.group}): {self.description}"
        return f"{self.code}: {self.description}"


@dataclass(frozen=True)
class E0Schema:
    columns: list[str]
    info: dict[str, ColumnInfo]

    def describe(self, code: str) -> str:
        info = self.info.get(code)
        if info is None:
            return f"{code}: Unknown description"
        return str(info)

    def __getitem__(self, code: str) -> ColumnInfo:
        return self.info[code]


@dataclass(frozen=True)
class InspectionReport:
    row_count: int
    columns: list[str]
    missing_columns: list[str]
    extra_columns: list[str]
    unknown_columns: list[str]
    order_mismatch: bool
    per_column_missing: dict[str, int]
    per_column_invalid: dict[str, int]
    sanity_violations: dict[str, int]
    column_types: dict[str, str]


@dataclass(frozen=True)
class CorrelationResult:
    field: str
    n: int
    r: float | None
    p_value: float | None
    q_value: float | None
    ci_low: float | None
    ci_high: float | None


def _build_expected_info() -> dict[str, ColumnInfo]:
    info_map: dict[str, ColumnInfo] = {}
    for code, info in EXPECTED_COLUMN_INFO.items():
        info_map[code] = ColumnInfo(
            code=code,
            description=info.get("description", ""),
            group=info.get("group"),
        )
    return info_map


EXPECTED_SCHEMA = E0Schema(columns=list(EXPECTED_COLUMNS), info=_build_expected_info())


def describe(code: str) -> str:
    return EXPECTED_SCHEMA.describe(code)


_DATE_COLUMNS = {"Date"}
_TIME_COLUMNS = {"Time"}
_RESULT_COLUMNS = {"FTR", "HTR"}
_STRING_COLUMNS = {"Div", "HomeTeam", "AwayTeam", "Referee"}
_INT_COLUMNS = {
    "FTHG",
    "FTAG",
    "HTHG",
    "HTAG",
    "Attendance",
    "HS",
    "AS",
    "HST",
    "AST",
    "HHW",
    "AHW",
    "HC",
    "AC",
    "HF",
    "AF",
    "HFKC",
    "AFKC",
    "HO",
    "AO",
    "HY",
    "AY",
    "HR",
    "AR",
    "HBP",
    "ABP",
    "Bb1X2",
    "BbOU",
    "BbAH",
}


def _column_type(col: str, info: ColumnInfo | None) -> str:
    if col in _DATE_COLUMNS:
        return "date"
    if col in _TIME_COLUMNS:
        return "time"
    if col in _RESULT_COLUMNS:
        return "result"
    if col in _STRING_COLUMNS:
        return "string"
    if col in _INT_COLUMNS:
        return "int"
    if info is None:
        return "unknown"
    desc = info.description.lower()
    if "number of" in desc:
        return "int"
    if "handicap" in desc:
        return "handicap"
    if "odds" in desc or "maximum" in desc or "average" in desc:
        return "odds"
    if ("over" in desc or "under" in desc) and "goals" in desc:
        return "odds"
    if any(
        token in desc
        for token in (
            "goals",
            "shots",
            "cards",
            "corners",
            "fouls",
            "bookings",
            "attendance",
            "offsides",
            "free kicks",
            "hit woodwork",
        )
    ):
        return "int"
    return "unknown"


def inspect_e0_csv(
    csv_path: str | Path,
    schema: E0Schema | None = None,
    expected_columns: Iterable[str] | None = None,
    max_rows: int | None = None,
) -> InspectionReport:
    schema = schema or EXPECTED_SCHEMA
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []

        if expected_columns is None:
            expected_list = list(schema.columns)
        else:
            expected_list = list(expected_columns)

        missing_columns = sorted(set(expected_list) - set(columns))
        extra_columns = sorted(set(columns) - set(expected_list))
        order_mismatch = (
            len(columns) == len(expected_list) and columns != expected_list
        )

        info_map = schema.info
        unknown_columns = sorted(
            col
            for col in columns
            if info_map.get(col) is None
            or info_map[col].description.startswith("Unknown description")
        )

        column_types = {
            col: _column_type(col, info_map.get(col)) for col in columns
        }

        per_column_missing = {col: 0 for col in columns}
        per_column_invalid = {col: 0 for col in columns}
        sanity_violations: dict[str, int] = {
            "ftr_mismatch": 0,
            "htr_mismatch": 0,
            "hst_gt_hs": 0,
            "ast_gt_as": 0,
            "negative_count": 0,
            "non_positive_odds": 0,
        }

        row_count = 0
        for row in reader:
            if max_rows is not None and row_count >= max_rows:
                break
            row_count += 1

            for col in columns:
                val = (row.get(col) or "").strip()
                if not val:
                    per_column_missing[col] += 1
                    continue

                col_type = column_types.get(col, "unknown")
                if col_type == "date":
                    try:
                        dt.datetime.strptime(val, "%d/%m/%y")
                    except ValueError:
                        per_column_invalid[col] += 1
                    continue
                if col_type == "time":
                    try:
                        dt.datetime.strptime(val, "%H:%M")
                    except ValueError:
                        per_column_invalid[col] += 1
                    continue
                if col_type == "result":
                    if val not in {"H", "D", "A"}:
                        per_column_invalid[col] += 1
                    continue
                if col_type == "int":
                    try:
                        parsed = int(val)
                    except ValueError:
                        per_column_invalid[col] += 1
                        continue
                    if parsed < 0:
                        sanity_violations["negative_count"] += 1
                    continue
                if col_type in {"odds", "handicap"}:
                    try:
                        parsed = float(val)
                    except ValueError:
                        per_column_invalid[col] += 1
                        continue
                    if col_type == "odds" and parsed <= 0:
                        sanity_violations["non_positive_odds"] += 1

            fthg = _maybe_int(row.get("FTHG"))
            ftag = _maybe_int(row.get("FTAG"))
            ftr = (row.get("FTR") or "").strip()
            if fthg is not None and ftag is not None and ftr:
                expected_ftr = _expected_result(fthg, ftag)
                if expected_ftr and ftr != expected_ftr:
                    sanity_violations["ftr_mismatch"] += 1

            hthg = _maybe_int(row.get("HTHG"))
            htag = _maybe_int(row.get("HTAG"))
            htr = (row.get("HTR") or "").strip()
            if hthg is not None and htag is not None and htr:
                expected_htr = _expected_result(hthg, htag)
                if expected_htr and htr != expected_htr:
                    sanity_violations["htr_mismatch"] += 1

            hs = _maybe_int(row.get("HS"))
            hst = _maybe_int(row.get("HST"))
            if hs is not None and hst is not None and hst > hs:
                sanity_violations["hst_gt_hs"] += 1

            as_ = _maybe_int(row.get("AS"))
            ast = _maybe_int(row.get("AST"))
            if as_ is not None and ast is not None and ast > as_:
                sanity_violations["ast_gt_as"] += 1

    return InspectionReport(
        row_count=row_count,
        columns=list(columns),
        missing_columns=missing_columns,
        extra_columns=extra_columns,
        unknown_columns=unknown_columns,
        order_mismatch=order_mismatch,
        per_column_missing=per_column_missing,
        per_column_invalid=per_column_invalid,
        sanity_violations=sanity_violations,
        column_types=column_types,
    )


def extract_team_entries(
    csv_path: str | Path,
    team: str,
    side: str = "both",
    *,
    case_sensitive: bool = False,
    max_rows: int | None = None,
) -> list[dict[str, str]]:
    side_key = side.strip().lower()
    if side_key not in {"home", "away", "both"}:
        raise ValueError("side must be one of: 'home', 'away', 'both'")

    needle = team if case_sensitive else team.lower()

    results: list[dict[str, str]] = []
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        row_count = 0
        for row in reader:
            if max_rows is not None and row_count >= max_rows:
                break
            row_count += 1

            home = row.get("HomeTeam", "") or ""
            away = row.get("AwayTeam", "") or ""
            home_key = home if case_sensitive else home.lower()
            away_key = away if case_sensitive else away.lower()

            if side_key == "home" and home_key != needle:
                continue
            if side_key == "away" and away_key != needle:
                continue
            if side_key == "both" and home_key != needle and away_key != needle:
                continue

            results.append(dict(row))

    return results


def _maybe_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _expected_result(home_goals: int, away_goals: int) -> str | None:
    if home_goals > away_goals:
        return "H"
    if away_goals > home_goals:
        return "A"
    return "D"


def normalize_by_team(
    entries: Iterable[dict[str, str]],
    extract_team: str,
    *,
    case_sensitive: bool = False,
    keep_original: bool = False,
) -> list[dict[str, object]]:
    team_key = extract_team if case_sensitive else extract_team.lower()

    pairs = [
        ("FTHG", "FTAG", "total_goals", "opponent_total_goals"),
        ("HTHG", "HTAG", "halftime_goals", "opponent_halftime_goals"),
        ("HS", "AS", "shots", "opponent_shots"),
        ("HST", "AST", "shots_on_target", "opponent_shots_on_target"),
        ("HHW", "AHW", "hit_woodwork", "opponent_hit_woodwork"),
        ("HC", "AC", "corners", "opponent_corners"),
        ("HF", "AF", "fouls", "opponent_fouls"),
        ("HFKC", "AFKC", "free_kicks_conceded", "opponent_free_kicks_conceded"),
        ("HO", "AO", "offsides", "opponent_offsides"),
        ("HY", "AY", "yellow_cards", "opponent_yellow_cards"),
        ("HR", "AR", "red_cards", "opponent_red_cards"),
        ("HBP", "ABP", "bookings_points", "opponent_bookings_points"),
    ]

    normalized: list[dict[str, object]] = []
    for row in entries:
        home = row.get("HomeTeam", "") or ""
        away = row.get("AwayTeam", "") or ""
        home_key = home if case_sensitive else home.lower()
        away_key = away if case_sensitive else away.lower()

        if home_key == team_key:
            is_home = True
            team_name = home
            opponent = away
        elif away_key == team_key:
            is_home = False
            team_name = away
            opponent = home
        else:
            raise ValueError(
                f"Entry does not match team '{extract_team}': "
                f"{home} vs {away}"
            )

        base: dict[str, object] = {
            "team": team_name,
            "opponent": opponent,
            "venue": "home" if is_home else "away",
            "home_away": "home" if is_home else "away",
            "result": _normalize_result(row, is_home),
            "Div": row.get("Div", ""),
            "Date": row.get("Date", ""),
            "Time": row.get("Time", ""),
            "Referee": row.get("Referee", ""),
            "Attendance": _maybe_int(row.get("Attendance")),
        }

        for home_col, away_col, team_field, opp_field in pairs:
            if is_home:
                base[team_field] = _maybe_int(row.get(home_col))
                base[opp_field] = _maybe_int(row.get(away_col))
            else:
                base[team_field] = _maybe_int(row.get(away_col))
                base[opp_field] = _maybe_int(row.get(home_col))

        if keep_original:
            base["raw"] = dict(row)

        normalized.append(base)

    return normalized


def extract_team_entries_from_db(
    db_path: str | Path,
    *,
    team: str,
    side: str = "both",
    competition_code: str = "E0",
    seasons: Iterable[str] | None = None,
    max_rows: int | None = None,
    source_scope: str = "",
) -> list[dict[str, object]]:
    season_list = (
        [value.strip() for value in seasons if value.strip()]
        if seasons is not None
        else None
    )
    conn = initialize_db(db_path)
    try:
        repo = FootstatRepo(conn)
        rows = repo.fetch_team_match_stats(
            team,
            side=side,
            competition_code=competition_code,
            seasons=season_list,
            source_scope=source_scope,
        )
    finally:
        conn.close()

    if max_rows is not None:
        return rows[:max_rows]
    return rows


def load_normalized_team_rows(
    *,
    source: str,
    team: str,
    side: str = "both",
    csv_path: str | Path = "data/football-data.co.uk/E0.csv",
    db_path: str | Path = "data/footstat.sqlite3",
    competition_code: str = "E0",
    seasons: Iterable[str] | None = None,
    case_sensitive: bool = False,
    keep_original: bool = False,
    max_rows: int | None = None,
    source_scope: str = "",
) -> list[dict[str, object]]:
    source_key = source.strip().lower()
    if source_key == "csv":
        entries = extract_team_entries(
            csv_path,
            team=team,
            side=side,
            case_sensitive=case_sensitive,
            max_rows=max_rows,
        )
        return normalize_by_team(
            entries,
            extract_team=team,
            case_sensitive=case_sensitive,
            keep_original=keep_original,
        )
    if source_key == "db":
        season_list = (
            [value.strip() for value in seasons if value.strip()]
            if seasons is not None
            else None
        )
        conn = initialize_db(db_path)
        try:
            repo = FootstatRepo(conn)
            rows = repo.fetch_normalized_team_rows(
                team,
                side=side,
                competition_code=competition_code,
                seasons=season_list,
                source_scope=source_scope,
            )
        finally:
            conn.close()
        if max_rows is not None:
            return rows[:max_rows]
        return rows
    raise ValueError("source must be 'csv' or 'db'")


def correlation_for_team(
    *,
    source: str,
    team: str,
    side: str = "both",
    csv_path: str | Path = "data/football-data.co.uk/E0.csv",
    db_path: str | Path = "data/footstat.sqlite3",
    competition_code: str = "E0",
    seasons: Iterable[str] | None = None,
    case_sensitive: bool = False,
    result_key: str = "result",
    result_map: dict[str, float] | None = None,
    result_mode: str = "outcome",
    target: str | None = None,
    feature_set: str | None = None,
    fields: Iterable[str] | None = None,
    method: str = "pearson",
    min_pairs: int = 3,
    alpha: float = 0.05,
    pvalue_method: str = "auto",
    permutations: int = 0,
    ci_method: str = "auto",
    ci_samples: int = 300,
    seed: int | None = None,
    source_scope: str = "",
) -> list[CorrelationResult]:
    normalized = load_normalized_team_rows(
        source=source,
        team=team,
        side=side,
        csv_path=csv_path,
        db_path=db_path,
        competition_code=competition_code,
        seasons=seasons,
        case_sensitive=case_sensitive,
        keep_original=False,
        max_rows=None,
        source_scope=source_scope,
    )
    return correlation_with_result(
        normalized,
        fields=fields,
        target=target,
        feature_set=feature_set,
        result_key=result_key,
        result_map=result_map,
        result_mode=result_mode,
        method=method,
        min_pairs=min_pairs,
        alpha=alpha,
        pvalue_method=pvalue_method,
        permutations=permutations,
        ci_method=ci_method,
        ci_samples=ci_samples,
        seed=seed,
    )


def correlation_with_result(
    entries: Iterable[dict[str, object]],
    *,
    fields: Iterable[str] | None = None,
    target: str | None = None,
    feature_set: str | None = None,
    result_key: str = "result",
    result_map: dict[str, float] | None = None,
    result_mode: str = "outcome",
    method: str = "pearson",
    min_pairs: int = 3,
    alpha: float = 0.05,
    pvalue_method: str = "auto",
    permutations: int = 0,
    ci_method: str = "auto",
    ci_samples: int = 300,
    seed: int | None = None,
) -> list[CorrelationResult]:
    method_key = method.strip().lower()
    if method_key not in {
        "pearson",
        "spearman",
        "kendall",
        "pointbiserial",
        "distance",
    }:
        raise ValueError(
            "method must be 'pearson', 'spearman', 'kendall', 'pointbiserial', or "
            "'distance'"
        )

    target_key = (target or result_mode).strip().lower()
    if target_key not in {
        "outcome",
        "points",
        "winloss",
        "goal_diff",
        "goals_for",
        "goals_against",
    }:
        raise ValueError(
            "target must be 'outcome', 'points', 'winloss', 'goal_diff', "
            "'goals_for', or 'goals_against'"
        )

    pvalue_key = pvalue_method.strip().lower()
    if pvalue_key not in {"auto", "analytic", "permutation"}:
        raise ValueError("pvalue_method must be 'auto', 'analytic', or 'permutation'")

    ci_key = ci_method.strip().lower()
    if ci_key not in {"auto", "fisher", "bootstrap", "none"}:
        raise ValueError("ci_method must be 'auto', 'fisher', 'bootstrap', or 'none'")

    results_map: dict[str, float] | None = None
    if target_key in {"outcome", "points", "winloss"}:
        if result_map is not None:
            results_map = dict(result_map)
        elif target_key == "points":
            results_map = {"win": 3.0, "draw": 1.0, "loss": 0.0}
        elif target_key == "winloss":
            results_map = {"win": 1.0, "draw": 0.0, "loss": 0.0}
        else:
            results_map = {"win": 1.0, "draw": 0.0, "loss": -1.0}

    rows = list(entries)
    if not rows:
        return []

    if target_key in {"goal_diff", "goals_for", "goals_against"}:
        _require_fields(
            rows,
            {"total_goals", "opponent_total_goals"},
            context="Target mode",
        )

    feature_key = feature_set.strip().lower() if feature_set else None
    if feature_key not in {None, "base", "with_opponent", "with_diffs", "all"}:
        raise ValueError(
            "feature_set must be 'base', 'with_opponent', 'with_diffs', or 'all'"
        )

    if feature_key in {"with_diffs", "all"}:
        rows = _add_diff_features(rows)

    if fields is not None:
        field_list = list(fields)
    elif feature_key is None:
        field_list = _default_numeric_fields(rows)
    else:
        field_list = _fields_for_feature_set(rows, feature_key)

    results: list[CorrelationResult] = []
    for field in field_list:
        xs: list[float] = []
        ys: list[float] = []
        for row in rows:
            value = row.get(field)
            if value is None:
                continue
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            if not isinstance(value, (int, float)):
                continue

            target_value = _target_value(
                row,
                target_key,
                result_key=result_key,
                result_map=results_map,
            )
            if target_value is None:
                continue

            xs.append(float(value))
            ys.append(float(target_value))

        if method_key == "pointbiserial" and len(ys) >= min_pairs:
            distinct = {value for value in ys}
            if len(distinct) != 2:
                raise ValueError(
                    "pointbiserial requires a binary result mapping; "
                    "use target='winloss' or provide a custom result_map."
                )

        r, p_value = _compute_corr_and_pvalue(
            method_key,
            xs,
            ys,
            pvalue_key,
            permutations,
            seed,
            min_pairs=min_pairs,
        )
        ci_low, ci_high = _compute_ci(
            method_key,
            xs,
            ys,
            r,
            ci_key,
            ci_samples,
            alpha,
            seed,
        )
        results.append(
            CorrelationResult(
                field=field,
                n=len(xs),
                r=r,
                p_value=p_value,
                q_value=None,
                ci_low=ci_low,
                ci_high=ci_high,
            )
        )

    results.sort(key=lambda item: (item.r is None, -abs(item.r or 0.0)))
    return results


def apply_fdr_correction(
    results: Iterable[CorrelationResult],
    *,
    method: str = "bh",
) -> list[CorrelationResult]:
    method_key = method.strip().lower()
    if method_key != "bh":
        raise ValueError("Only Benjamini-Hochberg ('bh') adjustment is supported.")

    results_list = list(results)
    p_values: dict[str, float | None] = {
        item.field: item.p_value for item in results_list
    }
    q_values = benjamini_hochberg(p_values)

    adjusted: list[CorrelationResult] = []
    for item in results_list:
        adjusted.append(
            CorrelationResult(
                field=item.field,
                n=item.n,
                r=item.r,
                p_value=item.p_value,
                q_value=q_values.get(item.field),
                ci_low=item.ci_low,
                ci_high=item.ci_high,
            )
        )
    return adjusted


def benjamini_hochberg(
    p_values: dict[str, float | None],
) -> dict[str, float | None]:
    valid = [(field, p) for field, p in p_values.items() if p is not None]
    m = len(valid)
    if m == 0:
        return {field: None for field in p_values}

    sorted_vals = sorted(valid, key=lambda item: item[1])
    q_temp: dict[str, float] = {}
    for idx, (field, p) in enumerate(sorted_vals, start=1):
        q_temp[field] = min(1.0, max(0.0, p * m / idx))

    q_values: dict[str, float] = {}
    prev = 1.0
    for field, _ in reversed(sorted_vals):
        q = min(q_temp[field], prev)
        q_values[field] = min(1.0, max(0.0, q))
        prev = q_values[field]

    results: dict[str, float | None] = {}
    for field in p_values:
        results[field] = q_values.get(field)
    return results


def _target_value(
    row: dict[str, object],
    target: str,
    *,
    result_key: str,
    result_map: dict[str, float] | None,
) -> float | None:
    if target in {"goal_diff", "goals_for", "goals_against"}:
        goals_for = _coerce_float(row.get("total_goals"))
        goals_against = _coerce_float(row.get("opponent_total_goals"))
        if goals_for is None or goals_against is None:
            return None
        if target == "goal_diff":
            return goals_for - goals_against
        if target == "goals_for":
            return goals_for
        return goals_against

    raw_result = row.get(result_key, "")
    if not isinstance(raw_result, str):
        return None
    if result_map is None:
        return None
    return result_map.get(raw_result.strip().lower())


def _require_fields(
    rows: list[dict[str, object]],
    required: set[str],
    *,
    context: str,
) -> None:
    present: set[str] = set()
    for row in rows:
        present.update(row.keys())
    missing = sorted(required - present)
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(f"{context} requires fields: {missing_list}")


def _fields_for_feature_set(rows: list[dict[str, object]], feature_set: str) -> list[str]:
    all_fields = _default_numeric_fields(rows)
    if feature_set == "base":
        return [
            field
            for field in all_fields
            if not field.startswith("opponent_") and not field.startswith("diff_")
        ]
    if feature_set == "with_opponent":
        return [field for field in all_fields if not field.startswith("diff_")]
    if feature_set == "with_diffs":
        return [
            field for field in all_fields if not field.startswith("opponent_")
        ]
    return all_fields


def _add_diff_features(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    augmented: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        base_fields = [
            key
            for key in row
            if not key.startswith("opponent_") and not key.startswith("diff_")
        ]
        for field in base_fields:
            opp_field = f"opponent_{field}"
            if opp_field not in row:
                continue
            team_value = _coerce_float(row.get(field))
            opp_value = _coerce_float(row.get(opp_field))
            diff_value = None
            if team_value is not None and opp_value is not None:
                diff_value = float(team_value - opp_value)
            updated[f"diff_{field}"] = diff_value
        augmented.append(updated)
    return augmented


def _normalize_result(row: dict[str, str], is_home: bool) -> str:
    ftr = (row.get("FTR") or "").strip()
    if not ftr:
        fthg = _maybe_int(row.get("FTHG"))
        ftag = _maybe_int(row.get("FTAG"))
        if fthg is None or ftag is None:
            return ""
        ftr = _expected_result(fthg, ftag) or ""
    if ftr == "D":
        return "draw"
    if is_home:
        return "win" if ftr == "H" else "loss"
    return "win" if ftr == "A" else "loss"


def _pearson_r(xs: list[float], ys: list[float], *, min_pairs: int = 3) -> float | None:
    if len(xs) != len(ys) or len(xs) < min_pairs:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = 0.0
    den_x = 0.0
    den_y = 0.0
    for x, y in zip(xs, ys, strict=True):
        dx = x - mean_x
        dy = y - mean_y
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy
    if den_x == 0.0 or den_y == 0.0:
        return None
    return num / math.sqrt(den_x * den_y)


def _spearman_r(xs: list[float], ys: list[float], *, min_pairs: int = 3) -> float | None:
    if len(xs) != len(ys) or len(xs) < min_pairs:
        return None
    return _pearson_r(_rank(xs), _rank(ys), min_pairs=min_pairs)


def _rank(values: list[float]) -> list[float]:
    indexed = list(enumerate(values))
    indexed.sort(key=lambda item: item[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            idx = indexed[k][0]
            ranks[idx] = avg_rank
        i = j
    return ranks


def _kendall_tau(
    xs: list[float], ys: list[float], *, min_pairs: int = 3
) -> float | None:
    if len(xs) != len(ys) or len(xs) < min_pairs:
        return None
    n = len(xs)
    concordant = 0
    discordant = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            if dx == 0 or dy == 0:
                continue
            if dx * dy > 0:
                concordant += 1
            else:
                discordant += 1

    n0 = n * (n - 1) / 2.0
    tie_x = _count_ties(xs)
    tie_y = _count_ties(ys)
    n1 = sum(count * (count - 1) / 2.0 for count in tie_x.values())
    n2 = sum(count * (count - 1) / 2.0 for count in tie_y.values())
    denom = math.sqrt((n0 - n1) * (n0 - n2))
    if denom == 0.0:
        return None
    return (concordant - discordant) / denom


def _count_ties(values: list[float]) -> dict[float, int]:
    counts: dict[float, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _compute_corr_and_pvalue(
    method: str,
    xs: list[float],
    ys: list[float],
    pvalue_method: str,
    permutations: int,
    seed: int | None,
    *,
    min_pairs: int,
) -> tuple[float | None, float | None]:
    if len(xs) < min_pairs:
        return None, None

    p_value: float | None = None
    r: float | None = None

    if pvalue_method in {"auto", "analytic"} and _stats is not None:
        r, p_value = _scipy_correlation(method, xs, ys)
    else:
        r = _compute_stat_only(method, xs, ys, min_pairs=min_pairs)

    if pvalue_method == "permutation" or (
        pvalue_method == "auto" and p_value is None and permutations > 0
    ):
        if r is None:
            return None, None
        p_value = _permutation_pvalue(
            method,
            xs,
            ys,
            r,
            permutations=permutations,
            seed=seed,
        )

    if pvalue_method == "analytic" and p_value is None:
        if method in {"pearson", "pointbiserial"}:
            p_value = _fisher_p_value(r, len(xs))
        elif _stats is None:
            raise ImportError("scipy is required for analytic p-values")

    return r, p_value


def _compute_ci(
    method: str,
    xs: list[float],
    ys: list[float],
    r: float | None,
    ci_method: str,
    ci_samples: int,
    alpha: float,
    seed: int | None,
) -> tuple[float | None, float | None]:
    if r is None:
        return None, None
    if ci_method == "none":
        return None, None
    if ci_method == "fisher" or (ci_method == "auto" and method in {"pearson", "pointbiserial"}):
        return _fisher_ci(r, len(xs), alpha=alpha)
    if ci_method in {"bootstrap", "auto"}:
        return _bootstrap_ci(method, xs, ys, ci_samples, alpha, seed)
    return None, None


def _compute_stat_only(
    method: str, xs: list[float], ys: list[float], *, min_pairs: int
) -> float | None:
    if method == "pearson":
        return _pearson_r(xs, ys, min_pairs=min_pairs)
    if method == "spearman":
        return _spearman_r(xs, ys, min_pairs=min_pairs)
    if method == "kendall":
        if _stats is None:
            return _kendall_tau(xs, ys, min_pairs=min_pairs)
        tau, _ = _stats.kendalltau(xs, ys)
        return float(tau) if tau is not None else None
    if method == "pointbiserial":
        return _pearson_r(xs, ys, min_pairs=min_pairs)
    if method == "distance":
        return _distance_correlation(xs, ys, min_pairs=min_pairs)
    return None


def _scipy_correlation(
    method: str, xs: list[float], ys: list[float]
) -> tuple[float | None, float | None]:
    if _stats is None:
        raise ImportError("scipy is required for analytic p-values")
    if method == "pearson":
        r, p = _stats.pearsonr(xs, ys)
        return _sanitize_stat(r), _sanitize_stat(p)
    if method == "spearman":
        r, p = _stats.spearmanr(xs, ys)
        return _sanitize_stat(r), _sanitize_stat(p)
    if method == "kendall":
        r, p = _stats.kendalltau(xs, ys)
        return _sanitize_stat(r), _sanitize_stat(p)
    if method == "pointbiserial":
        r, p = _stats.pointbiserialr(ys, xs)
        return _sanitize_stat(r), _sanitize_stat(p)
    if method == "distance":
        return _distance_correlation(xs, ys, min_pairs=3), None
    return None, None


def _sanitize_stat(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if math.isnan(value):
        return None
    return value


def _permutation_pvalue(
    method: str,
    xs: list[float],
    ys: list[float],
    observed: float,
    *,
    permutations: int,
    seed: int | None,
) -> float | None:
    if permutations <= 0:
        return None
    rng = random.Random(seed)
    more_extreme = 0
    total = 0
    two_sided = method != "distance"
    for _ in range(permutations):
        ys_perm = ys[:]
        rng.shuffle(ys_perm)
        stat = _compute_stat_only(method, xs, ys_perm, min_pairs=2)
        if stat is None:
            continue
        total += 1
        if two_sided:
            if abs(stat) >= abs(observed):
                more_extreme += 1
        else:
            if stat >= observed:
                more_extreme += 1
    if total == 0:
        return None
    return (more_extreme + 1) / (total + 1)


def _bootstrap_ci(
    method: str,
    xs: list[float],
    ys: list[float],
    samples: int,
    alpha: float,
    seed: int | None,
) -> tuple[float | None, float | None]:
    if samples <= 0:
        return None, None
    rng = random.Random(seed)
    n = len(xs)
    stats: list[float] = []
    for _ in range(samples):
        idxs = [rng.randrange(n) for _ in range(n)]
        xs_sample = [xs[i] for i in idxs]
        ys_sample = [ys[i] for i in idxs]
        stat = _compute_stat_only(method, xs_sample, ys_sample, min_pairs=2)
        if stat is not None:
            stats.append(stat)
    if len(stats) < 2:
        return None, None
    stats.sort()
    low_idx = max(0, int((alpha / 2.0) * len(stats)))
    high_idx = min(len(stats) - 1, int((1.0 - alpha / 2.0) * len(stats)) - 1)
    return stats[low_idx], stats[high_idx]


def _fisher_ci(
    r: float, n: int, *, alpha: float = 0.05
) -> tuple[float | None, float | None]:
    if n < 4 or abs(r) >= 1.0:
        return r, r
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3)
    normal = statistics.NormalDist()
    z_crit = normal.inv_cdf(1.0 - alpha / 2.0)
    z_low = z - z_crit * se
    z_high = z + z_crit * se
    return math.tanh(z_low), math.tanh(z_high)


def _fisher_p_value(r: float | None, n: int) -> float | None:
    if r is None or n < 4:
        return None
    if abs(r) >= 1.0:
        return 0.0
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3)
    normal = statistics.NormalDist()
    z_stat = z / se
    return 2.0 * (1.0 - normal.cdf(abs(z_stat)))


def _distance_correlation(
    xs: list[float], ys: list[float], *, min_pairs: int = 3
) -> float | None:
    if len(xs) != len(ys) or len(xs) < min_pairs:
        return None
    n = len(xs)
    ax = _distance_matrix(xs)
    ay = _distance_matrix(ys)
    axc = _double_center(ax)
    ayc = _double_center(ay)
    dcov = 0.0
    dvar_x = 0.0
    dvar_y = 0.0
    inv_n2 = 1.0 / (n * n)
    for i in range(n):
        for j in range(n):
            dcov += axc[i][j] * ayc[i][j]
            dvar_x += axc[i][j] * axc[i][j]
            dvar_y += ayc[i][j] * ayc[i][j]
    dcov *= inv_n2
    dvar_x *= inv_n2
    dvar_y *= inv_n2
    if dvar_x <= 0.0 or dvar_y <= 0.0:
        return None
    return math.sqrt(dcov) / math.sqrt(math.sqrt(dvar_x) * math.sqrt(dvar_y))


def _distance_matrix(values: list[float]) -> list[list[float]]:
    n = len(values)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        vi = values[i]
        for j in range(n):
            matrix[i][j] = abs(vi - values[j])
    return matrix


def _double_center(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    row_means = [sum(row) / n for row in matrix]
    col_means = [sum(matrix[i][j] for i in range(n)) / n for j in range(n)]
    grand_mean = sum(row_means) / n
    centered = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            centered[i][j] = matrix[i][j] - row_means[i] - col_means[j] + grand_mean
    return centered


def _default_numeric_fields(rows: list[dict[str, object]]) -> list[str]:
    reserved = {
        "team",
        "opponent",
        "venue",
        "home_away",
        "result",
        "Div",
        "Date",
        "Time",
        "Referee",
        "raw",
    }
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if key in reserved or key in seen:
                continue
            if value is None:
                continue
            if isinstance(value, bool):
                fields.append(key)
                seen.add(key)
                continue
            if isinstance(value, (int, float)):
                fields.append(key)
                seen.add(key)
    return fields
