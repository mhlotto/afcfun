#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from e0_loader_db import (
    E0IngestSummary,
    discover_e0_csv_files,
    ingest_e0_csv,
    plan_e0_csv,
)
from footstat_db import initialize_db


def _season_override_for_path(path: Path, current_label: str | None) -> str | None:
    if path.name == "E0.csv":
        return current_label
    return None


def _resolve_paths(
    *,
    data_dir: str | Path,
    pattern: str,
    explicit_csvs: Iterable[str] | None,
) -> list[Path]:
    if explicit_csvs:
        out: list[Path] = []
        for csv_path in explicit_csvs:
            path = Path(csv_path)
            if not path.exists() or not path.is_file():
                raise ValueError(f"CSV file does not exist: {path}")
            out.append(path)
        return sorted(out)
    return discover_e0_csv_files(data_dir, pattern=pattern)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest football-data.co.uk E0 CSV files into SQLite, with optional "
            "dry-run planning and replace-source behavior."
        )
    )
    parser.add_argument(
        "--db",
        default="data/footstat.sqlite3",
        help="SQLite file path.",
    )
    parser.add_argument(
        "--data-dir",
        default="data/football-data.co.uk",
        help="Directory containing E0.csv and E0-YYYYYYYY.csv files.",
    )
    parser.add_argument(
        "--glob",
        default="E0*.csv",
        help="Glob pattern under --data-dir for selecting files.",
    )
    parser.add_argument(
        "--csv",
        action="append",
        default=None,
        help="Specific CSV file path(s); may be provided multiple times.",
    )
    parser.add_argument(
        "--current-label",
        default=None,
        help="Override season label for E0.csv (for example 2025-2026).",
    )
    parser.add_argument(
        "--loader-name",
        default="football-data-e0",
        help="Logical loader name stored in sources table.",
    )
    parser.add_argument(
        "--source-scope",
        default="football-data.co.uk",
        help="Source scope tag for loader-level behavior.",
    )
    parser.add_argument(
        "--replace-source",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Delete existing source data for each source_key before ingest.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan ingest without writing to DB.",
    )
    args = parser.parse_args(argv)

    paths = _resolve_paths(
        data_dir=args.data_dir,
        pattern=args.glob,
        explicit_csvs=args.csv,
    )
    if not paths:
        raise ValueError("No matching E0 CSV files found.")

    plans = [
        plan_e0_csv(
            path,
            season_label_override=_season_override_for_path(path, args.current_label),
        )
        for path in paths
    ]

    print(f"Files matched: {len(plans)}")
    for item in plans:
        print(
            f"- {item.csv_path} | key={item.source_key} | "
            f"rows={item.row_count} | sha256={item.checksum_sha256[:12]}..."
        )

    if args.dry_run:
        print("Dry run only: no DB writes performed.")
        return 0

    conn = initialize_db(args.db)
    try:
        summaries: list[E0IngestSummary] = []
        for path in paths:
            summary = ingest_e0_csv(
                conn,
                path,
                loader_name=args.loader_name,
                source_scope=args.source_scope,
                season_label_override=_season_override_for_path(path, args.current_label),
                replace_source=args.replace_source,
            )
            summaries.append(summary)
    finally:
        conn.close()

    total_rows = sum(item.rows_processed for item in summaries)
    total_matches = sum(item.matches_upserted for item in summaries)
    total_team_stats = sum(item.team_stats_upserted for item in summaries)
    print(f"DB: {args.db}")
    print(f"Sources ingested: {len(summaries)}")
    print(f"Rows processed: {total_rows}")
    print(f"Matches upserted: {total_matches}")
    print(f"Team-stat rows upserted: {total_team_stats}")
    print(f"Replace source: {'on' if args.replace_source else 'off'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

