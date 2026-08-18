"""Cached Stockfish evaluation through python-chess's UCI integration."""

from __future__ import annotations

import math
from dataclasses import dataclass

import chess
import chess.engine


@dataclass(frozen=True, slots=True)
class PositionEvaluation:
    """A position score from White's perspective."""

    centipawns: int
    mate_in: int | None = None

    @property
    def label(self) -> str:
        if self.mate_in is not None:
            if self.mate_in == 0:
                return "#"
            sign = "+" if self.mate_in > 0 else "-"
            return f"{sign}M{abs(self.mate_in)}"
        return f"{self.centipawns / 100:+.1f}"

    @property
    def white_fraction(self) -> float:
        if self.mate_in is not None:
            if self.mate_in > 0:
                return 0.98
            if self.mate_in < 0:
                return 0.02
            if self.centipawns > 0:
                return 1.0
            if self.centipawns < 0:
                return 0.0
            return 0.5
        return 1 / (1 + math.exp(-self.centipawns / 400))


class StockfishEvaluator:
    """Evaluate unique positions with one persistent Stockfish process."""

    def __init__(
        self,
        executable: str = "stockfish",
        *,
        time_seconds: float = 0.2,
        depth: int = 18,
        hash_mb: int = 256,
        threads: int = 2,
    ) -> None:
        if time_seconds <= 0:
            raise ValueError("Stockfish analysis time must be positive")
        if hash_mb < 16:
            raise ValueError("Stockfish hash must be at least 16 MiB")
        if depth < 1:
            raise ValueError("Stockfish depth must be positive")
        if threads < 1:
            raise ValueError("Stockfish threads must be positive")
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(executable)
        except (FileNotFoundError, PermissionError, chess.engine.EngineError) as error:
            raise RuntimeError(f"Stockfish is unavailable at {executable!r}") from error
        self._engine.configure({"Hash": hash_mb, "Threads": threads})
        self.time_seconds = time_seconds
        self.depth = depth
        self._cache: dict[str, PositionEvaluation] = {}

    def __enter__(self) -> StockfishEvaluator:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def evaluate(self, fen: str) -> PositionEvaluation:
        cached = self._cache.get(fen)
        if cached is not None:
            return cached

        board = chess.Board(fen)
        if board.is_checkmate():
            result = PositionEvaluation(
                centipawns=-100_000 if board.turn == chess.WHITE else 100_000,
                mate_in=0,
            )
        else:
            info = self._engine.analyse(
                board,
                chess.engine.Limit(time=self.time_seconds, depth=self.depth),
            )
            score = info["score"].pov(chess.WHITE)
            result = PositionEvaluation(
                centipawns=score.score(mate_score=100_000) or 0,
                mate_in=score.mate(),
            )
        self._cache[fen] = result
        return result

    def close(self) -> None:
        self._engine.quit()