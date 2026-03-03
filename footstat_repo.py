#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from typing import Iterable


def normalize_team_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


class FootstatRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_competitions(self) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """
            SELECT id, code, name
            FROM competitions
            ORDER BY code
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_seasons(
        self,
        *,
        competition_code: str | None = None,
    ) -> list[dict[str, object]]:
        params: list[object] = []
        where = ""
        if competition_code is not None:
            where = "WHERE c.code = ?"
            params.append(competition_code)
        rows = self.conn.execute(
            f"""
            SELECT s.id, s.start_year, s.end_year, s.label, c.code AS competition_code
            FROM seasons AS s
            JOIN competitions AS c ON c.id = s.competition_id
            {where}
            ORDER BY s.start_year, s.end_year
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_teams(self) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """
            SELECT id, canonical_name, short_name, country
            FROM teams
            ORDER BY canonical_name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def resolve_team_id(
        self,
        team_name: str,
        *,
        source_scope: str = "",
    ) -> int:
        text_norm = normalize_team_text(team_name)
        if not text_norm:
            raise ValueError("team_name cannot be empty")

        canonical_rows = self.conn.execute(
            """
            SELECT id
            FROM teams
            WHERE lower(canonical_name) = ?
            """,
            (text_norm,),
        ).fetchall()
        if canonical_rows:
            return int(canonical_rows[0]["id"])

        alias_rows = self.conn.execute(
            """
            SELECT ta.team_id, ta.source_scope
            FROM team_aliases AS ta
            WHERE ta.alias_norm = ?
              AND ta.source_scope IN (?, '')
            ORDER BY CASE WHEN ta.source_scope = ? THEN 0 ELSE 1 END, ta.is_primary DESC
            """,
            (text_norm, source_scope, source_scope),
        ).fetchall()
        if not alias_rows:
            raise ValueError(f"Unknown team or alias: {team_name!r}")

        team_ids = {int(row["team_id"]) for row in alias_rows}
        if len(team_ids) > 1:
            raise ValueError(
                f"Alias {team_name!r} is ambiguous across multiple teams."
            )
        return int(alias_rows[0]["team_id"])

    def fetch_matches(
        self,
        *,
        competition_code: str | None = None,
        seasons: Iterable[str] | None = None,
        team: str | None = None,
        source_scope: str = "",
    ) -> list[dict[str, object]]:
        where: list[str] = []
        params: list[object] = []
        if competition_code is not None:
            where.append("c.code = ?")
            params.append(competition_code)
        if seasons is not None:
            labels = [label.strip() for label in seasons if label.strip()]
            if labels:
                marks = ", ".join("?" for _ in labels)
                where.append(f"s.label IN ({marks})")
                params.extend(labels)
        if team is not None:
            team_id = self.resolve_team_id(team, source_scope=source_scope)
            where.append("(m.home_team_id = ? OR m.away_team_id = ?)")
            params.extend([team_id, team_id])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        rows = self.conn.execute(
            f"""
            SELECT
                m.id,
                c.code AS competition_code,
                s.label AS season_label,
                m.match_date,
                COALESCE(m.match_time, '') AS match_time,
                ht.canonical_name AS home_team,
                at.canonical_name AS away_team,
                m.full_time_home_goals,
                m.full_time_away_goals,
                m.full_time_result,
                COALESCE(m.referee, '') AS referee,
                m.attendance
            FROM matches AS m
            JOIN competitions AS c ON c.id = m.competition_id
            JOIN seasons AS s ON s.id = m.season_id
            JOIN teams AS ht ON ht.id = m.home_team_id
            JOIN teams AS at ON at.id = m.away_team_id
            {where_sql}
            ORDER BY m.match_date, m.match_time, m.id
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_team_match_stats(
        self,
        team: str,
        *,
        side: str = "both",
        competition_code: str | None = None,
        seasons: Iterable[str] | None = None,
        source_scope: str = "",
    ) -> list[dict[str, object]]:
        side_key = side.strip().lower()
        if side_key not in {"home", "away", "both"}:
            raise ValueError("side must be one of: 'home', 'away', 'both'")

        team_id = self.resolve_team_id(team, source_scope=source_scope)
        where: list[str] = ["tms.team_id = ?"]
        params: list[object] = [team_id]
        if side_key != "both":
            where.append("tms.venue = ?")
            params.append(side_key)
        if competition_code is not None:
            where.append("c.code = ?")
            params.append(competition_code)
        if seasons is not None:
            labels = [label.strip() for label in seasons if label.strip()]
            if labels:
                marks = ", ".join("?" for _ in labels)
                where.append(f"s.label IN ({marks})")
                params.extend(labels)

        where_sql = " AND ".join(where)
        rows = self.conn.execute(
            f"""
            SELECT
                tms.id,
                tms.match_id,
                c.code AS competition_code,
                s.label AS season_label,
                tms.match_date,
                COALESCE(m.match_time, '') AS match_time,
                t.canonical_name AS team,
                ot.canonical_name AS opponent,
                tms.venue,
                tms.result,
                COALESCE(m.referee, '') AS referee,
                m.attendance,
                tms.total_goals,
                tms.opponent_total_goals,
                tms.halftime_goals,
                tms.opponent_halftime_goals,
                tms.shots,
                tms.opponent_shots,
                tms.shots_on_target,
                tms.opponent_shots_on_target,
                tms.hit_woodwork,
                tms.opponent_hit_woodwork,
                tms.corners,
                tms.opponent_corners,
                tms.fouls,
                tms.opponent_fouls,
                tms.free_kicks_conceded,
                tms.opponent_free_kicks_conceded,
                tms.offsides,
                tms.opponent_offsides,
                tms.yellow_cards,
                tms.opponent_yellow_cards,
                tms.red_cards,
                tms.opponent_red_cards,
                tms.bookings_points,
                tms.opponent_bookings_points
            FROM team_match_stats AS tms
            JOIN matches AS m ON m.id = tms.match_id
            JOIN competitions AS c ON c.id = tms.competition_id
            JOIN seasons AS s ON s.id = tms.season_id
            JOIN teams AS t ON t.id = tms.team_id
            JOIN teams AS ot ON ot.id = tms.opponent_team_id
            WHERE {where_sql}
            ORDER BY tms.match_date, m.match_time, tms.match_id
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_normalized_team_rows(
        self,
        team: str,
        *,
        side: str = "both",
        competition_code: str | None = None,
        seasons: Iterable[str] | None = None,
        source_scope: str = "",
    ) -> list[dict[str, object]]:
        stats_rows = self.fetch_team_match_stats(
            team,
            side=side,
            competition_code=competition_code,
            seasons=seasons,
            source_scope=source_scope,
        )
        normalized: list[dict[str, object]] = []
        for row in stats_rows:
            normalized.append(
                {
                    "team": row["team"],
                    "opponent": row["opponent"],
                    "venue": row["venue"],
                    "home_away": row["venue"],
                    "result": row["result"],
                    "Div": row["competition_code"],
                    "Date": row["match_date"],
                    "Time": row["match_time"],
                    "Referee": row["referee"],
                    "Attendance": row["attendance"],
                    "season": row["season_label"],
                    "total_goals": row["total_goals"],
                    "opponent_total_goals": row["opponent_total_goals"],
                    "halftime_goals": row["halftime_goals"],
                    "opponent_halftime_goals": row["opponent_halftime_goals"],
                    "shots": row["shots"],
                    "opponent_shots": row["opponent_shots"],
                    "shots_on_target": row["shots_on_target"],
                    "opponent_shots_on_target": row["opponent_shots_on_target"],
                    "hit_woodwork": row["hit_woodwork"],
                    "opponent_hit_woodwork": row["opponent_hit_woodwork"],
                    "corners": row["corners"],
                    "opponent_corners": row["opponent_corners"],
                    "fouls": row["fouls"],
                    "opponent_fouls": row["opponent_fouls"],
                    "free_kicks_conceded": row["free_kicks_conceded"],
                    "opponent_free_kicks_conceded": row[
                        "opponent_free_kicks_conceded"
                    ],
                    "offsides": row["offsides"],
                    "opponent_offsides": row["opponent_offsides"],
                    "yellow_cards": row["yellow_cards"],
                    "opponent_yellow_cards": row["opponent_yellow_cards"],
                    "red_cards": row["red_cards"],
                    "opponent_red_cards": row["opponent_red_cards"],
                    "bookings_points": row["bookings_points"],
                    "opponent_bookings_points": row["opponent_bookings_points"],
                }
            )
        return normalized

