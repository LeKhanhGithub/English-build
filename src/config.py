"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, PositiveFloat, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils import ensure_directories, project_root

PROJECT_ROOT = project_root()


class Settings(BaseSettings):
    """Validated runtime settings."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    project_root: Path = Field(default=PROJECT_ROOT, exclude=True)
    headless: bool = Field(default=True, validation_alias="HEADLESS")
    download_folder: Path = Field(default=Path("downloads"), validation_alias="DOWNLOAD_FOLDER")
    output_folder: Path = Field(default=Path("outputs"), validation_alias="OUTPUT_FOLDER")
    logs_folder: Path = Field(default=Path("logs"), validation_alias="LOGS_FOLDER")
    assets_folder: Path = Field(default=Path("assets"), validation_alias="ASSETS_FOLDER")
    temp_folder: Path = Field(default=Path(".tmp"), validation_alias="TEMP_FOLDER")
    playwright_timeout: PositiveInt = Field(default=45_000, validation_alias="PLAYWRIGHT_TIMEOUT")
    max_parallel: PositiveInt = Field(default=4, validation_alias="MAX_PARALLEL")
    retries: PositiveInt = Field(default=3, validation_alias="RETRIES")
    retry_backoff: PositiveFloat = Field(default=1.5, validation_alias="RETRY_BACKOFF")
    search_max_rounds: PositiveInt = Field(default=30, validation_alias="SEARCH_MAX_ROUNDS")
    max_clips: int = Field(default=10, ge=0, validation_alias="MAX_CLIPS")
    target_total_clips: int = Field(default=10, ge=1, le=20, validation_alias="TARGET_TOTAL_CLIPS")
    max_total_clips: int = Field(default=12, ge=1, le=20, validation_alias="MAX_TOTAL_CLIPS")
    min_total_duration_seconds: int = Field(
        default=45,
        ge=0,
        le=600,
        validation_alias="MIN_TOTAL_DURATION_SECONDS",
    )
    comb_enabled: bool = Field(default=True, validation_alias="COMB_ENABLED")
    comb_max_clips: int = Field(default=5, ge=0, le=10, validation_alias="COMB_MAX_CLIPS")
    comb_url: str = Field(default="https://comb.io", validation_alias="COMB_URL")
    clipcafe_enabled: bool = Field(default=True, validation_alias="CLIPCAFE_ENABLED")
    clipcafe_max_clips: int = Field(default=5, ge=0, le=10, validation_alias="CLIPCAFE_MAX_CLIPS")
    clipcafe_url: str = Field(default="https://clip.cafe", validation_alias="CLIPCAFE_URL")
    playphrase_url: str = Field(
        default="https://www.playphrase.me",
        validation_alias="PLAYPHRASE_URL",
    )

    @model_validator(mode="after")
    def normalize_paths(self) -> "Settings":
        """Resolve folder settings relative to the project root."""

        for field_name in (
            "download_folder",
            "output_folder",
            "logs_folder",
            "assets_folder",
            "temp_folder",
        ):
            value = getattr(self, field_name)
            if not value.is_absolute():
                value = self.project_root / value
            setattr(self, field_name, value.resolve())
        self.playphrase_url = self.playphrase_url.rstrip("/")
        self.comb_url = self.comb_url.rstrip("/")
        self.clipcafe_url = self.clipcafe_url.rstrip("/")
        if self.target_total_clips < self.max_clips:
            self.target_total_clips = min(20, max(self.max_clips, 1))
        if self.max_total_clips < self.target_total_clips:
            self.max_total_clips = self.target_total_clips
        return self

    def ensure_folders(self) -> None:
        """Create all runtime folders."""

        ensure_directories(
            self.download_folder,
            self.output_folder,
            self.logs_folder,
            self.assets_folder,
            self.temp_folder,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings."""

    settings = Settings()
    settings.ensure_folders()
    return settings
