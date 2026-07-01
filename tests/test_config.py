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

