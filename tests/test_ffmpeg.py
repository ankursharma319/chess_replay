from pathlib import Path

from chess_replay.media.ffmpeg import FFmpegEncoder


def test_decodes_each_segment_before_filtered_av_concat(tmp_path: Path, monkeypatch) -> None:
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append(command)

    monkeypatch.setattr("subprocess.run", run)
    encoder = FFmpegEncoder("ffmpeg")
    segments = (tmp_path / "one.mp4", tmp_path / "two.mp4")

    encoder.concatenate(segments, tmp_path / "final.mp4")

    assert commands[0][0] == "ffmpeg"
    assert commands[0].count("-i") == 2
    filter_graph = commands[0][commands[0].index("-filter_complex") + 1]
    assert "[0:a:0]asetpts=PTS-STARTPTS[a0]" in filter_graph
    assert "[1:a:0]asetpts=PTS-STARTPTS[a1]" in filter_graph
    assert "concat=n=2:v=1:a=1[outv][outa]" in filter_graph
    assert commands[0][commands[0].index("-c:a") + 1] == "aac"


def test_uses_millisecond_timebase_and_upward_fps_rounding(tmp_path, monkeypatch) -> None:
    commands: list[list[str]] = []

    def run(command, **kwargs):
        commands.append(command)

    monkeypatch.setattr("subprocess.run", run)
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame-00000.png").write_bytes(b"png")
    (frames / "frame-00001.png").write_bytes(b"png")

    FFmpegEncoder("ffmpeg").encode_frames(
        frames,
        tmp_path / "video.mp4",
        seconds_per_position=1.2,
        frame_rate=30,
        frame_durations=(1.2, 0.9),
    )

    manifest = (frames / "frames.txt").read_text(encoding="ascii")
    assert manifest.startswith("ffconcat version 1.0\n")
    assert manifest.count("option framerate 1000") == 3
    assert "duration 1.200000000" in manifest
    assert "-vf" in commands[0]
    assert "fps=30:round=up" in commands[0]