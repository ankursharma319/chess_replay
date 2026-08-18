"""Import a private local Dmitri clip pack from the dmitlichess extension."""

from __future__ import annotations

import json
import shutil
import struct
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

EXTENSION_ID = "haigaafonckooggfpmjplfpbkafelcfe"


@dataclass(frozen=True, slots=True)
class DmitlichessImportResult:
    target_directory: Path
    extension_version: str
    clip_count: int
    categories: dict[str, int]


def import_dmitlichess(
    target_directory: Path,
    *,
    extension_directory: Path | None = None,
    download: bool = False,
    private_use_accepted: bool = False,
    clips_per_category: int = 8,
) -> DmitlichessImportResult:
    """Create an ignored local pack without redistributing extension recordings."""
    if not private_use_accepted:
        raise ValueError("Import requires explicit private-use-only acknowledgment")
    if clips_per_category < 1:
        raise ValueError("clips_per_category must be positive")
    if (extension_directory is None) == (not download):
        raise ValueError("Choose exactly one of extension_directory or download")

    with tempfile.TemporaryDirectory(prefix="dmitlichess-import-") as temporary:
        temporary_path = Path(temporary)
        source = extension_directory
        if download:
            crx_path = temporary_path / "dmitlichess.crx"
            _download_crx(crx_path)
            source = temporary_path / "extension"
            _extract_crx(crx_path, source)
        if source is None:
            raise AssertionError("source must be resolved")
        return _build_pack(source, target_directory, clips_per_category)


def _build_pack(
    extension_directory: Path,
    target_directory: Path,
    limit: int,
) -> DmitlichessImportResult:
    extension_manifest = _json_object(extension_directory / "manifest.json")
    dmitri_directory = extension_directory / "ogg" / "dmitri"
    native_metadata = _json_object(dmitri_directory / "meta.json")
    sounds = native_metadata.get("sounds")
    if not isinstance(sounds, dict):
        raise ValueError("Dmitri metadata does not contain a sounds object")

    selected: dict[str, tuple[str, ...]] = {
        "intro": _category(sounds, "fill", limit),
        "castle": _combined_categories(sounds, ("O-O", "O-O-O"), limit),
        "capture": _capture_clips(sounds, limit),
        "check": _category(sounds, "check", limit),
        "checkmate": _category(sounds, "checkmate", limit),
        "promotion": _category(sounds, "fill", limit),
        "result": _category(sounds, "resign", limit),
        "default": _category(sounds, "fill", limit),
    }
    missing = [kind for kind, files in selected.items() if not files]
    if missing:
        raise ValueError(f"Dmitri pack is missing required categories: {', '.join(missing)}")

    if target_directory.exists():
        shutil.rmtree(target_directory)
    target_directory.mkdir(parents=True)
    manifest: dict[str, list[str]] = {}
    copied = 0
    for kind, filenames in selected.items():
        category_directory = target_directory / "clips" / kind
        category_directory.mkdir(parents=True)
        relative_files: list[str] = []
        for filename in filenames:
            source = dmitri_directory / filename
            if not source.is_file():
                raise ValueError(f"Dmitri clip listed in metadata is missing: {source}")
            destination = category_directory / source.name
            shutil.copy2(source, destination)
            relative_files.append(destination.relative_to(target_directory).as_posix())
            copied += 1
        manifest[kind] = relative_files

    (target_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    provenance = {
        "source": "dmitlichess Chrome extension",
        "extension_id": EXTENSION_ID,
        "extension_version": str(extension_manifest.get("version", "unknown")),
        "private_use_only": True,
        "redistribution_license": None,
        "note": "Audio is third-party content and must not be committed or redistributed.",
    }
    (target_directory / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n",
        encoding="utf-8",
    )
    return DmitlichessImportResult(
        target_directory=target_directory,
        extension_version=provenance["extension_version"],
        clip_count=copied,
        categories={kind: len(files) for kind, files in manifest.items()},
    )


def _download_crx(destination: Path) -> None:
    query = urllib.parse.urlencode(
        {
            "response": "redirect",
            "prodversion": "140.0.0.0",
            "acceptformat": "crx2,crx3",
            "x": f"id={EXTENSION_ID}&installsource=ondemand&uc",
        }
    )
    request = urllib.request.Request(
        f"https://clients2.google.com/service/update2/crx?{query}",
        headers={"User-Agent": "chess-replay-private-importer/0.1"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())


def _extract_crx(crx_path: Path, destination: Path) -> None:
    data = crx_path.read_bytes()
    if data[:4] != b"Cr24":
        raise ValueError("Downloaded file is not a CRX package")
    version = struct.unpack("<I", data[4:8])[0]
    if version == 3:
        offset = 12 + struct.unpack("<I", data[8:12])[0]
    elif version == 2:
        public_key_size = struct.unpack("<I", data[8:12])[0]
        signature_size = struct.unpack("<I", data[12:16])[0]
        offset = 16 + public_key_size + signature_size
    else:
        raise ValueError(f"Unsupported CRX version: {version}")

    with tempfile.NamedTemporaryFile(suffix=".zip") as archive_file:
        archive_file.write(data[offset:])
        archive_file.flush()
        with zipfile.ZipFile(archive_file.name) as archive:
            for member in archive.infolist():
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"Unsafe extension archive path: {member.filename}")
            archive.extractall(destination)


def _category(sounds: dict[str, Any], key: str, limit: int) -> tuple[str, ...]:
    value = sounds.get(key, [])
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value[:limit] if isinstance(item, str))


def _combined_categories(
    sounds: dict[str, Any],
    keys: tuple[str, ...],
    limit: int,
) -> tuple[str, ...]:
    files: list[str] = []
    for key in keys:
        files.extend(_category(sounds, key, limit))
    return tuple(dict.fromkeys(files))[:limit]


def _capture_clips(sounds: dict[str, Any], limit: int) -> tuple[str, ...]:
    files: list[str] = []
    for key in sorted(sounds):
        if "x" not in key:
            continue
        files.extend(_category(sounds, key, limit))
        if len(files) >= limit:
            break
    return tuple(dict.fromkeys(files))[:limit]


def _json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Required extension file is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value