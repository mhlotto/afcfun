#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from footstat_db import SCHEMA_VERSION, current_schema_version, initialize_db, list_tables


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize or migrate the footstat SQLite database."
    )
    parser.add_argument(
        "--db",
        default="data/footstat.sqlite3",
        help="SQLite file path.",
    )
    parser.add_argument(
        "--show-tables",
        action="store_true",
        help="Print all table names after migration.",
    )
    args = parser.parse_args()

    conn = initialize_db(args.db)
    try:
        version = current_schema_version(conn)
        tables = list_tables(conn)
    finally:
        conn.close()

    print(f"DB: {Path(args.db)}")
    print(f"Schema version: {version}")
    print(f"Latest supported: {SCHEMA_VERSION}")
    print(f"Table count: {len(tables)}")
    if args.show_tables:
        for table in tables:
            print(f"- {table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

