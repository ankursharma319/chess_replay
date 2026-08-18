import chess
from PIL import Image

from chess_replay.analysis.stockfish import PositionEvaluation
from chess_replay.chess.pgn import parse_pgn
from chess_replay.rendering.pillow_board import (
    PillowBoardRenderer,
    _piece_symbol,
    _screen_square,
)
from chess_replay.rendering.presentation import PlayerPresentation


def test_renders_replay_frame(tmp_path) -> None:
    game = parse_pgn('[White "A"]\n[Black "B"]\n\n1. e4 {[%clk 0:04:58]} *')
    frame = tmp_path / "frame.png"

    PillowBoardRenderer(960, 540).render(
        fen=game.plies[0].fen,
        output_path=frame,
        white=PlayerPresentation(username="A"),
        black=PlayerPresentation(username="B"),
        white_clock=game.plies[0].clock_seconds,
        black_clock=300,
        move_label="1. e4",
        last_move_uci=game.plies[0].uci,
    )

    with Image.open(frame) as image:
        assert image.size == (960, 540)
        assert image.format == "PNG"


def test_uses_standard_chess_piece_glyphs() -> None:
    assert _piece_symbol(chess.Piece(chess.QUEEN, chess.WHITE)) == "♕"
    assert _piece_symbol(chess.Piece(chess.KNIGHT, chess.BLACK)) == "♞"


def test_flips_board_for_black_and_renders_evaluation_bar(tmp_path) -> None:
    frame = tmp_path / "black-bottom.png"

    PillowBoardRenderer(960, 540).render(
        fen=chess.STARTING_FEN,
        output_path=frame,
        white=PlayerPresentation(username="White"),
        black=PlayerPresentation(username="Black"),
        bottom_color=chess.BLACK,
        evaluation=PositionEvaluation(125),
    )

    assert _screen_square(7, 0, chess.WHITE) == chess.A1
    assert _screen_square(7, 0, chess.BLACK) == chess.H8
    with Image.open(frame) as image:
        assert image.size == (960, 540)
        assert image.getbbox() is not None