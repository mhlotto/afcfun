#!/usr/bin/env python3
from __future__ import annotations

import argparse

from e0_season_utils import parse_season_filter
from e0_inspect import (
    apply_fdr_correction,
    correlation_for_team,
)


def _format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _print_table(rows: list[dict[str, str]], columns: list[str]) -> None:
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(row.get(col, "")))

    header = "  ".join(col.ljust(widths[col]) for col in columns)
    divider = "  ".join("-" * widths[col] for col in columns)
    print(header)
    print(divider)
    for row in rows:
        parts: list[str] = []
        for col in columns:
            value = row.get(col, "")
            if col == "field":
                parts.append(value.ljust(widths[col]))
            else:
                parts.append(value.rjust(widths[col]))
        print("  ".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Correlate team-normalized stats against match outcomes."
    )
    parser.add_argument(
        "--csv",
        default="data/football-data.co.uk/E0.csv",
        help="Path to E0.csv",
    )
    parser.add_argument(
        "--source",
        default="csv",
        choices=["csv", "db"],
        help="Input source mode.",
    )
    parser.add_argument(
        "--db",
        default="data/footstat.sqlite3",
        help="SQLite file path for --source db.",
    )
    parser.add_argument(
        "--competition",
        default="E0",
        help="Competition code for --source db.",
    )
    parser.add_argument(
        "--seasons",
        default=None,
        help="Optional season filters for --source db (YYYY-YYYY or YYYYYYYY, comma-delimited).",
    )
    parser.add_argument("--team", default="Arsenal", help="Team name to analyze.")
    parser.add_argument(
        "--side",
        default="both",
        choices=["home", "away", "both"],
        help="Filter matches by venue.",
    )
    parser.add_argument(
        "--method",
        default="pearson",
        choices=["pearson", "spearman", "kendall", "pointbiserial", "distance"],
        help="Correlation method.",
    )
    parser.add_argument(
        "--target",
        default=None,
        choices=["outcome", "points", "goal_diff", "goals_for", "goals_against", "winloss"],
        help="Target variable for correlation.",
    )
    parser.add_argument(
        "--result-mode",
        default="outcome",
        choices=["outcome", "points", "winloss"],
        help="(Deprecated) Outcome mapping; use --target instead.",
    )
    parser.add_argument(
        "--pvalue-method",
        default="auto",
        choices=["auto", "analytic", "permutation"],
        help="How to compute p-values.",
    )
    parser.add_argument(
        "--feature-set",
        default="with_opponent",
        choices=["base", "with_opponent", "with_diffs", "all"],
        help="Feature set to include in correlations.",
    )
    parser.add_argument(
        "--adjust",
        default="none",
        choices=["none", "bh"],
        help="Multiple-comparisons adjustment for p-values.",
    )
    parser.add_argument(
        "--fdr",
        action="store_true",
        help="Alias for --adjust=bh.",
    )
    parser.add_argument(
        "--filter-significant",
        action="store_true",
        help="Filter rows by alpha (q-value if adjusted, else p-value).",
    )
    parser.add_argument(
        "--permutations",
        type=int,
        default=0,
        help="Permutation count for permutation p-values.",
    )
    parser.add_argument(
        "--ci-method",
        default="auto",
        choices=["auto", "fisher", "bootstrap", "none"],
        help="How to compute confidence intervals.",
    )
    parser.add_argument(
        "--ci-samples",
        type=int,
        default=300,
        help="Bootstrap samples for confidence intervals.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for permutation/bootstrap.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Number of results to display.",
    )
    parser.add_argument(
        "--min-pairs",
        type=int,
        default=3,
        help="Minimum pairs needed for a correlation.",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Alpha for confidence intervals and significance filtering.",
    )

    args = parser.parse_args()

    if args.fdr:
        args.adjust = "bh"

    target = args.target or args.result_mode

    season_filter = parse_season_filter(args.seasons)
    correlations = correlation_for_team(
        source=args.source,
        team=args.team,
        side=args.side,
        csv_path=args.csv,
        db_path=args.db,
        competition_code=args.competition,
        seasons=season_filter,
        method=args.method,
        target=target,
        result_mode=args.result_mode,
        feature_set=args.feature_set,
        min_pairs=args.min_pairs,
        alpha=args.alpha,
        pvalue_method=args.pvalue_method,
        permutations=args.permutations,
        ci_method=args.ci_method,
        ci_samples=args.ci_samples,
        seed=args.seed,
    )

    if args.adjust == "bh":
        correlations = apply_fdr_correction(correlations, method="bh")

    if args.filter_significant:
        if args.adjust == "bh":
            correlations = [
                item
                for item in correlations
                if item.q_value is not None and item.q_value <= args.alpha
            ]
        else:
            correlations = [
                item
                for item in correlations
                if item.p_value is not None and item.p_value <= args.alpha
            ]

    print(
        f"Team: {args.team} | source={args.source} | side={args.side} | method={args.method} | "
        f"target={target} | feature_set={args.feature_set} | "
        f"pvalue={args.pvalue_method} | adjust={args.adjust} | ci={args.ci_method}"
    )
    rows: list[dict[str, str]] = []
    for item in correlations[: args.limit]:
        row = {
            "field": item.field,
            "r": _format_float(item.r),
            "n": str(item.n),
            "p_value": _format_float(item.p_value),
            "ci_low": _format_float(item.ci_low),
            "ci_high": _format_float(item.ci_high),
        }
        if args.adjust == "bh":
            row["q_value"] = _format_float(item.q_value)
        rows.append(row)

    columns = ["field", "r", "n", "p_value"]
    if args.adjust == "bh":
        columns.append("q_value")
    columns += ["ci_low", "ci_high"]
    _print_table(rows, columns)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
