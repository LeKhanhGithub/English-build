"""Wikimedia Commons b-roll search and download helpers."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import httpx
from pydantic import BaseModel, Field

from src.config import Settings
from src.utils import AppError, ensure_directories, read_json, remove_file, slugify, write_json

logger = logging.getLogger(__name__)
COMMONS_USER_AGENT = (
    "playphrase-video-builder/1.0 "
    "(local educational video tool; contact: local@example.invalid)"
)
MAX_BROLL_QUERY_ATTEMPTS = 6
COMMONS_NOISY_TERMS = {
    "arrest",
    "arrested",
    "hiv",
    "hurricane",
    "geese",
    "laser",
    "officer",
    "police",
    "protest",
    "storm",
}
UNDESIRED_DEFAULT_BROLL_TERMS = {
    "boardroom",
    "business",
    "conference",
    "congress",
    "corporate",
    "interview",
    "meeting",
    "office",
    "panel",
    "presentation",
    "seminar",
    "speaker",
    "talk",
    "webinar",
    "workshop",
}


class CommonsVideo(BaseModel):
    """One downloadable video discovered from Wikimedia Commons."""

    title: str
    query: str | None = None
    page_url: str
    file_url: str
    mime: str
    size: int
    width: int | None = None
    height: int | None = None
    license_name: str | None = None
    artist: str | None = None
    credit: str | None = None
    local_path: str | None = None


class CommonsBrollService:
    """Search Wikimedia Commons for lightweight b-roll video clips."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def download_best(
        self,
        query: str | list[str],
        *,
        slug: str,
        force: bool = False,
    ) -> CommonsVideo | None:
        """Download the best Commons b-roll candidate for a phrase slug."""

        if not self.settings.commons_broll_enabled:
            return None

        broll_dir = self.settings.download_folder / slug / "broll"
        ensure_directories(broll_dir)
        metadata_path = broll_dir / "commons-broll.json"

        queries = normalize_search_queries(query)
        query_tokens = set().union(*(normalized_tokens(item) for item in queries)) if queries else set()

        if not force and metadata_path.exists():
            cached = CommonsVideo.model_validate(read_json(metadata_path))
            if (
                cached.local_path
                and Path(cached.local_path).is_file()
                and self._passes_quality_threshold(cached)
                and not self._is_discouraged_default_broll(cached, query_tokens)
            ):
                logger.info("Using cached Wikimedia Commons b-roll: %s", cached.title)
                return cached
            logger.info("Ignoring cached Wikimedia Commons b-roll below current quality/style settings")

        selected: CommonsVideo | None = None
        for item in queries:
            item_tokens = normalized_tokens(item)
            candidates = await self.search(item)
            selected = next(
                (
                    video
                    for video in candidates
                    if not self._is_discouraged_default_broll(video, item_tokens)
                ),
                None,
            )
            if selected:
                break

        if not selected:
            logger.warning("No suitable Wikimedia Commons b-roll found for queries %r", queries)
            return None

        suffix = Path(urlparse(selected.file_url).path).suffix.lower() or ".webm"
        if suffix not in {".mp4", ".m4v", ".webm", ".ogv", ".ogg"}:
            suffix = ".webm"
        output_path = broll_dir / f"commons-{slugify(selected.title, 'broll')[:60]}{suffix}"

        if force:
            remove_file(output_path)

        if not output_path.exists() or output_path.stat().st_size == 0:
            await self._download_file(selected.file_url, output_path, selected.size)

        selected.local_path = str(output_path)
        write_json(metadata_path, selected.model_dump(mode="json"))
        logger.info("Downloaded Wikimedia Commons b-roll: %s", selected.title)
        return selected

    async def search(self, query: str, *, limit: int = 12) -> list[CommonsVideo]:
        """Search Commons file namespace for video files."""

        normalized_query = " ".join(query.split()).strip()
        if not normalized_query:
            return []

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{normalized_query} filetype:video",
            "gsrnamespace": "6",
            "gsrlimit": str(max(1, min(limit, 20))),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|dimensions|extmetadata",
            "format": "json",
            "formatversion": "2",
        }
        headers = {"User-Agent": COMMONS_USER_AGENT}

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(45.0, connect=20.0),
            headers=headers,
            verify=self.settings.commons_verify_ssl,
        ) as client:
            response = await client.get(f"{self.settings.commons_url}/w/api.php", params=params)
            response.raise_for_status()
            data = response.json()

        pages = (data.get("query") or {}).get("pages") or []
        query_tokens = normalized_tokens(normalized_query)
        candidates = [
            video
            for page in pages
            if (video := self._video_from_page(page)) is not None
        ]
        for video in candidates:
            video.query = normalized_query
        return sorted(
            candidates,
            key=lambda video: self._candidate_score(video, query_tokens),
            reverse=True,
        )

    def _video_from_page(self, page: dict[str, object]) -> CommonsVideo | None:
        """Convert one MediaWiki API page into a CommonsVideo."""

        imageinfo = page.get("imageinfo")
        if not isinstance(imageinfo, list) or not imageinfo:
            return None
        info = imageinfo[0]
        if not isinstance(info, dict):
            return None

        mime = str(info.get("mime") or "")
        file_url = str(info.get("url") or "")
        if not mime.startswith("video/") or not file_url.startswith("https://"):
            return None

        size = int(info.get("size") or 0)
        if size <= 0 or size > self.settings.commons_max_bytes:
            return None

        width = int(info["width"]) if isinstance(info.get("width"), int) else None
        height = int(info["height"]) if isinstance(info.get("height"), int) else None
        if not self._passes_quality_threshold(width=width, height=height):
            return None

        title = str(page.get("title") or "Wikimedia Commons video")
        page_url = str(info.get("descriptionurl") or f"{self.settings.commons_url}/wiki/{title}")
        metadata = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
        license_name = metadata_value(metadata, "LicenseShortName")
        artist = metadata_value(metadata, "Artist")
        credit = build_credit(title, artist, license_name)

        return CommonsVideo(
            title=title.removeprefix("File:"),
            page_url=page_url,
            file_url=file_url,
            mime=mime,
            size=size,
            width=width,
            height=height,
            license_name=license_name,
            artist=artist,
            credit=credit,
        )

    def _passes_quality_threshold(
        self,
        video: CommonsVideo | None = None,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> bool:
        """Return True when a b-roll candidate is at least configured HD quality."""

        resolved_width = video.width if video else width
        resolved_height = video.height if video else height
        if not resolved_width or not resolved_height:
            return False

        short_edge = min(resolved_width, resolved_height)
        long_edge = max(resolved_width, resolved_height)
        return (
            short_edge >= self.settings.commons_min_short_edge
            and long_edge >= self.settings.commons_min_long_edge
        )

    @staticmethod
    def _candidate_score(video: CommonsVideo, query_tokens: set[str]) -> tuple[int, int, int, int, int]:
        """Prefer reasonably large, higher-resolution clips without huge downloads."""

        title_tokens = normalized_tokens(video.title)
        title = video.title.lower()
        match_score = len(query_tokens & title_tokens)
        if COMMONS_NOISY_TERMS & title_tokens:
            match_score -= 3
        if UNDESIRED_DEFAULT_BROLL_TERMS & title_tokens and not (
            UNDESIRED_DEFAULT_BROLL_TERMS & query_tokens
        ):
            match_score -= 5
        width = video.width or 0
        height = video.height or 0
        resolution_score = width * height
        mp4_bonus = 1 if video.mime == "video/mp4" else 0
        size_score = min(video.size, 40_000_000)
        portrait_bonus = 1 if (video.height or 0) > (video.width or 0) else 0
        if "holding hands" in title:
            match_score += 2
        return (match_score, portrait_bonus, mp4_bonus, resolution_score, size_score)

    @staticmethod
    def _is_discouraged_default_broll(video: CommonsVideo, query_tokens: set[str]) -> bool:
        """Return True for office/meeting style b-roll unless explicitly requested."""

        title_tokens = normalized_tokens(video.title)
        return bool(UNDESIRED_DEFAULT_BROLL_TERMS & title_tokens) and not bool(
            UNDESIRED_DEFAULT_BROLL_TERMS & query_tokens
        )

    async def _download_file(self, url: str, output_path: Path, expected_size: int) -> None:
        """Download one Commons media file."""

        ensure_directories(output_path.parent)
        part_path = output_path.with_suffix(output_path.suffix + ".part")
        remove_file(part_path)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(120.0, connect=30.0),
            verify=self.settings.commons_verify_ssl,
            headers={"User-Agent": COMMONS_USER_AGENT},
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async with aiofiles.open(part_path, "wb") as file:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 512):
                        if chunk:
                            await file.write(chunk)

        if not part_path.exists() or part_path.stat().st_size == 0:
            raise AppError("Wikimedia Commons b-roll download produced an empty file.")
        if expected_size and part_path.stat().st_size > self.settings.commons_max_bytes:
            remove_file(part_path)
            raise AppError("Wikimedia Commons b-roll exceeded COMMONS_MAX_BYTES.")

        part_path.replace(output_path)


