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


def _silence(path: Path, frames: int = 4_410) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(44_100)
        output.writeframes(b"\0\0" * frames)