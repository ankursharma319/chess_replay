from pathlib import Path

import pytest

from chess_replay.chess.pgn import (
    PgnParseError,
    parse_pgn,
    parse_pgn_file,
)

SAMPLE_PGN = (
    Path(__file__).parents[1] / "samples" / "titled-tuesday-2026-08-11-round-9.pgn"
)


def test_parses_titled_tuesday_game_with_clocks() -> None:
    game = parse_pgn_file(SAMPLE_PGN)

    assert game.headers["Tournament"].endswith(
        "titled-tuesday-blitz-august-11-2026-6657019"
    )
    assert game.headers["White"] == "artin10862"
    assert game.headers["Black"] == "LeRoidesChampions"
    assert game.result == "1-0"
    assert len(game.plies) == 39
    assert game.plies[0].san == "e4"
    assert game.plies[0].clock_seconds == pytest.approx(298.8)
    assert game.plies[-1].san == "Rad1"
    assert game.plies[-1].clock_seconds == pytest.approx(205.7)
    assert game.final_fen == game.headers["CurrentPosition"]


def test_rejects_empty_pgn() -> None:
    with pytest.raises(PgnParseError, match="empty"):
        parse_pgn("  ")


def test_classifies_capture_check_and_checkmate() -> None:
    capture = parse_pgn("1. e4 d5 2. exd5 *")
    checkmate = parse_pgn("1. f3 e5 2. g4 Qh4# 0-1")

    assert capture.plies[-1].is_capture
    assert not capture.plies[-1].is_check
    assert checkmate.plies[-1].is_check
    assert checkmate.plies[-1].is_checkmate
    assert not checkmate.plies[-1].is_capture