def metadata_value(metadata: dict[str, object], key: str) -> str | None:
    """Extract and clean one Commons extmetadata value."""

    item = metadata.get(key)
    if not isinstance(item, dict):
        return None
    value = item.get("value")
    if not isinstance(value, str):
        return None
    return clean_metadata_text(value)


def clean_metadata_text(value: str) -> str | None:
    """Strip simple HTML from Commons metadata."""

    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text or None


def build_credit(title: str, artist: str | None, license_name: str | None) -> str:
    """Build a compact credit line for generated metadata and video microcopy."""

    pieces = ["Wikimedia Commons", title.removeprefix("File:")]
    if artist:
        pieces.append(artist)
    if license_name:
        pieces.append(license_name)
    return " | ".join(piece for piece in pieces if piece)


def normalize_search_queries(query: str | list[str]) -> list[str]:
    """Normalize and cap b-roll search queries."""

    raw_queries = [query] if isinstance(query, str) else query
    queries: list[str] = []
    for raw_query in raw_queries:
        normalized = re.sub(r"\s+", " ", raw_query).strip()
        if normalized and normalized not in queries:
            queries.append(normalized)
        if len(queries) >= MAX_BROLL_QUERY_ATTEMPTS:
            break
    return queries


def normalized_tokens(value: str) -> set[str]:
    """Return simple lowercase tokens with naive singular normalization."""

    tokens = re.findall(r"[a-z0-9]+", value.lower())
    roots: set[str] = set()
    for token in tokens:
        if len(token) > 3 and token.endswith("s"):
            roots.add(token[:-1])
        roots.add(token)
    return roots
