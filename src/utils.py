"""Shared utilities for the PlayPhrase Video Builder."""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import unicodedata
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler


def configure_console_encoding() -> None:
    """Make CLI output tolerant of Unicode titles on Windows terminals."""

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")


configure_console_encoding()
console = Console(legacy_windows=False)


class AppError(RuntimeError):
    """Base class for user-facing application errors."""


class NoSearchResultsError(AppError):
    """Raised when PlayPhrase does not return downloadable clips."""


class DownloadError(AppError):
    """Raised when one or more clips cannot be downloaded."""


class FFmpegNotFoundError(AppError):
    """Raised when FFmpeg or FFprobe cannot be found."""


class BrowserAutomationError(AppError):
    """Raised when browser automation fails."""


def project_root() -> Path:
    """Return the project root directory."""

    return Path(__file__).resolve().parents[1]


def timestamp() -> str:
    """Return a filesystem-safe UTC timestamp."""

    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""

    return datetime.now(UTC).isoformat()


def slugify(value: str, fallback: str = "phrase") -> str:
    """Convert a phrase into a stable lowercase filename slug."""

    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or fallback


def title_case_phrase(value: str) -> str:
    """Return a readable title for intro screens."""

    words = [word for word in re.split(r"\s+", value.strip()) if word]
    return " ".join(word[:1].upper() + word[1:] for word in words)


def ensure_directories(*paths: Path) -> None:
    """Create directories if they do not already exist."""

    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def setup_logging(logs_folder: Path, verbose: bool = False) -> Path:
    """Configure console and file logging for one CLI execution."""

    ensure_directories(logs_folder)
    log_path = logs_folder / f"run-{timestamp()}.log"
    level = logging.DEBUG if verbose else logging.INFO

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    rich_handler = RichHandler(console=console, rich_tracebacks=True, show_path=False)
    rich_handler.setFormatter(logging.Formatter("%(message)s"))

    logging.basicConfig(level=level, handlers=[rich_handler, file_handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logging.getLogger(__name__).debug("Log file created at %s", log_path)
    return log_path


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON document from disk."""

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically to disk."""

    ensure_directories(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)


def copy_file(source: Path, destination: Path) -> None:
    """Copy a file, creating the destination directory first."""

    ensure_directories(destination.parent)
    shutil.copy2(source, destination)


def remove_file(path: Path) -> None:
    """Remove a file if it exists."""

    with suppress(FileNotFoundError):
        path.unlink()


def require_executable(name: str) -> Path:
    """Return an executable path or raise a user-facing error."""

    executable = shutil.which(name)
    if not executable:
        raise FFmpegNotFoundError(
            f"{name} was not found on PATH. Install FFmpeg and restart your terminal."
        )
    return Path(executable)


def normalize_whitespace(value: str | None) -> str | None:
    """Normalize whitespace and drop empty strings."""

    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def is_http_url(value: str | None) -> bool:
    """Return True if a value is an HTTP(S) URL."""

    if not value:
        return False
    return value.startswith(("http://", "https://"))


def is_hls_url(value: str | None) -> bool:
    """Return True if a URL appears to be an HLS playlist."""

    return bool(value and ".m3u8" in value.lower())


def is_media_url(value: str | None) -> bool:
    """Return True if a URL looks like downloadable video media."""

    if not is_http_url(value):
        return False
    lower = value.lower()
    return any(ext in lower for ext in (".mp4", ".m4v", ".mov", ".webm", ".m3u8"))
