"""Clip.Cafe fallback source for quote clips with VTT captions."""

from __future__ import annotations

import html
import logging
import re
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

from src.config import Settings
from src.search import ClipInfo, SubtitleCue
from src.subtitle import phrase_has_highlight_match
from src.utils import is_media_url, normalize_whitespace

logger = logging.getLogger(__name__)


class ClipCafeSearchService:
    """Search Clip.Cafe and return matching public MP4 clips with captions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search(self, phrase: str, *, start_index: int, max_clips: int) -> list[ClipInfo]:
        """Return up to max_clips Clip.Cafe clips that match the requested phrase."""

        if not self.settings.clipcafe_enabled or self.settings.clipcafe_max_clips <= 0:
            return []

        limit = max(0, min(max_clips, self.settings.clipcafe_max_clips))
        if limit <= 0:
            return []

        clips: list[ClipInfo] = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(45.0, connect=20.0),
            headers=headers,
        ) as client:
            try:
                candidates = await self._search_candidates(client, phrase)
                logger.info("Clip.Cafe returned %s clip candidates", len(candidates))
                for candidate_url in candidates:
                    if len(clips) >= limit:
                        break
                    clip = await self._build_clip(
                        client,
                        candidate_url,
                        phrase=phrase,
                        index=start_index + len(clips),
                    )
                    if clip:
                        clips.append(clip)
            except httpx.HTTPError as exc:
                logger.warning("Clip.Cafe source failed and will be skipped: %s", exc)

        logger.info("Clip.Cafe added %s public clips", len(clips))
        return clips

    async def _search_candidates(self, client: httpx.AsyncClient, phrase: str) -> list[str]:
        """Search Clip.Cafe and return candidate clip page URLs."""

        query = quote_plus(phrase)
        search_url = f"{self.settings.clipcafe_url}/?s={query}&usersearch=1&onlyTranscript=on"
        response = await client.get(search_url)
        response.raise_for_status()

        links = re.findall(
            r"<a\b[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>",
            response.text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        candidates: list[str] = []
        seen: set[str] = set()
        for href, label_html in links:
            label = clean_html(label_html)
            if not looks_like_clip_result(href, label):
                continue
            url = self._absolute_url(href)
            if not is_same_site(url, self.settings.clipcafe_url) or url in seen:
                continue
            seen.add(url)
            candidates.append(url)

        return candidates

    async def _build_clip(
        self,
        client: httpx.AsyncClient,
        page_url: str,
        *,
        phrase: str,
        index: int,
    ) -> ClipInfo | None:
        """Fetch one Clip.Cafe clip page and convert it into ClipInfo."""

        try:
            response = await client.get(page_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("Could not fetch Clip.Cafe page %s: %s", page_url, exc)
            return None

        page_html = response.text
        video_url = first_match(
            page_html,
            [
                r"<source\b[^>]*src=\"([^\"]+\.mp4[^\"]*)\"",
                r"<meta\b[^>]*property=\"og:video\"[^>]*content=\"([^\"]+\.mp4[^\"]*)\"",
                r"\"contentUrl\"\s*:\s*\"([^\"]+\.mp4[^\"]*)\"",
            ],
        )
        if not video_url:
            return None
        video_url = self._absolute_url(html.unescape(video_url))
        if not is_media_url(video_url):
            return None

        title = extract_clip_title(page_html)
        movie_name = extract_movie_name(page_html)
        thumbnail = first_match(
            page_html,
            [
                r"<meta\b[^>]*property=\"og:image\"[^>]*content=\"([^\"]+)\"",
                r"<meta\b[^>]*name=\"twitter:image\"[^>]*content=\"([^\"]+)\"",
            ],
        )
        if thumbnail:
            thumbnail = self._absolute_url(html.unescape(thumbnail))

        vtt_url = first_match(page_html, [r"<track\b[^>]*src=\"([^\"]+\.vtt[^\"]*)\""])
        cues: list[SubtitleCue] = []
        if vtt_url:
            cues = await self._fetch_vtt_cues(client, self._absolute_url(html.unescape(vtt_url)))

        subtitle_text = "\n".join(cue.text for cue in cues) or title
        searchable_text = "\n".join(
            item for item in (title, subtitle_text) if item and item.strip()
        )
        if not phrase_has_highlight_match(searchable_text, phrase):
            logger.info("Skipping Clip.Cafe clip without requested phrase match: %s", title)
            return None

        duration = round(max((cue.end for cue in cues), default=0) / 1000, 3) or None
        return ClipInfo(
            index=index,
            source="clipcafe",
            title=title,
            movie_name=movie_name,
            source_page_url=page_url,
            video_url=video_url,
            download_url=video_url,
            duration=duration,
            thumbnail=thumbnail,
            subtitle_text=subtitle_text,
            subtitle_cues=cues,
            words=[],
            sources=[video_url],
        )

    async def _fetch_vtt_cues(
        self,
        client: httpx.AsyncClient,
        vtt_url: str,
    ) -> list[SubtitleCue]:
        """Fetch and parse a Clip.Cafe VTT caption file."""

        try:
            response = await client.get(vtt_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("Could not fetch Clip.Cafe VTT %s: %s", vtt_url, exc)
            return []

        return parse_vtt_cues(response.text)

    def _absolute_url(self, value: str) -> str:
        """Resolve Clip.Cafe URLs against the site root."""

        return urljoin(f"{self.settings.clipcafe_url}/", value)


def looks_like_clip_result(href: str, label: str) -> bool:
    """Return True for Clip.Cafe search-result links that point to clip pages."""

    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return False
    parsed = urlparse(href)
    path = parsed.path if parsed.scheme else href
    normalized_path = path.strip("/")
    if not normalized_path or normalized_path.startswith(("s/", "login", "spotlight", "categories")):
        return False
    if normalized_path in {"play", "pro", "movies-by-year"}:
        return False
    if len(normalized_path.split("/")) < 2:
        return False
    return bool(re.search(r"\b\d{2}:\d{2}\b", label))


def is_same_site(url: str, base_url: str) -> bool:
    """Return True when a URL belongs to the configured Clip.Cafe host."""

    return urlparse(url).netloc.lower() == urlparse(base_url).netloc.lower()


def extract_clip_title(page_html: str) -> str | None:
    """Extract the quote title from Clip.Cafe metadata."""

    raw_title = first_match(
        page_html,
        [
            r"<meta\b[^>]*property=\"og:title\"[^>]*content=\"([^\"]+)\"",
            r"<meta\b[^>]*name=\"twitter:title\"[^>]*content=\"([^\"]+)\"",
            r"<title>(.*?)</title>",
        ],
    )
    if not raw_title:
        return None

    title = clean_html(html.unescape(raw_title))
    if "|" in title:
        title = title.split("|", maxsplit=1)[0]
    title = title.strip().strip("'\" ")
    return normalize_whitespace(title)


def extract_movie_name(page_html: str) -> str | None:
    """Extract movie/show name from Clip.Cafe page JavaScript or metadata."""

    raw = first_match(page_html, [r"window\.movieData\s*=\s*\{.*?name:\s*\"([^\"]+)\""])
    if raw:
        return normalize_whitespace(html.unescape(raw))

    og_title = first_match(page_html, [r"<meta\b[^>]*property=\"og:title\"[^>]*content=\"([^\"]+)\""])
    if og_title and "|" in og_title:
        movie = og_title.rsplit("|", maxsplit=1)[-1].replace("Clip", "")
        return normalize_whitespace(html.unescape(movie))
    return None


def first_match(text: str, patterns: list[str]) -> str | None:
    """Return the first regex capture found in text."""

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


def clean_html(value: str) -> str:
    """Strip tags and normalize HTML text."""

    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def parse_vtt_cues(vtt_text: str) -> list[SubtitleCue]:
    """Parse a WEBVTT file into subtitle cues."""

    cues: list[SubtitleCue] = []
    lines = vtt_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if "-->" not in line:
            index += 1
            continue

        start_text, end_text = [part.strip().split()[0] for part in line.split("-->", maxsplit=1)]
        start = parse_vtt_timestamp(start_text)
        end = parse_vtt_timestamp(end_text)
        index += 1

        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1

        text = clean_caption_text(" ".join(text_lines))
        if text and end > start:
            try:
                cues.append(SubtitleCue(text=text, start=start, end=end))
            except ValueError:
                logger.debug("Ignoring invalid Clip.Cafe cue: %s", text)

    return cues


def parse_vtt_timestamp(value: str) -> int:
    """Convert a WEBVTT timestamp to milliseconds."""

    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = float(parts[1])
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    else:
        return 0
    return round(((hours * 3600) + (minutes * 60) + seconds) * 1000)


def clean_caption_text(value: str) -> str:
    """Clean WEBVTT caption text."""

    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\{\\.*?\}", " ", text)
    return normalize_whitespace(html.unescape(text)) or ""
