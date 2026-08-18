import json
from pathlib import Path

import pytest

from chess_replay.tools.dmitlichess import import_dmitlichess


def test_imports_bounded_private_dmitri_pack(tmp_path: Path) -> None:
    extension = tmp_path / "extension"
    clips = extension / "ogg" / "dmitri"
    clips.mkdir(parents=True)
    (extension / "manifest.json").write_text(
        json.dumps({"version": "1.2.3"}),
        encoding="utf-8",
    )
    sounds = {
        "fill": ["fill.ogg"],
        "O-O": ["castle.ogg"],
        "O-O-O": ["castle-long.ogg"],
        "axb5": ["capture.ogg"],
        "check": ["check.ogg"],
        "checkmate": ["mate.ogg"],
        "resign": ["resign.ogg"],
        "start": ["start.ogg"],
        "e4": ["e4.ogg"],
    }
    (clips / "meta.json").write_text(json.dumps({"sounds": sounds}), encoding="utf-8")
    for filename in {item for values in sounds.values() for item in values}:
        (clips / filename).write_bytes(b"ogg")

    target = tmp_path / "pack"
    result = import_dmitlichess(
        target,
        extension_directory=extension,
        private_use_accepted=True,
        clips_per_category=2,
    )

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert result.extension_version == "1.2.3"
    assert result.categories["capture"] == 1
    native_index = json.loads((target / "native-index.json").read_text(encoding="utf-8"))
    assert manifest["checkmate"] == ["clips/native/mate.ogg"]
    assert native_index["e4"] == ["clips/native/e4.ogg"]
    assert (target / manifest["castle"][0]).is_file()
    assert json.loads((target / "provenance.json").read_text())["private_use_only"]


def test_requires_private_use_acknowledgment(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="private-use-only"):
        import_dmitlichess(tmp_path / "target", extension_directory=tmp_path)