from pathlib import Path

import pytest

from src.merger import VideoMerger


def test_probe_video_falls_back_when_ffprobe_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"placeholder")

    def blocked_run(*_args: object, **_kwargs: object) -> object:
        raise OSError("Application Control policy has blocked this file")

    monkeypatch.setattr("src.merger.subprocess.run", blocked_run)

    spec = VideoMerger.probe_video(video_path)

    assert spec.width == 1920
    assert spec.height == 1080
    assert spec.fps == 30.0
    assert spec.has_audio is True
