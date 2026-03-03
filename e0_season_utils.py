#!/usr/bin/env python3
from __future__ import annotations

import re


_SEASON_TOKEN_RE = re.compile(r"^(\d{4})[-_/]?(\d{4})$")


def normalize_season_token(token: str) -> str:
    raw = token.strip()
    match = _SEASON_TOKEN_RE.match(raw)
    if not match:
        raise ValueError(
            f"Invalid season value {token!r}. Expected YYYY-YYYY or YYYYYYYY."
        )
    start = int(match.group(1))
    end = int(match.group(2))
    if end != start + 1:
        raise ValueError(
            f"Invalid season {token!r}: ending year must be start year + 1."
        )
    return f"{start:04d}-{end:04d}"


def parse_season_filter(value: str | None) -> list[str] | None:
    if value is None:
        return None
    tokens = [part.strip() for part in value.split(",") if part.strip()]
    if not tokens:
        return None
    normalized = [normalize_season_token(token) for token in tokens]
    seen: set[str] = set()
    unique: list[str] = []
    for label in normalized:
        if label in seen:
            continue
        unique.append(label)
        seen.add(label)
    return unique

