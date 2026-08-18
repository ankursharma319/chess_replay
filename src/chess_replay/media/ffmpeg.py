"""FFmpeg subprocess integration."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path


class FFmpegError(RuntimeError):
    """Raised when FFmpeg is missing or encoding fails."""


class FFmpegEncoder:
    def __init__(self, executable: str = "ffmpeg") -> None:
        self.executable = executable

    def version(self) -> str:
        try:
            result = subprocess.run(
                [self.executable, "-version"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise FFmpegError(f"FFmpeg is unavailable at {self.executable!r}") from error
        return result.stdout.splitlines()[0]

    def encode_frames(
        self,
        frame_directory: Path,
        output_path: Path,
        *,
        seconds_per_position: float,
        frame_rate: int,
        audio_path: Path | None = None,
        frame_durations: Sequence[float] | None = None,
    ) -> None:
        if not (frame_directory / "frame-00000.png").is_file():
            raise FFmpegError(f"No replay frames found in {frame_directory}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "-y",
            "-loglevel",
            "error",
        ]
        if frame_durations is None:
            input_rate = 1 / seconds_per_position
            command.extend(
                [
                    "-framerate",
                    f"{input_rate:.8f}",
                    "-i",
                    str(frame_directory / "frame-%05d.png"),
                ]
            )
        else:
            manifest_path = frame_directory / "frames.txt"
            self._write_concat_manifest(frame_directory, frame_durations, manifest_path)
            command.extend(["-f", "concat", "-safe", "0", "-i", str(manifest_path)])
        if audio_path is not None:
            if not audio_path.is_file():
                raise FFmpegError(f"Audio track does not exist: {audio_path}")
            command.extend(["-i", str(audio_path)])
        command.extend(
            [
            "-c:v",
            "libx264",
            "-r",
            str(frame_rate),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            ]
        )
        if audio_path is not None:
            command.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        command.append(str(output_path))
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as error:
            raise FFmpegError(f"FFmpeg is unavailable at {self.executable!r}") from error
        except subprocess.CalledProcessError as error:
            message = error.stderr.strip() or "unknown FFmpeg error"
            raise FFmpegError(f"FFmpeg failed: {message}") from error

    @staticmethod
    def _write_concat_manifest(
        frame_directory: Path,
        frame_durations: Sequence[float],
        manifest_path: Path,
    ) -> None:
        if not frame_durations:
            raise FFmpegError("At least one frame duration is required")
        lines: list[str] = []
        for index, duration in enumerate(frame_durations):
            if duration <= 0:
                raise FFmpegError("Frame durations must be positive")
            lines.extend([f"file 'frame-{index:05d}.png'", f"duration {duration:.6f}"])
        lines.append(f"file 'frame-{len(frame_durations) - 1:05d}.png'")
        manifest_path.write_text("\n".join(lines) + "\n", encoding="ascii")