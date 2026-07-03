from pathlib import Path

from src.config import Settings


def test_settings_resolves_relative_paths(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
    )

    assert settings.download_folder == tmp_path / "downloads"
    assert settings.output_folder == tmp_path / "outputs"
    assert settings.video_output_folder == tmp_path / "outputs" / "videos"
    assert settings.reel_output_folder == tmp_path / "outputs" / "reels"


def test_source_priority_order_normalizes_aliases(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
        SOURCE_PRIORITY="playphrase,cafe,comb",
    )

    assert settings.source_priority_order == ["playphrase", "clipcafe", "comb"]
