"""Build a real-time replay timeline from PGN clock annotations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from chess_replay.chess.pgn import ParsedGame


@dataclass(frozen=True, slots=True)
class TimelineFrame:
    fen: str
    duration_seconds: float
    white_clock: float | None
    black_clock: float | None
    move_label: str
    last_move_uci: str | None


@dataclass(frozen=True, slots=True)
class ReplayTimeline:
    frames: tuple[TimelineFrame, ...]
    move_timestamps: Mapping[int, float]
    duration_seconds: float
    uses_realtime_clocks: bool


class TimelineBuilder:
    def __init__(
        self,
        *,
        clock_tick_seconds: float = 1.0,
        fallback_move_seconds: float = 1.2,
        ending_hold_seconds: float = 3.6,
    ) -> None:
        if clock_tick_seconds <= 0:
            raise ValueError("clock_tick_seconds must be positive")
        if fallback_move_seconds <= 0:
            raise ValueError("fallback_move_seconds must be positive")
        if ending_hold_seconds <= 0:
            raise ValueError("ending_hold_seconds must be positive")
        self.clock_tick_seconds = clock_tick_seconds
        self.fallback_move_seconds = fallback_move_seconds
        self.ending_hold_seconds = ending_hold_seconds

    def build(self, game: ParsedGame) -> ReplayTimeline:
        base_clock, increment = parse_time_control(game.headers.get("TimeControl", ""))
        white_clock = base_clock
        black_clock = base_clock
        current_fen = game.initial_fen
        current_label = "Start"
        current_last_move: str | None = None
        frames: list[TimelineFrame] = []
        move_timestamps: dict[int, float] = {}
        timestamp = 0.0
        realtime_plies = 0

        for ply in game.plies:
            is_white = ply.number % 2 == 1
            clock_before = white_clock if is_white else black_clock
            think_seconds = self.fallback_move_seconds
            if clock_before is not None and ply.clock_seconds is not None:
                think_seconds = max(0.0, clock_before + increment - ply.clock_seconds)
                realtime_plies += 1

            elapsed = 0.0
            while elapsed < think_seconds - 1e-9:
                duration = min(self.clock_tick_seconds, think_seconds - elapsed)
                active_clock = (
                    max(0.0, clock_before - elapsed) if clock_before is not None else None
                )
                frames.append(
                    TimelineFrame(
                        fen=current_fen,
                        duration_seconds=duration,
                        white_clock=active_clock if is_white else white_clock,
                        black_clock=black_clock if is_white else active_clock,
                        move_label=current_label,
                        last_move_uci=current_last_move,
                    )
                )
                elapsed += duration

            timestamp += think_seconds
            move_timestamps[ply.number] = round(timestamp, 6)
            if is_white:
                white_clock = ply.clock_seconds
            else:
                black_clock = ply.clock_seconds
            current_fen = ply.fen
            current_label = _move_label(ply.number, ply.san)
            current_last_move = ply.uci

        frames.append(
            TimelineFrame(
                fen=current_fen,
                duration_seconds=self.ending_hold_seconds,
                white_clock=white_clock,
                black_clock=black_clock,
                move_label=current_label,
                last_move_uci=current_last_move,
            )
        )
        timestamp += self.ending_hold_seconds
        return ReplayTimeline(
            frames=tuple(frames),
            move_timestamps=MappingProxyType(move_timestamps),
            duration_seconds=round(timestamp, 6),
            uses_realtime_clocks=realtime_plies == len(game.plies),
        )


def parse_time_control(time_control: str) -> tuple[float | None, float]:
    if not time_control or "/" in time_control:
        return None, 0.0
    base, separator, increment = time_control.partition("+")
    try:
        base_seconds = float(base)
        increment_seconds = float(increment) if separator else 0.0
    except ValueError:
        return None, 0.0
    return base_seconds, increment_seconds


def _move_label(ply_number: int, san: str) -> str:
    move_number = (ply_number + 1) // 2
    prefix = f"{move_number}." if ply_number % 2 == 1 else f"{move_number}..."
    return f"{prefix} {san}"