#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from footstat_repo import FootstatRepo, normalize_team_text


# Common long-form EPL names seen in schedule sources mapped to DB canonical names.
SCHEDULE_NAME_ALIASES: dict[str, str] = {
    "Brighton & Hove Albion": "Brighton",
    "Leeds United": "Leeds",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
}


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path}: expected top-level JSON list")
    rows: list[dict[str, Any]] = []
    for i, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: row {i} expected object, got {type(item).__name__}")
        rows.append(item)
    return rows


def _candidate_names(opponent: str) -> list[tuple[str, str]]:
    text = opponent.strip()
    candidates: list[tuple[str, str]] = []
    if not text:
        return candidates

    # Keep original name first.
    candidates.append((text, "direct"))

    mapped = SCHEDULE_NAME_ALIASES.get(text)
    if mapped and mapped != text:
        candidates.append((mapped, "alias_map"))

    # Lightweight heuristics as fallback only.
    heuristics: list[str] = []
    if text.startswith("Manchester "):
        heuristics.append(text.replace("Manchester ", "Man ", 1))
    if text.endswith(" United"):
        heuristics.append(text[: -len(" United")])
    if text.endswith(" Wanderers"):
        heuristics.append(text[: -len(" Wanderers")])

    for guess in heuristics:
        guess_clean = guess.strip()
        if guess_clean and guess_clean != text:
            candidates.append((guess_clean, "heuristic"))

    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name, method in candidates:
        key = normalize_team_text(name)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, method))
    return out


def _resolve_team(
    repo: FootstatRepo,
    opponent: str,
    *,
    source_scope: str,
    team_names_by_id: dict[int, str],
) -> tuple[int, str, str, str] | None:
    for candidate, method in _candidate_names(opponent):
        try:
            team_id = repo.resolve_team_id(candidate, source_scope=source_scope)
        except ValueError:
            continue
        canonical = team_names_by_id.get(team_id, candidate)
        return team_id, canonical, candidate, method
    return None


def _upsert_aliases(
    conn: sqlite3.Connection,
    *,
    alias_rows: list[tuple[int, str, str]],
    source_scope: str,
) -> None:
    if not alias_rows:
        return
    conn.executemany(
        """
        INSERT INTO team_aliases(team_id, alias, alias_norm, source_scope, is_primary)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(alias_norm, source_scope) DO UPDATE SET
            team_id = excluded.team_id,
            alias = excluded.alias
        """,
        [(team_id, alias, normalize_team_text(alias), source_scope) for team_id, alias, _ in alias_rows],
    )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize schedule opponent names to DB teams and flag unresolved rows."
    )
    parser.add_argument(
        "--db",
        default="data/footstat.sqlite3",
        help="SQLite DB path (default: data/footstat.sqlite3)",
    )
    parser.add_argument(
        "--in",
        dest="in_json",
        required=True,
        help="Input schedule JSON (list of fixtures).",
    )
    parser.add_argument(
        "--out",
        dest="out_json",
        default="",
        help="Output normalized JSON path (default: <input>.normalized.json)",
    )
    parser.add_argument(
        "--source-scope",
        default="",
        help="Alias source scope for team resolution (default: '').",
    )
    parser.add_argument(
        "--write-aliases",
        action="store_true",
        help="Upsert resolved non-canonical schedule names into team_aliases.",
    )
    parser.add_argument(
        "--alias-source-scope",
        default="schedule",
        help="Source scope to use when writing aliases (default: schedule).",
    )
    args = parser.parse_args()

    db_path = _resolve_path(args.db)
    in_path = _resolve_path(args.in_json)
    out_path = (
        _resolve_path(args.out_json)
        if args.out_json.strip()
        else in_path.with_name(f"{in_path.stem}.normalized.json")
    )

    rows = _load_rows(in_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    repo = FootstatRepo(conn)
    teams = repo.list_teams()
    team_names_by_id = {int(item["id"]): str(item["canonical_name"]) for item in teams}

    normalized_rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    alias_rows_to_write: list[tuple[int, str, str]] = []

    for row in rows:
        out_row = dict(row)
        opponent = str(row.get("opponent", "")).strip()
        out_row["opponent_input"] = opponent

        resolved = _resolve_team(
            repo,
            opponent,
            source_scope=args.source_scope,
            team_names_by_id=team_names_by_id,
        )
        if resolved is None:
            out_row["opponent_team_id"] = None
            out_row["opponent_canonical_name"] = None
            out_row["opponent_resolution_method"] = "unresolved"
            unresolved.append(
                {
                    "matchday": row.get("matchday"),
                    "opponent": opponent,
                    "venue": row.get("venue"),
                    "kickoff_utc": row.get("kickoff_utc"),
                }
            )
            normalized_rows.append(out_row)
            continue

        team_id, canonical_name, matched_name, method = resolved
        out_row["opponent_team_id"] = team_id
        out_row["opponent_canonical_name"] = canonical_name
        out_row["opponent_resolution_method"] = method
        out_row["opponent_matched_name"] = matched_name
        normalized_rows.append(out_row)

        if args.write_aliases and opponent and normalize_team_text(opponent) != normalize_team_text(canonical_name):
            alias_rows_to_write.append((team_id, opponent, canonical_name))

    if args.write_aliases:
        _upsert_aliases(
            conn,
            alias_rows=alias_rows_to_write,
            source_scope=args.alias_source_scope,
        )

    payload = {
        "meta": {
            "source_schedule": str(in_path),
            "db_path": str(db_path),
            "source_scope": args.source_scope,
            "rows": len(normalized_rows),
            "resolved_rows": len(normalized_rows) - len(unresolved),
            "unresolved_rows": len(unresolved),
            "aliases_written": len(alias_rows_to_write) if args.write_aliases else 0,
        },
        "rows": normalized_rows,
        "unresolved": unresolved,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Rows: {len(normalized_rows)}")
    print(f"Resolved: {len(normalized_rows) - len(unresolved)}")
    print(f"Unresolved: {len(unresolved)}")
    if unresolved:
        print("Unresolved opponents:")
        for item in unresolved[:10]:
            print(
                f"- matchday={item.get('matchday')} opponent={item.get('opponent')!r} "
                f"kickoff={item.get('kickoff_utc')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

