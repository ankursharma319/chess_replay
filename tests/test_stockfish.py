import chess
import chess.engine
import pytest

from chess_replay.analysis.stockfish import PositionEvaluation, StockfishEvaluator


class FakeEngine:
    def __init__(self) -> None:
        self.analyse_calls = 0
        self.configured = None
        self.closed = False

    def configure(self, options) -> None:
        self.configured = options

    def analyse(self, board, limit):
        self.analyse_calls += 1
        return {"score": chess.engine.PovScore(chess.engine.Cp(80), chess.WHITE)}

    def quit(self) -> None:
        self.closed = True


def test_caches_stockfish_evaluation(monkeypatch) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda _: engine)

    evaluator = StockfishEvaluator(
        "stockfish",
        time_seconds=0.01,
        depth=12,
        hash_mb=32,
        threads=1,
    )
    first = evaluator.evaluate(chess.STARTING_FEN)
    second = evaluator.evaluate(chess.STARTING_FEN)
    evaluator.close()

    assert first == PositionEvaluation(80)
    assert second == first
    assert engine.analyse_calls == 1
    assert engine.configured == {"Hash": 32, "Threads": 1}
    assert engine.closed


def test_evaluation_fraction_and_labels() -> None:
    assert PositionEvaluation(0).white_fraction == pytest.approx(0.5)
    assert PositionEvaluation(100_000, mate_in=0).white_fraction == 1
    assert PositionEvaluation(-100_000, mate_in=0).white_fraction == 0
    assert PositionEvaluation(0, mate_in=3).label == "+M3"