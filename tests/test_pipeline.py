import pytest

from chess_replay.analysis.stockfish import PositionEvaluation
from chess_replay.jobs.pipeline import _evaluation_animation


def test_animates_evaluation_without_changing_frame_duration() -> None:
    steps = _evaluation_animation(
        1.0,
        PositionEvaluation(-300),
        PositionEvaluation(300),
        frame_rate=30,
    )

    fractions = [fraction for _, fraction in steps]
    assert sum(duration for duration, _ in steps) == pytest.approx(1.0)
    assert len(steps) == 13
    assert fractions == sorted(fractions)
    assert fractions[-1] == PositionEvaluation(300).white_fraction