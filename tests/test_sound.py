import wave
from array import array

from chess_replay.chess.pgn import parse_pgn
from chess_replay.media.sound import SoundKind, SoundtrackBuilder, sound_kind


def test_uses_distinct_capture_and_checkmate_sounds(tmp_path) -> None:
    game = parse_pgn("1. f3 e5 2. g4 Qh4# 0-1")
    output = tmp_path / "soundtrack.wav"

    counts = SoundtrackBuilder(sample_rate=8_000).build(
        game.plies,
        output,
        move_timestamps={ply.number: ply.number * 0.25 for ply in game.plies},
        total_duration_seconds=2,
    )

    assert counts[SoundKind.MOVE] == 3
    assert counts[SoundKind.CHECKMATE] == 1
    assert sound_kind(game.plies[-1]) is SoundKind.CHECKMATE
    with wave.open(str(output), "rb") as soundtrack:
        assert soundtrack.getframerate() == 8_000
        assert soundtrack.getnchannels() == 1
        assert soundtrack.getnframes() == 16_000


def test_capture_takes_precedence_over_normal_move() -> None:
    game = parse_pgn("1. e4 d5 2. exd5 *")

    assert sound_kind(game.plies[-1]) is SoundKind.CAPTURE


def test_move_sound_has_an_immediate_attack_at_requested_sample(tmp_path) -> None:
    game = parse_pgn("1. e4 *")
    output = tmp_path / "soundtrack.wav"
    SoundtrackBuilder(sample_rate=8_000).build(
        game.plies,
        output,
        move_timestamps={1: 0.25},
        total_duration_seconds=1,
    )

    with wave.open(str(output), "rb") as soundtrack:
        samples = array("h")
        samples.frombytes(soundtrack.readframes(soundtrack.getnframes()))

    onset = 2_000
    assert all(sample == 0 for sample in samples[:onset])
    assert abs(samples[onset]) > 5_000