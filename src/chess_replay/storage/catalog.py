"""SQLite catalog for idempotent game ingestion."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from chess_replay.ingestion.chess_com import ArchivedGame


class GameCatalog:
    """Store source games by stable Chess.com game ID."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    source_id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    tournament_url TEXT,
                    white_username TEXT NOT NULL,
                    black_username TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    pgn TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def upsert_game(self, game: ArchivedGame) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO games (
                    source_id, source_url, tournament_url, white_username,
                    black_username, end_time, pgn
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_url = excluded.source_url,
                    tournament_url = excluded.tournament_url,
                    white_username = excluded.white_username,
                    black_username = excluded.black_username,
                    end_time = excluded.end_time,
                    pgn = excluded.pgn,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                (
                    game.source_id,
                    game.url,
                    game.tournament_url,
                    game.white.username,
                    game.black.username,
                    game.end_time.isoformat(),
                    game.pgn,
                ),
            )

    def contains(self, source_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM games WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return row is not None

    def count_games(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM games").fetchone()
        return int(row[0]) if row else 0

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)