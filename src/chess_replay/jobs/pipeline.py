"""Orchestrate PGN parsing, frame rendering, and video encoding."""

from __future__ import annotations

import json
import shutil
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from chess_replay.analysis.stockfish import PositionEvaluation
from chess_replay.chess.pgn import ParsedGame, parse_pgn_file
from chess_replay.jobs.timeline import TimelineBuilder, align_timestamps_to_frames
from chess_replay.media.commentary import CommentaryGenerator
from chess_replay.media.narration import Narrator, NullNarrator
from chess_replay.media.sound import SoundtrackBuilder
from chess_replay.rendering.pillow_board import PillowBoardRenderer
from chess_replay.rendering.presentation import PlayerPresentation, ReplayPresentation


@dataclass(frozen=True, slots=True)
class RenderResult:
    video_path: Path
    manifest_path: Path
    frame_count: int
    duration_seconds: float


class FrameEncoder(Protocol):
    def encode_frames(
        self,
        frame_directory: Path,
        output_path: Path,
        *,
        seconds_per_position: float,
        frame_rate: int,
        audio_path: Path | None = None,
        frame_durations: tuple[float, ...] | None = None,
    ) -> None: ...


class PositionEvaluator(Protocol):
    def evaluate(self, fen: str) -> PositionEvaluation: ...


