import json
import wave
from pathlib import Path

from chess_replay.media.commentary import CommentaryCue
from chess_replay.media.narration import (
    LocalClipPackNarrator,
    NullNarrator,
    create_narrator,
)


def test_off_narrator_returns_no_clips(tmp_path: Path) -> None:
    narrator = NullNarrator()

    assert narrator.synthesize((), tmp_path, cue_timestamps={}) == ()
    assert isinstance(create_narrator("off"), NullNarrator)


def test_local_dmitri_pack_uses_user_supplied_manifest(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    clip = pack / "capture.wav"
    _silence(clip)
    (pack / "manifest.json").write_text(
        json.dumps({"capture": ["capture.wav"]}),
        encoding="utf-8",
    )
    narrator = LocalClipPackNarrator(pack)
    cue = CommentaryCue(2, "A capture.", "capture")

    clips = narrator.synthesize((cue,), tmp_path / "out", cue_timestamps={2: 4.5})

    assert len(clips) == 1
    assert clips[0].offset_seconds == 4.5
    assert clips[0].path.is_file()


def test_local_pack_prefers_native_move_and_capture_fallback(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    native = pack / "native"
    native.mkdir(parents=True)
    _silence(native / "e4.wav")
    _silence(native / "xd5.wav")
    (pack / "manifest.json").write_text(json.dumps({"default": []}), encoding="utf-8")
    (pack / "native-index.json").write_text(
        json.dumps({"e4": ["native/e4.wav"], "xd5": ["native/xd5.wav"]}),
        encoding="utf-8",
    )
    narrator = LocalClipPackNarrator(pack)
    cues = (
        CommentaryCue(1, "e4", "move", "e4"),
        CommentaryCue(3, "exd5", "move", "exd5"),
    )

    clips = narrator.synthesize(cues, tmp_path / "out", cue_timestamps={1: 1, 3: 3})

    assert len(clips) == 2


def _silence(path: Path, frames: int = 4_410) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(44_100)
        output.writeframes(b"\0\0" * frames)