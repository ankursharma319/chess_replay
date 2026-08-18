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
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            ]
        )
        if frame_durations is None:
            command.extend(["-r", str(frame_rate)])
        else:
            command.extend(["-vf", f"fps={frame_rate}:round=up"])
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

    def encode_still(
        self,
        image_path: Path,
        output_path: Path,
        *,
        duration_seconds: float,
        frame_rate: int,
    ) -> None:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=44100",
            "-t",
            f"{duration_seconds:.3f}",
            "-c:v",
            "libx264",
            "-r",
            str(frame_rate),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ]
        self._run(command, "transition encoding")

    def concatenate(self, segments: Sequence[Path], output_path: Path) -> None:
        if not segments:
            raise ValueError("At least one segment is required")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "-y",
            "-loglevel",
            "error",
        ]
        for segment in segments:
            command.extend(["-i", str(segment)])
        filter_parts: list[str] = []
        concat_inputs: list[str] = []
        for index in range(len(segments)):
            filter_parts.extend(
                [
                    f"[{index}:v:0]setpts=PTS-STARTPTS[v{index}]",
                    f"[{index}:a:0]asetpts=PTS-STARTPTS[a{index}]",
                ]
            )
            concat_inputs.extend([f"[v{index}]", f"[a{index}]"])
        filter_parts.append(
            "".join(concat_inputs)
            + f"concat=n={len(segments)}:v=1:a=1[outv][outa]"
        )
        command.extend(
            [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
            ]
        )
        self._run(command, "video concatenation")

    @staticmethod
    def _run(command: list[str], operation: str) -> None:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as error:
            raise FFmpegError("FFmpeg is unavailable") from error
        except subprocess.CalledProcessError as error:
            message = error.stderr.strip() or "unknown FFmpeg error"
            raise FFmpegError(f"{operation} failed: {message}") from error

    @staticmethod
    def _write_concat_manifest(
        frame_directory: Path,
        frame_durations: Sequence[float],
        manifest_path: Path,
    ) -> None:
        if not frame_durations:
            raise FFmpegError("At least one frame duration is required")
        lines = ["ffconcat version 1.0"]
        for index, duration in enumerate(frame_durations):
            if duration <= 0:
                raise FFmpegError("Frame durations must be positive")
            lines.extend(
                [
                    f"file 'frame-{index:05d}.png'",
                    "option framerate 1000",
                    f"duration {duration:.9f}",
                ]
            )
        # A concat duration takes effect only when the following file starts.
        lines.extend(
            [
                f"file 'frame-{len(frame_durations) - 1:05d}.png'",
                "option framerate 1000",
            ]
        )
        manifest_path.write_text("\n".join(lines) + "\n", encoding="ascii")