class ReplayPipeline:
    def __init__(
        self,
        renderer: PillowBoardRenderer,
        encoder: FrameEncoder,
        *,
        commentary_generator: CommentaryGenerator | None = None,
        narrator: Narrator | None = None,
        soundtrack_builder: SoundtrackBuilder | None = None,
        timeline_builder: TimelineBuilder | None = None,
        evaluator: PositionEvaluator | None = None,
        frame_rate: int = 30,
        seconds_per_position: float = 1.2,
        ending_hold_positions: int = 3,
    ) -> None:
        self.renderer = renderer
        self.encoder = encoder
        self.commentary_generator = commentary_generator or CommentaryGenerator()
        self.narrator = narrator or NullNarrator()
        self.soundtrack_builder = soundtrack_builder or SoundtrackBuilder()
        self.timeline_builder = timeline_builder or TimelineBuilder(
            fallback_move_seconds=seconds_per_position,
            ending_hold_seconds=ending_hold_positions * seconds_per_position,
        )
        self.evaluator = evaluator
        self.frame_rate = frame_rate
        self.seconds_per_position = seconds_per_position
        self.ending_hold_positions = ending_hold_positions

    def render_pgn(
        self,
        pgn_path: Path,
        output_path: Path,
        *,
        keep_frames: bool = False,
        presentation: ReplayPresentation | None = None,
        include_commentary: bool = False,
    ) -> RenderResult:
        game = parse_pgn_file(pgn_path)
        if keep_frames:
            frame_directory = output_path.parent / f"{output_path.stem}-frames"
            if frame_directory.exists():
                shutil.rmtree(frame_directory)
            frame_directory.mkdir(parents=True)
            result = self._render(
                game,
                frame_directory,
                output_path,
                presentation,
                include_commentary,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="chess-replay-") as temporary:
                result = self._render(
                    game,
                    Path(temporary),
                    output_path,
                    presentation,
                    include_commentary,
                )
        return result

    def _render(
        self,
        game: ParsedGame,
        frame_directory: Path,
        output_path: Path,
        presentation: ReplayPresentation | None,
        include_commentary: bool,
    ) -> RenderResult:
        presentation = presentation or _default_presentation(game)
        timeline = self.timeline_builder.build(game)
        move_timestamps = align_timestamps_to_frames(
            timeline.move_timestamps,
            self.frame_rate,
        )
        common = {
            "white": presentation.white,
            "black": presentation.black,
            "event_label": presentation.event_line,
            "bottom_color": presentation.bottom_color,
        }
        evaluations = (
            {
                fen: self.evaluator.evaluate(fen)
                for fen in dict.fromkeys(frame.fen for frame in timeline.frames)
            }
            if self.evaluator is not None
            else {}
        )
        frame_durations: list[float] = []
        previous_evaluation: PositionEvaluation | None = None
        previous_fen: str | None = None
        for frame in timeline.frames:
            evaluation = evaluations.get(frame.fen)
            animate = previous_fen is not None and frame.fen != previous_fen
            animation = _evaluation_animation(
                frame.duration_seconds,
                previous_evaluation if animate else None,
                evaluation,
                self.frame_rate,
            )
            for duration, fraction in animation:
                frame_number = len(frame_durations)
                self.renderer.render(
                    fen=frame.fen,
                    output_path=frame_directory / f"frame-{frame_number:05d}.png",
                    white_clock=frame.white_clock,
                    black_clock=frame.black_clock,
                    move_label=frame.move_label,
                    last_move_uci=frame.last_move_uci,
                    evaluation=evaluation,
                    evaluation_fraction=fraction,
                    **common,
                )
                frame_durations.append(duration)
            previous_evaluation = evaluation
            previous_fen = frame.fen

        commentary_cues = (
            self.commentary_generator.generate(game, presentation) if include_commentary else ()
        )
        narration_clips = self.narrator.synthesize(
            commentary_cues,
            frame_directory / "narration",
            cue_timestamps=move_timestamps,
        )
        narration_end = max(
            (
                clip.offset_seconds + _wav_duration(clip.path) + 0.3
                for clip in narration_clips
            ),
            default=0.0,
        )
        duration_seconds = timeline.duration_seconds
        final_frame = frame_directory / f"frame-{len(frame_durations) - 1:05d}.png"
        while duration_seconds < narration_end:
            duration = min(1.0, narration_end - duration_seconds)
            frame_number = len(frame_durations)
            shutil.copyfile(
                final_frame,
                frame_directory / f"frame-{frame_number:05d}.png",
            )
            frame_durations.append(duration)
            duration_seconds += duration
        duration_seconds = round(duration_seconds, 3)
        frame_count = len(frame_durations)
        soundtrack_path = frame_directory / "soundtrack.wav"
        sound_counts = self.soundtrack_builder.build(
            game.plies,
            soundtrack_path,
            move_timestamps=move_timestamps,
            total_duration_seconds=duration_seconds,
            narration_clips=narration_clips,
        )
        self.encoder.encode_frames(
            frame_directory,
            output_path,
            seconds_per_position=self.seconds_per_position,
            frame_rate=self.frame_rate,
            audio_path=soundtrack_path,
            frame_durations=tuple(frame_durations),
        )
        manifest_path = output_path.with_suffix(".json")
        result = RenderResult(
            video_path=output_path,
            manifest_path=manifest_path,
            frame_count=frame_count,
            duration_seconds=duration_seconds,
        )
        manifest = {
            **asdict(result),
            "video_path": str(result.video_path),
            "manifest_path": str(result.manifest_path),
            "source_pgn_headers": dict(game.headers),
            "frame_rate": self.frame_rate,
            "seconds_per_position": self.seconds_per_position,
            "clock_tick_seconds": self.timeline_builder.clock_tick_seconds,
            "uses_realtime_clocks": timeline.uses_realtime_clocks,
            "move_timestamps": dict(move_timestamps),
            "sound_events": {kind.value: count for kind, count in sound_counts.items()},
            "presentation": _presentation_manifest(presentation),
            "commentary": [cue.text for cue in commentary_cues],
            "commentary_cues": [
                {
                    "ply_number": cue.ply_number,
                    "kind": cue.kind,
                    "clip_key": cue.clip_key,
                    "text": cue.text,
                }
                for cue in commentary_cues
            ],
            "narration_clips": [
                {
                    "offset_seconds": clip.offset_seconds,
                    "file": clip.path.name,
                }
                for clip in narration_clips
            ],
            "narrator": type(self.narrator).__name__,
            "evaluation_enabled": self.evaluator is not None,
            "evaluated_positions": len(evaluations),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return result


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def _evaluation_animation(
    duration_seconds: float,
    previous: PositionEvaluation | None,
    current: PositionEvaluation | None,
    frame_rate: int,
    animation_seconds: float = 0.4,
) -> tuple[tuple[float, float | None], ...]:
    if previous is None or current is None or previous == current:
        return ((duration_seconds, current.white_fraction if current else None),)

    animation_duration = min(duration_seconds, animation_seconds)
    step_count = max(1, round(animation_duration * frame_rate))
    step_duration = animation_duration / step_count
    start = previous.white_fraction
    end = current.white_fraction
    steps: list[tuple[float, float | None]] = []
    for index in range(step_count):
        progress = (index + 1) / step_count
        eased = progress * progress * (3 - 2 * progress)
        steps.append((step_duration, start + (end - start) * eased))
    remainder = duration_seconds - animation_duration
    if remainder > 1e-9:
        steps.append((remainder, end))
    return tuple(steps)


def _default_presentation(game: ParsedGame) -> ReplayPresentation:
    return ReplayPresentation(
        white=PlayerPresentation(
            username=game.headers.get("White", "White"),
            rating=game.headers.get("WhiteElo", ""),
        ),
        black=PlayerPresentation(
            username=game.headers.get("Black", "Black"),
            rating=game.headers.get("BlackElo", ""),
        ),
    )


def _presentation_manifest(presentation: ReplayPresentation) -> dict[str, object]:
    def player(value: PlayerPresentation) -> dict[str, object]:
        return {
            "username": value.username,
            "name": value.name,
            "title": value.title,
            "rating": value.rating,
            "avatar_path": str(value.avatar_path) if value.avatar_path else None,
            "country_code": value.country_code,
            "flag_path": str(value.flag_path) if value.flag_path else None,
            "score_before": value.score_before,
            "game_number": value.game_number,
            "standing_label": value.standing_label,
        }

    return {
        "white": player(presentation.white),
        "black": player(presentation.black),
        "tournament_name": presentation.tournament_name,
        "round_number": presentation.round_number,
        "total_rounds": presentation.total_rounds,
        "game_format": presentation.game_format,
        "bottom_color": "white" if presentation.bottom_color else "black",
    }