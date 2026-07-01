from pathlib import Path

from src.config import Settings
from src.downloader import DownloadManager
from src.search import ClipInfo


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
        CLIPCAFE_URL="https://clip.cafe",
        COMB_URL="https://comb.io",
    )


def test_clipcafe_headers_use_clipcafe_referer(tmp_path: Path) -> None:
    manager = DownloadManager(make_settings(tmp_path))
    clip = ClipInfo(
        index=6,
        source="clipcafe",
        source_page_url="https://clip.cafe/example/show/quote/",
        video_url="https://clip.cafe/videos/example.mp4",
    )

    headers = manager._headers_for_clip(clip)

    assert headers["Referer"] == "https://clip.cafe/example/show/quote/"
    assert headers["Origin"] == "https://clip.cafe"
