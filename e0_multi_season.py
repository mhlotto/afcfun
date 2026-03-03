#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from e0_season_utils import normalize_season_token, parse_season_filter
from e0_weekly_halfwin_plot import WeeklyAveragePoint, build_weekly_half_win_average
from e0_inspect import extract_team_entries, normalize_by_team


_SEASON_FILE_RE = re.compile(r"^E0-(\d{4})(\d{4})\.csv$")


@dataclass(frozen=True)
class SeasonSource:
    label: str
    path: Path
    is_current: bool

    @property
    def start_year(self) -> int:
        return int(self.label[:4])


def _label_from_historic_filename(name: str) -> str | None:
    match = _SEASON_FILE_RE.match(name)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if end != start + 1:
        return None
    return f"{start:04d}-{end:04d}"


def _parse_date_year(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            return parsed.year
        except ValueError:
            continue
    return None


def infer_season_label(csv_path: str | Path) -> str:
    years: list[int] = []
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            year = _parse_date_year(str(row.get("Date", "")))
            if year is not None:
                years.append(year)
    if not years:
        raise ValueError(
            f"Cannot infer season label from {csv_path!s}; no parseable Date values."
        )
    start = min(years)
    end = max(years)
    if end == start:
        end = start + 1
    if end != start + 1:
        raise ValueError(
            f"Cannot infer a single-season range from {csv_path!s}: "
            f"years={start}..{end}."
        )
    return f"{start:04d}-{end:04d}"


def discover_season_sources(
    data_dir: str | Path,
    *,
    include_current: bool = True,
    current_label: str | None = None,
) -> list[SeasonSource]:
    root = Path(data_dir)
    if not root.exists():
        raise ValueError(f"Data directory does not exist: {root}")

    sources: list[SeasonSource] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        label = _label_from_historic_filename(path.name)
        if label is None:
            continue
        sources.append(SeasonSource(label=label, path=path, is_current=False))

    if include_current:
        current_path = root / "E0.csv"
        if current_path.exists():
            label = (
                normalize_season_token(current_label)
                if current_label
                else infer_season_label(current_path)
            )
            sources.append(
                SeasonSource(label=label, path=current_path, is_current=True)
            )

    sources.sort(key=lambda source: (source.start_year, source.is_current))
    return sources


def build_multi_season_series(
    *,
    data_dir: str | Path,
    teams: list[str],
    side: str,
    seasons: Iterable[str] | None = None,
    include_current: bool = True,
    current_label: str | None = None,
) -> tuple[dict[str, list[WeeklyAveragePoint]], list[SeasonSource]]:
    sources = discover_season_sources(
        data_dir,
        include_current=include_current,
        current_label=current_label,
    )
    if not sources:
        raise ValueError(f"No E0 season files found in {data_dir}.")

    selected_labels = None
    if seasons is not None:
        selected_labels = {normalize_season_token(token) for token in seasons}
        sources = [source for source in sources if source.label in selected_labels]
        if not sources:
            wanted = ", ".join(sorted(selected_labels))
            raise ValueError(f"No season files matched requested seasons: {wanted}.")

    series: dict[str, list[WeeklyAveragePoint]] = {}
    for team in teams:
        for source in sources:
            entries = extract_team_entries(source.path, team=team, side=side)
            if not entries:
                continue
            normalized = normalize_by_team(entries, extract_team=team)
            points = build_weekly_half_win_average(normalized)
            if not points:
                continue
            key = f"{team} ({source.label})"
            series[key] = points

    if not series:
        raise ValueError(
            "No matching rows found for the requested team/season selection."
        )
    return series, sources
