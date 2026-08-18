"""Configurable local narration for Windows, Linux, and user-supplied clip packs."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Mapping, Sequence
from pathlib import Path
from shutil import which
from typing import Protocol

from chess_replay.media.commentary import CommentaryCue
from chess_replay.media.sound import NarrationClip


class NarrationUnavailable(RuntimeError):
    """Raised when the configured local narrator cannot synthesize speech."""


class Narrator(Protocol):
    def synthesize(
        self,
        cues: tuple[CommentaryCue, ...],
        output_directory: Path,
        *,
        cue_timestamps: Mapping[int, float],
    ) -> tuple[NarrationClip, ...]: ...


class NullNarrator:
    def synthesize(
        self,
        cues: tuple[CommentaryCue, ...],
        output_directory: Path,
        *,
        cue_timestamps: Mapping[int, float],
    ) -> tuple[NarrationClip, ...]:
        return ()


class WindowsSapiNarrator:
    """Synthesize commentary with the default generic Windows system voice."""

    def __init__(self, powershell_executable: str = "powershell", rate: int = 1) -> None:
        self.powershell_executable = powershell_executable
        self.rate = rate

    def synthesize(
        self,
        cues: tuple[CommentaryCue, ...],
        output_directory: Path,
        *,
        cue_timestamps: Mapping[int, float],
    ) -> tuple[NarrationClip, ...]:
        if not cues:
            return ()
        if which(self.powershell_executable) is None:
            raise NarrationUnavailable("Windows PowerShell is required for SAPI narration")

        output_directory.mkdir(parents=True, exist_ok=True)
        entries = [
            {
                "path": str((output_directory / f"cue-{index:03d}.wav").resolve()),
                "text": cue.text,
            }
            for index, cue in enumerate(cues)
        ]
        with tempfile.TemporaryDirectory(prefix="chess-replay-sapi-") as temporary:
            temporary_path = Path(temporary)
            payload_path = temporary_path / "cues.json"
            script_path = temporary_path / "synthesize.ps1"
            payload_path.write_text(json.dumps(entries), encoding="utf-8")
            script_path.write_text(_SAPI_SCRIPT, encoding="utf-8")
            try:
                subprocess.run(
                    [
                        self.powershell_executable,
                        "-NoProfile",
                        "-NonInteractive",
                        "-File",
                        str(script_path),
                        str(payload_path),
                        str(self.rate),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except (FileNotFoundError, subprocess.CalledProcessError) as error:
                message = getattr(error, "stderr", "") or str(error)
                raise NarrationUnavailable(
                    f"Windows narration failed: {message.strip()}"
                ) from error
        return _schedule(cues, [Path(entry["path"]) for entry in entries], cue_timestamps)


class EspeakNarrator:
    """Synthesize generic Linux narration with espeak-ng."""

    def __init__(
        self,
        executable: str = "espeak-ng",
        *,
        rate: int = 165,
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        self.executable = executable
        self.rate = rate
        self.ffmpeg_executable = ffmpeg_executable

    def synthesize(
        self,
        cues: tuple[CommentaryCue, ...],
        output_directory: Path,
        *,
        cue_timestamps: Mapping[int, float],
    ) -> tuple[NarrationClip, ...]:
        if not cues:
            return ()
        if which(self.executable) is None:
            raise NarrationUnavailable(f"Linux narration requires {self.executable}")
        output_directory.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for index, cue in enumerate(cues):
            raw_path = output_directory / f"cue-{index:03d}-raw.wav"
            output_path = output_directory / f"cue-{index:03d}.wav"
            _run(
                [self.executable, "-s", str(self.rate), "-w", str(raw_path), cue.text],
                "espeak-ng narration",
            )
            _normalize_audio(raw_path, output_path, self.ffmpeg_executable)
            raw_path.unlink(missing_ok=True)
            paths.append(output_path)
        return _schedule(cues, paths, cue_timestamps)


class LocalClipPackNarrator:
    """Use a local, user-supplied and licensed commentary clip pack."""

    def __init__(
        self,
        directory: Path,
        *,
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        self.directory = directory
        self.ffmpeg_executable = ffmpeg_executable
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise NarrationUnavailable(f"Voice pack manifest is missing: {manifest_path}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise NarrationUnavailable("Voice pack manifest must be a JSON object")
        self.clips = {str(kind): _clip_names(value) for kind, value in payload.items()}

    def synthesize(
        self,
        cues: tuple[CommentaryCue, ...],
        output_directory: Path,
        *,
        cue_timestamps: Mapping[int, float],
    ) -> tuple[NarrationClip, ...]:
        output_directory.mkdir(parents=True, exist_ok=True)
        selected_cues: list[CommentaryCue] = []
        paths: list[Path] = []
        for cue in cues:
            candidates = self.clips.get(cue.kind) or self.clips.get("default") or ()
            if not candidates:
                continue
            source = self.directory / candidates[cue.ply_number % len(candidates)]
            if not source.is_file():
                raise NarrationUnavailable(f"Voice clip is missing: {source}")
            output = output_directory / f"cue-{len(paths):03d}.wav"
            _prepare_clip(source, output, self.ffmpeg_executable)
            selected_cues.append(cue)
            paths.append(output)
        return _schedule(tuple(selected_cues), paths, cue_timestamps)


def create_narrator(
    mode: str,
    *,
    ffmpeg_executable: str = "ffmpeg",
    espeak_executable: str = "espeak-ng",
    voice_pack_directory: Path | None = None,
) -> Narrator:
    normalized = mode.strip().lower()
    if normalized == "off":
        return NullNarrator()
    if normalized == "auto":
        normalized = "windows-sapi" if platform.system() == "Windows" else "espeak"
    if normalized == "windows-sapi":
        return WindowsSapiNarrator()
    if normalized == "espeak":
        return EspeakNarrator(espeak_executable, ffmpeg_executable=ffmpeg_executable)
    if normalized == "dmitri":
        if voice_pack_directory is None:
            raise NarrationUnavailable("Dmitri mode requires a local voice pack directory")
        return LocalClipPackNarrator(
            voice_pack_directory,
            ffmpeg_executable=ffmpeg_executable,
        )
    raise ValueError(f"Unknown narrator mode: {mode}")


def _schedule(
    cues: Sequence[CommentaryCue],
    paths: Sequence[Path],
    cue_timestamps: Mapping[int, float],
) -> tuple[NarrationClip, ...]:
    clips: list[NarrationClip] = []
    next_available = 0.0
    for cue, path in zip(cues, paths, strict=True):
        if not path.is_file() or path.stat().st_size <= 46:
            raise NarrationUnavailable(f"Narration did not produce audio for: {cue.text}")
        desired_offset = 0.0 if cue.ply_number == 0 else cue_timestamps[cue.ply_number]
        offset = max(desired_offset, next_available)
        with wave.open(str(path), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        clips.append(NarrationClip(offset_seconds=offset, path=path))
        next_available = offset + duration + 0.15
    return tuple(clips)


def _prepare_clip(source: Path, output: Path, ffmpeg_executable: str) -> None:
    try:
        with wave.open(str(source), "rb") as audio:
            compatible = (
                audio.getnchannels() == 1
                and audio.getsampwidth() == 2
                and audio.getframerate() == 44_100
            )
    except (wave.Error, EOFError):
        compatible = False
    if compatible:
        shutil.copyfile(source, output)
    else:
        _normalize_audio(source, output, ffmpeg_executable)


def _normalize_audio(source: Path, output: Path, ffmpeg_executable: str) -> None:
    _run(
        [
            ffmpeg_executable,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        "audio normalization",
    )


def _run(command: list[str], operation: str) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        message = getattr(error, "stderr", "") or str(error)
        raise NarrationUnavailable(f"{operation} failed: {message.strip()}") from error


def _clip_names(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise NarrationUnavailable("Voice pack entries must be a filename or list of filenames")


_SAPI_SCRIPT = r"""
param([string]$PayloadPath, [int]$Rate)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$entries = Get-Content -LiteralPath $PayloadPath -Raw | ConvertFrom-Json
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$synth.Rate = $Rate
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
    44100,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)
try {
    foreach ($entry in $entries) {
        $synth.SetOutputToWaveFile([string]$entry.path, $format)
        $synth.Speak([string]$entry.text)
    }
} finally {
    $synth.Dispose()
}
"""