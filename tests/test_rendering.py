import chess
from PIL import Image

from chess_replay.analysis.stockfish import PositionEvaluation
from chess_replay.chess.pgn import parse_pgn
from chess_replay.rendering.pieces import piece_sprite
from chess_replay.rendering.pillow_board import (
    PillowBoardRenderer,
    _format_clock,
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


def test_uses_standard_chess_piece_sprites_and_whole_second_clocks() -> None:
    sprite = piece_sprite("N", 96)

    assert sprite.size == (96, 96)
    assert sprite.mode == "RGBA"
    assert sprite.getchannel("A").getextrema() == (0, 255)
    assert any(
        alpha not in {0, 255}
        for alpha in sprite.getchannel("A").get_flattened_data()
    )
    assert _format_clock(59.01) == "01:00"
    assert _format_clock(59.0) == "00:59"


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