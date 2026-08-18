"""Generate an original deterministic soundtrack for replay move events."""

from __future__ import annotations

import math
import wave
from array import array
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from chess_replay.chess.pgn import ReplayPly


class SoundKind(StrEnum):
    MOVE = "move"
    CAPTURE = "capture"
    CHECKMATE = "checkmate"


@dataclass(frozen=True, slots=True)
class NarrationClip:
    offset_seconds: float
    path: Path


class SoundtrackBuilder:
    """Synthesize event cues into a mono 16-bit PCM WAV file."""

    def __init__(self, sample_rate: int = 44_100) -> None:
        self.sample_rate = sample_rate

    def build(
        self,
        plies: Sequence[ReplayPly],
        output_path: Path,
        *,
        move_timestamps: Mapping[int, float],
        total_duration_seconds: float,
        narration_clips: Sequence[NarrationClip] = (),
    ) -> Counter[SoundKind]:
        sample_count = math.ceil(total_duration_seconds * self.sample_rate)
        mixed = array("f", [0.0]) * sample_count
        counts: Counter[SoundKind] = Counter()

        for ply in plies:
            kind = sound_kind(ply)
            counts[kind] += 1
            cue = self._cue(kind)
            offset = round(move_timestamps[ply.number] * self.sample_rate)
            for index, value in enumerate(cue):
                target = offset + index
                if target >= sample_count:
                    break
                mixed[target] += value

        for clip in narration_clips:
            self._mix_narration(mixed, clip)

        peak = max((abs(value) for value in mixed), default=1.0)
        scale = 0.88 / max(peak, 1.0)
        pcm = array("h", (round(max(-1.0, min(1.0, value * scale)) * 32767) for value in mixed))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(self.sample_rate)
            output.writeframes(pcm.tobytes())
        return counts

    def _mix_narration(self, mixed: array[float], clip: NarrationClip) -> None:
        with wave.open(str(clip.path), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getframerate() != self.sample_rate
            ):
                raise ValueError("Narration must be 44.1 kHz mono 16-bit PCM")
            samples = array("h")
            samples.frombytes(source.readframes(source.getnframes()))
        offset = round(clip.offset_seconds * self.sample_rate)
        for index, value in enumerate(samples):
            target = offset + index
            if target >= len(mixed):
                break
            mixed[target] += (value / 32768) * 0.72

    def _cue(self, kind: SoundKind) -> array[float]:
        if kind is SoundKind.CAPTURE:
            return self._capture_cue()
        if kind is SoundKind.CHECKMATE:
            return self._checkmate_cue()
        return self._move_cue()

    def _move_cue(self) -> array[float]:
        duration = 0.09
        return self._samples(
            duration,
            lambda time: self._wood_hit(time, resonance_hz=860, brightness=1.0),
        )

    def _capture_cue(self) -> array[float]:
        duration = 0.18

        def signal(time: float) -> float:
            first = self._wood_hit(time, resonance_hz=330, brightness=0.9)
            delayed = time - 0.042
            second = (
                0.58 * self._wood_hit(delayed, resonance_hz=610, brightness=0.7)
                if delayed >= 0
                else 0.0
            )
            return first + second

        return self._samples(duration, signal)

    def _checkmate_cue(self) -> array[float]:
        duration = 0.95

        def signal(time: float) -> float:
            impact = self._wood_hit(time, resonance_hz=470, brightness=0.8)
            attack = min(1.0, time / 0.012)
            release = math.exp(-2.8 * time)
            chord = sum(
                math.sin(2 * math.pi * frequency * time)
                for frequency in (261.63, 329.63, 392.0, 523.25)
            )
            return impact + 0.16 * attack * release * chord

        return self._samples(duration, signal)

    def _wood_hit(self, time: float, *, resonance_hz: float, brightness: float) -> float:
        sample_index = round(time * self.sample_rate)
        if sample_index == 0:
            return 1.0
        noise = _deterministic_noise(sample_index)
        transient = 0.72 * brightness * math.exp(-520 * time) * noise
        body = 0.48 * math.exp(-48 * time) * math.cos(2 * math.pi * resonance_hz * time)
        overtone = 0.18 * math.exp(-75 * time) * math.cos(
            2 * math.pi * resonance_hz * 1.91 * time
        )
        return transient + body + overtone

    def _samples(self, duration: float, signal: Callable[[float], float]) -> array[float]:
        sample_count = round(duration * self.sample_rate)
        return array(
            "f",
            (signal(index / self.sample_rate) for index in range(sample_count)),
        )


def sound_kind(ply: ReplayPly) -> SoundKind:
    if ply.is_checkmate:
        return SoundKind.CHECKMATE
    if ply.is_capture:
        return SoundKind.CAPTURE
    return SoundKind.MOVE


def _deterministic_noise(sample_index: int) -> float:
    value = (sample_index * 1_103_515_245 + 12_345) & 0x7FFFFFFF
    return (value / 0x3FFFFFFF) - 1.0