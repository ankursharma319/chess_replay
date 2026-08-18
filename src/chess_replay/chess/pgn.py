"""Parse PGN into a deterministic replay timeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import MappingProxyType

import chess.pgn


class PgnParseError(ValueError):
    """Raised when PGN cannot be converted into a legal mainline replay."""


@dataclass(frozen=True, slots=True)
class ReplayPly:
    """One half-move and the resulting board state."""

    number: int
    san: str
    uci: str
    fen: str
    clock_seconds: float | None
    is_capture: bool
    is_check: bool
    is_checkmate: bool
    captured_piece: str | None
    is_castling: bool
    promotion_piece: str | None


@dataclass(frozen=True, slots=True)
class ParsedGame:
    """Normalized game metadata and its mainline replay."""

    headers: Mapping[str, str]
    initial_fen: str
    final_fen: str
    result: str
    plies: tuple[ReplayPly, ...]


def parse_pgn(pgn_text: str) -> ParsedGame:
    """Parse one PGN game and validate every move in its mainline."""
    if not pgn_text.strip():
        raise PgnParseError("PGN input is empty")

    try:
        game = chess.pgn.read_game(StringIO(pgn_text))
    except (ValueError, UnicodeError) as error:
        raise PgnParseError(f"Unable to read PGN: {error}") from error

    if game is None:
        raise PgnParseError("PGN does not contain a game")
    if game.errors:
        messages = "; ".join(str(error) for error in game.errors)
        raise PgnParseError(f"PGN contains illegal or malformed moves: {messages}")

    board = game.board()
    initial_fen = board.fen()
    plies: list[ReplayPly] = []

    for number, node in enumerate(game.mainline(), start=1):
        move = node.move
        is_capture = board.is_capture(move)
        captured = board.piece_at(move.to_square)
        if captured is None and board.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not board.turn)
        is_castling = board.is_castling(move)
        san = board.san(move)
        board.push(move)
        plies.append(
            ReplayPly(
                number=number,
                san=san,
                uci=move.uci(),
                fen=board.fen(),
                clock_seconds=node.clock(),
                is_capture=is_capture,
                is_check=board.is_check(),
                is_checkmate=board.is_checkmate(),
                captured_piece=chess.piece_name(captured.piece_type) if captured else None,
                is_castling=is_castling,
                promotion_piece=chess.piece_name(move.promotion) if move.promotion else None,
            )
        )

    headers = MappingProxyType({key: str(value) for key, value in game.headers.items()})
    return ParsedGame(
        headers=headers,
        initial_fen=initial_fen,
        final_fen=board.fen(),
        result=headers.get("Result", "*"),
        plies=tuple(plies),
    )


def parse_pgn_file(path: Path) -> ParsedGame:
    """Read and parse one UTF-8 PGN file."""
    return parse_pgn(path.read_text(encoding="utf-8"))