from pathlib import Path

from chess_replay.media.ffmpeg import FFmpegEncoder


def test_writes_concat_manifest_and_invokes_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append(command)

    monkeypatch.setattr("subprocess.run", run)
    encoder = FFmpegEncoder("ffmpeg")
    segments = (tmp_path / "one.mp4", tmp_path / "two.mp4")

    encoder.concatenate(segments, tmp_path / "final.mp4")

    assert commands[0][0] == "ffmpeg"
    assert "concat" in commands[0]