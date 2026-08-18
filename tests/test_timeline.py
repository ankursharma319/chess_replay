import pytest

from chess_replay.chess.pgn import parse_pgn
from chess_replay.jobs.timeline import TimelineBuilder, parse_time_control


def test_builds_realtime_clock_countdown_and_move_timestamps() -> None:
    game = parse_pgn(
        '[TimeControl "10+2"]\n\n'
        "1. e4 {[%clk 0:00:09]} e5 {[%clk 0:00:08]} *"
    )

    timeline = TimelineBuilder(clock_tick_seconds=1, ending_hold_seconds=2).build(game)

    assert timeline.uses_realtime_clocks
    assert timeline.move_timestamps == {1: 3, 2: 7}
    assert [frame.white_clock for frame in timeline.frames[:3]] == [10, 9, 8]
    assert [frame.duration_seconds for frame in timeline.frames] == [1, 1, 1, 1, 1, 1, 1, 2]
    assert timeline.frames[3].fen == game.plies[0].fen
    assert timeline.duration_seconds == 9


def test_uses_fractional_final_tick_without_rounding_game_time() -> None:
    game = parse_pgn('[TimeControl "10"]\n\n1. e4 {[%clk 0:00:08.6]} *')

    timeline = TimelineBuilder(clock_tick_seconds=1, ending_hold_seconds=1).build(game)

    assert [frame.duration_seconds for frame in timeline.frames] == pytest.approx([1, 0.4, 1])
    assert timeline.move_timestamps[1] == pytest.approx(1.4)


def test_parses_increment_time_control() -> None:
    assert parse_time_control("300+2") == (300, 2)
    assert parse_time_control("1/86400") == (None, 0)