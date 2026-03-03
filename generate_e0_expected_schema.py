#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import pprint
import re


def _format_py_value(value: object) -> str:
    return pprint.pformat(value, width=100, sort_dicts=False)


_KEY_LINE = re.compile(r"^([^=]+?)\s*=\s*(.+)$")


def load_notes_mapping(notes_path: Path) -> dict[str, tuple[str, str | None]]:
    group = None
    mapping: dict[str, tuple[str, str | None]] = {}
    lines = notes_path.read_text(encoding="utf-8").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if line.endswith(":"):
            group = line[:-1].strip()
            continue
        if lower.startswith("match statistics"):
            group = "Match Statistics"
            continue
        if lower.startswith("key to total goals betting odds"):
            group = "Key to total goals betting odds"
            continue
        if lower.startswith("key to asian handicap betting odds"):
            group = "Key to asian handicap betting odds"
            continue
        if lower.startswith("key to results data"):
            group = "Key to results data"
            continue

        match = _KEY_LINE.match(line)
        if not match:
            continue
        keys_part, description = match.groups()
        keys = [k.strip() for k in keys_part.split(" and ")]
        for key in keys:
            if key:
                mapping[key] = (description.strip(), group)
    return mapping


def read_csv_header(csv_path: Path) -> list[str]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _derive_closing_description(
    code: str, mapping: dict[str, tuple[str, str | None]]
) -> tuple[str, str | None] | None:
    if "C" not in code:
        return None
    for idx, ch in enumerate(code):
        if ch == "C":
            base = code[:idx] + code[idx + 1 :]
            if base in mapping:
                desc, group = mapping[base]
                return (f"Closing {desc}", group)
            break
    return None


def build_expected_schema(
    notes_path: Path, csv_path: Path
) -> tuple[list[str], dict[str, dict[str, str | None]]]:
    mapping = load_notes_mapping(notes_path)
    columns = read_csv_header(csv_path)
    info: dict[str, dict[str, str | None]] = {}
    for col in columns:
        found = mapping.get(col)
        if found is None:
            found = _derive_closing_description(col, mapping)
        if found is None:
            description, group = "Unknown description (not in notes.txt)", None
        else:
            description, group = found
        info[col] = {"description": description, "group": group}
    return columns, info


def write_expected_schema(module_path: Path, schema_path: Path, notes_path: Path) -> None:
    columns, info = build_expected_schema(notes_path, schema_path)

    lines: list[str] = []
    lines.append('"""Auto-generated expected schema for football-data.co.uk E0.csv."""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("COLUMNS: list[str] = " + _format_py_value(columns))
    lines.append("")
    lines.append("COLUMN_INFO: dict[str, dict[str, str | None]] = " + _format_py_value(info))
    lines.append("")
    lines.append(
        "EXPECTED_SCHEMA: dict[str, object] = {"
        + "'columns': COLUMNS, 'column_info': COLUMN_INFO}"
    )
    lines.append("")
    lines.append("")
    lines.append("def describe(code: str) -> str:")
    lines.append("    info = COLUMN_INFO.get(code)")
    lines.append("    if info is None:")
    lines.append("        return f\"{code}: Unknown description\"")
    lines.append("    group = info.get('group')")
    lines.append("    desc = info.get('description', '')")
    lines.append("    if group:")
    lines.append("        return f\"{code} ({group}): {desc}\"")
    lines.append("    return f\"{code}: {desc}\"")
    lines.append("")

    module_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a python module containing the expected E0.csv schema."
    )
    parser.add_argument(
        "--notes",
        default="data/football-data.co.uk/notes.txt",
        help="Path to notes.txt",
    )
    parser.add_argument(
        "--csv",
        default="data/football-data.co.uk/E0.csv",
        help="Path to E0.csv",
    )
    parser.add_argument(
        "--out",
        default="e0_expected_schema.py",
        help="Output python module path",
    )

    args = parser.parse_args()
    write_expected_schema(Path(args.out), Path(args.csv), Path(args.notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
