"""Search PlayPhrase and cache discovered clip metadata."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field

from src.browser import BrowserSession, PlaywrightError, PlaywrightTimeoutError
from src.config import Settings
from src.utils import (
    BrowserAutomationError,
    NoSearchResultsError,
    is_media_url,
    normalize_whitespace,
    read_json,
    slugify,
    utc_now_iso,
    write_json,
)

logger = logging.getLogger(__name__)


class WordTiming(BaseModel):
    """One word timing from PlayPhrase karaoke subtitles."""

    model_config = ConfigDict(populate_by_name=True)

    text: str
    start: int
    end: int
    index: int | None = None
    searched: bool = Field(default=False, alias="searched?")


class SubtitleCue(BaseModel):
    """A timed subtitle cue for source clips that provide line-level captions."""

    text: str
    start: int
    end: int


class ClipInfo(BaseModel):
    """Metadata for one matching PlayPhrase clip."""

    index: int
    source: str = "playphrase"
    title: str | None = None
    movie_name: str | None = None
    playphrase_id: str | None = None
    source_page_url: str | None = None
    video_url: str | None = None
    download_url: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    subtitle_text: str | None = None
    subtitle_cues: list[SubtitleCue] = Field(default_factory=list)
    words: list[WordTiming] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Search result document saved as JSON."""

    phrase: str
    slug: str
    source_url: str
    created_at: str
    clips: list[ClipInfo] = Field(default_factory=list)
    source_status: dict[str, Any] = Field(default_factory=dict)

    @property
    def phrase_download_dir(self) -> Path:
        """Return the relative download folder name for this phrase."""

        return Path(self.slug)


class SearchService:
    """High-level PlayPhrase search and cache service."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache_root = self.settings.download_folder / "search-cache"
        self.latest_path = self.settings.download_folder / "latest-search.json"

    def cache_path_for(self, phrase: str) -> Path:
        """Return the cache path for a phrase."""

        return self.cache_root / f"{slugify(phrase)}.json"

    def clip_root_for(self, result: SearchResult) -> Path:
        """Return the folder where clips for a result should be stored."""

        return self.settings.download_folder / result.slug / "clips"

    def subtitle_root_for(self, result: SearchResult) -> Path:
        """Return the folder where subtitle sidecar files should be stored."""

        return self.settings.download_folder / result.slug / "subtitles"

    def result_path_for(self, result: SearchResult) -> Path:
        """Return the phrase-local search result path."""

        return self.settings.download_folder / result.slug / "search-results.json"

    def load_cached(self, phrase: str) -> SearchResult | None:
        """Load a cached search result for a phrase."""

        path = self.cache_path_for(phrase)
        if not path.exists():
            return None
        return SearchResult.model_validate(read_json(path))

    def load_latest(self) -> SearchResult:
        """Load the most recent search result."""

        if not self.latest_path.exists():
            raise NoSearchResultsError(
                "No previous search found. Run `python main.py search \"your phrase\"` first."
            )
        return SearchResult.model_validate(read_json(self.latest_path))

    def save_result(self, result: SearchResult) -> None:
        """Persist a search result in all expected locations."""

        payload = result.model_dump(mode="json")
        write_json(self.cache_path_for(result.phrase), payload)
        write_json(self.result_path_for(result), payload)
        write_json(self.latest_path, payload)

    async def search(self, phrase: str, *, force: bool = False) -> SearchResult:
        """Search PlayPhrase for a phrase and return matching clip metadata."""

        normalized_phrase = normalize_whitespace(phrase)
        if not normalized_phrase:
            raise NoSearchResultsError("Please provide a non-empty phrase.")

        if not force:
            cached = self.load_cached(normalized_phrase)
            if cached and self._cached_result_is_usable(cached):
                logger.info("Loaded %s cached clips for %r", len(cached.clips), normalized_phrase)
                write_json(self.latest_path, cached.model_dump(mode="json"))
                return cached
            if cached:
                logger.info("Ignoring old cache without PlayPhrase word timings for %r", normalized_phrase)

        result = await self._search_playphrase(normalized_phrase)
        if self.settings.comb_enabled:
            from src.comb import CombSearchService

            comb_start_index = len(result.clips) + 1
            comb_clips = await CombSearchService(self.settings).search(
                normalized_phrase,
                start_index=comb_start_index,
            )
            result.clips.extend(comb_clips)
            result.source_status["comb"] = {
                "enabled": True,
                "strict_phrase_match": True,
                "clips": len(comb_clips),
            }
        else:
            result.source_status["comb"] = {
                "enabled": False,
                "strict_phrase_match": True,
                "clips": 0,
            }

        if self._should_query_clipcafe(result):
            from src.clipcafe import ClipCafeSearchService

            remaining_slots = self._clipcafe_remaining_slots(result)
            clipcafe_clips = await ClipCafeSearchService(self.settings).search(
                normalized_phrase,
                start_index=len(result.clips) + 1,
                max_clips=remaining_slots,
            )
            result.clips.extend(clipcafe_clips)
            result.source_status["clipcafe"] = {
                "enabled": True,
                "strict_phrase_match": True,
                "clips": len(clipcafe_clips),
            }
        else:
            result.source_status["clipcafe"] = {
                "enabled": self.settings.clipcafe_enabled,
                "strict_phrase_match": True,
                "clips": 0,
                "skipped": True,
            }

        self.save_result(result)
        return result

    async def _search_playphrase(self, phrase: str) -> SearchResult:
        """Run browser automation and collect clips."""

        media_urls: dict[str, dict[str, Any]] = {}
        api_clips: list[dict[str, Any]] = []

        async with BrowserSession(self.settings) as page:
            async def handle_response(response: Any) -> None:
                try:
                    self._record_media_response(response.url, media_urls)
                    clips = await self._extract_api_clips_from_response(response)
                    if clips:
                        api_clips.clear()
                        api_clips.extend(clips)
                except Exception as exc:  # noqa: BLE001 - event handler should not break search
                    logger.debug("Ignoring response handler error: %s", exc)

            page.on("response", lambda response: asyncio.create_task(handle_response(response)))

            try:
                logger.info("Opening PlayPhrase search for %r", phrase)
                await self._open_search_page(page, phrase)
                await self._quiet_network_idle(page)
                await self._accept_cookies(page)
                await self._wait_for_active_phrase(page, phrase)
                await self._wait_for_api_clips(api_clips)
                raw_clips = list(api_clips)
                if not raw_clips:
                    raw_clips = await self._fetch_api_clips(page, phrase)
                if not raw_clips:
                    raw_clips = await self._collect_until_stable(page, media_urls)
            except PlaywrightTimeoutError as exc:
                raise BrowserAutomationError(
                    f"Timed out while searching PlayPhrase for {phrase!r}."
                ) from exc
            except PlaywrightError as exc:
                raise BrowserAutomationError(f"PlayPhrase browser automation failed: {exc}") from exc

            result = self._build_result(
                phrase=phrase,
                source_url=page.url,
                raw_clips=raw_clips,
                media_urls=media_urls,
            )

        if not result.clips:
            raise NoSearchResultsError(
                f"No downloadable video clips were found for {phrase!r}. "
                "Try the phrase manually in PlayPhrase, or rerun with HEADLESS=false."
            )

        logger.info("Found %s downloadable clips", len(result.clips))
        return result

    @staticmethod
    def _record_media_response(url: str, media_urls: dict[str, dict[str, Any]]) -> None:
        """Track media URLs observed by Playwright network events."""

        if is_media_url(url):
            media_urls.setdefault(url, {"sources": [url], "download_url": url})

    async def _open_search_page(self, page: Any, phrase: str) -> None:
        """Open PlayPhrase directly on the requested search route."""

        encoded = quote_plus(phrase)
        search_url = f"{self.settings.playphrase_url}/#/search?language=en&q={encoded}"
        await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=self.settings.playwright_timeout,
        )

    async def _wait_for_active_phrase(self, page: Any, phrase: str) -> None:
        """Wait until the PlayPhrase UI reflects the requested phrase."""

        expected = normalize_phrase_for_compare(phrase)
        deadline_seconds = max(2.0, min(self.settings.playwright_timeout / 1000, 15.0))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + deadline_seconds

        while loop.time() < deadline:
            active = await self._read_active_search_phrase(page)
            if active and normalize_phrase_for_compare(active) == expected:
                logger.debug("Active PlayPhrase query is %r", active)
                return
            await asyncio.sleep(0.4)

        active = await self._read_active_search_phrase(page)
        logger.warning(
            "Could not confirm active PlayPhrase query. Expected %r, saw %r.",
            phrase,
            active,
        )

    @staticmethod
    async def _read_active_search_phrase(page: Any) -> str | None:
        """Read the visible PlayPhrase search input value."""

        try:
            value = await page.evaluate(
                """
                () => {
                  const inputs = Array.from(document.querySelectorAll("input[type='text'], input[type='search'], textarea"));
                  const candidates = inputs
                    .map((input) => input.value || input.getAttribute("value") || input.placeholder || "")
                    .map((value) => String(value).trim())
                    .filter(Boolean)
                    .filter((value) => !value.startsWith("/") && !value.includes("?language="));
                  return candidates[0] || null;
                }
                """
            )
        except PlaywrightError:
            return None
        return normalize_whitespace(value) if isinstance(value, str) else None

    async def _fetch_api_clips(self, page: Any, phrase: str) -> list[dict[str, Any]]:
        """Fetch PlayPhrase's own search API so free clips and word timings are exact."""

        limit = self._clip_limit()
        query = quote_plus(phrase)
        request_id = f"search-session-{uuid.uuid4()}"
        api_url = (
            f"{self.settings.playphrase_url}/api/v1/phrases/search"
            f"?q={query}"
            f"&limit={limit}"
            "&language=en"
            "&platform=desktop%20safari"
            "&skip=0"
            f"&request-id={request_id}"
            "&hideHardOffensiveIn17Plus=false"
            "&hideExplicitNudityIn17Plus=false"
        )

        try:
            data = await page.evaluate(
                """
                async (url) => {
                  const response = await fetch(url, {
                    headers: { "Accept": "application/json" },
                    credentials: "include"
                  });
                  if (!response.ok) {
                    throw new Error(`PlayPhrase API returned ${response.status}`);
                  }
                  return await response.json();
                }
                """,
                api_url,
            )
        except PlaywrightError as exc:
            logger.warning("PlayPhrase API fetch failed; falling back to DOM collection: %s", exc)
            return []

        return self._extract_api_clips(data)

    async def _extract_api_clips_from_response(self, response: Any) -> list[dict[str, Any]]:
        """Extract clips from PlayPhrase's own search response when the app requests it."""

        if "/api/v1/phrases/search?" not in response.url:
            return []
        try:
            data = await response.json()
        except PlaywrightError as exc:
            logger.debug("Could not parse PlayPhrase search response JSON: %s", exc)
            return []
        except ValueError:
            return []
        return self._extract_api_clips(data)

    def _extract_api_clips(self, data: Any) -> list[dict[str, Any]]:
        """Convert PlayPhrase API JSON into raw clip dictionaries."""

        phrases = data.get("phrases") if isinstance(data, dict) else None
        if not isinstance(phrases, list):
            return []

        limit = self._clip_limit()
        clips: list[dict[str, Any]] = []
        for item in phrases[:limit]:
            if not isinstance(item, dict):
                continue
            video_url = item.get("video-url")
            if not isinstance(video_url, str) or not is_media_url(video_url):
                continue

            text = normalize_whitespace(item.get("text"))
            video_info = item.get("video-info") if isinstance(item.get("video-info"), dict) else {}
            movie_name = normalize_whitespace(video_info.get("info") if video_info else None)
            words = item.get("words") if isinstance(item.get("words"), list) else []
            duration = self._duration_from_api_item(item)

            clips.append(
                {
                    "source": "playphrase",
                    "title": text,
                    "movie_name": movie_name,
                    "playphrase_id": item.get("id"),
                    "source_page_url": self.settings.playphrase_url,
                    "duration": duration,
                    "video_url": video_url,
                    "download_url": video_url,
                    "sources": [video_url],
                    "subtitle_text": text,
                    "words": words,
                    "download_file_name": item.get("download-file-name"),
                    "start": item.get("start"),
                    "end": item.get("end"),
                }
            )

        logger.info("PlayPhrase API returned %s free downloadable clips", len(clips))
        return clips

    async def _wait_for_api_clips(self, api_clips: list[dict[str, Any]]) -> None:
        """Wait briefly for the in-page PlayPhrase API response to arrive."""

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10
        while loop.time() < deadline:
            if api_clips:
                return
            await asyncio.sleep(0.25)

    @staticmethod
    def _duration_from_api_item(item: dict[str, Any]) -> float | None:
        """Return clip duration from PlayPhrase millisecond offsets."""

        start = item.get("start")
        end = item.get("end")
        if isinstance(start, int | float) and isinstance(end, int | float) and end > start:
            return round((end - start) / 1000, 3)
        words = item.get("words")
        if isinstance(words, list) and words:
            word_ends = [
                word.get("end")
                for word in words
                if isinstance(word, dict) and isinstance(word.get("end"), int | float)
            ]
            if word_ends:
                return round(max(word_ends) / 1000, 3)
        return None

    def _clip_limit(self) -> int:
        """Return the enforced free clip cap for this project."""

        return max(1, min(self.settings.max_clips or 10, 10))

    def _cached_result_is_usable(self, result: SearchResult) -> bool:
        """Return True if a cached result has current subtitle metadata."""

        if self.settings.comb_enabled:
            comb_status = result.source_status.get("comb", {})
            if comb_status.get("strict_phrase_match") is not True:
                return False
        if self.settings.clipcafe_enabled:
            clipcafe_status = result.source_status.get("clipcafe", {})
            if clipcafe_status.get("strict_phrase_match") is not True:
                return False

        return bool(result.clips) and all(
            clip.subtitle_text
            and (clip.source != "playphrase" or clip.words)
            and (clip.source != "comb" or clip.subtitle_cues)
            and (clip.source != "clipcafe" or clip.subtitle_cues)
            and (clip.source != "comb" or self._clip_matches_requested_phrase(result.phrase, clip))
            and (clip.source != "clipcafe" or self._clip_matches_requested_phrase(result.phrase, clip))
            for clip in result.clips
        )

    @staticmethod
    def _clip_matches_requested_phrase(phrase: str, clip: ClipInfo) -> bool:
        """Return True when an external clip still matches the requested phrase."""

        from src.subtitle import phrase_has_highlight_match

        searchable_text = "\n".join(
            value
            for value in (clip.title, clip.subtitle_text)
            if value and value.strip()
        )
        return phrase_has_highlight_match(searchable_text, phrase)

    def _should_query_clipcafe(self, result: SearchResult) -> bool:
        """Return True when Clip.Cafe should try to fill count or duration gaps."""

        if not self.settings.clipcafe_enabled or self.settings.clipcafe_max_clips <= 0:
            return False
        if len(result.clips) < self.settings.target_total_clips:
            return True
        return (
            len(result.clips) < self.settings.max_total_clips
            and self._estimated_duration(result) < self.settings.min_total_duration_seconds
        )

    def _clipcafe_remaining_slots(self, result: SearchResult) -> int:
        """Return how many Clip.Cafe clips can still be added."""

        if len(result.clips) < self.settings.target_total_clips:
            return max(0, self.settings.target_total_clips - len(result.clips))
        if self._estimated_duration(result) < self.settings.min_total_duration_seconds:
            return max(0, self.settings.max_total_clips - len(result.clips))
        return 0

    @staticmethod
    def _estimated_duration(result: SearchResult) -> float:
        """Estimate final content duration from clip metadata."""

        return sum(float(clip.duration or 0) for clip in result.clips)

    async def _quiet_network_idle(self, page: Any) -> None:
        """Wait for the page to settle without failing on chatty pages."""

        try:
            await page.wait_for_load_state("networkidle", timeout=min(self.settings.playwright_timeout, 8000))
        except PlaywrightTimeoutError:
            logger.debug("Network idle wait timed out; continuing")

    async def _accept_cookies(self, page: Any) -> None:
        """Click a common cookie consent button if one appears."""

        labels = ["Accept", "I agree", "Agree", "Got it", "Allow all"]
        for label in labels:
            locator = page.get_by_role("button", name=re.compile(label, re.I)).first
            try:
                if await locator.count() and await locator.is_visible(timeout=1000):
                    await locator.click(timeout=1000)
                    logger.debug("Accepted cookie prompt with label %r", label)
                    return
            except PlaywrightError:
                continue

    async def _submit_search(self, page: Any, phrase: str) -> None:
        """Submit the phrase using visible controls, with URL fallbacks."""

        input_selectors = [
            "input[type='search']",
            "input[placeholder*='phrase' i]",
            "input[placeholder*='search' i]",
            "input[name*='search' i]",
            "input[type='text']",
            "textarea",
            "input:not([type])",
        ]

        for selector in input_selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=1500):
                    await locator.fill(phrase)
                    await locator.press("Enter")
                    logger.info("Submitted phrase through selector %s", selector)
                    return
            except PlaywrightError:
                continue

        for name in (re.compile("search", re.I), re.compile("find", re.I)):
            try:
                button = page.get_by_role("button", name=name).first
                if await button.count() and await button.is_visible(timeout=1000):
                    await button.click(timeout=1000)
                    await page.keyboard.type(phrase)
                    await page.keyboard.press("Enter")
                    logger.info("Submitted phrase through a search button")
                    return
            except PlaywrightError:
                continue

        encoded = quote_plus(phrase)
        fallback_urls = [
            f"{self.settings.playphrase_url}/#/search?language=en&q={encoded}",
            f"{self.settings.playphrase_url}/#/clip-search?language=en&q={encoded}",
            f"{self.settings.playphrase_url}/search?q={encoded}",
            f"{self.settings.playphrase_url}/?q={encoded}",
            f"{self.settings.playphrase_url}/en/search?q={encoded}",
            f"{self.settings.playphrase_url}/#{encoded}",
        ]
        for url in fallback_urls:
            try:
                logger.info("Trying search URL fallback: %s", url)
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.playwright_timeout,
                )
                return
            except PlaywrightError:
                continue

        raise BrowserAutomationError("Could not find a usable PlayPhrase search input.")

    async def _collect_until_stable(
        self,
        page: Any,
        media_urls: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Collect clips while scrolling and clicking load-more style controls."""

        raw_clips: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        stable_rounds = 0

        for round_number in range(self.settings.search_max_rounds):
            await asyncio.sleep(0.8)
            dom_clips = await self._collect_dom_clips(page)
            new_count = 0

            for clip in [*dom_clips, *media_urls.values()]:
                key = self._raw_clip_key(clip)
                if not key or key in seen_keys:
                    continue
                raw_clips.append(clip)
                seen_keys.add(key)
                new_count += 1

            logger.debug(
                "Collection round %s discovered %s new clips",
                round_number + 1,
                new_count,
            )

            limit = self._clip_limit()
            if len(raw_clips) >= limit:
                return raw_clips[:limit]

            clicked = await self._click_more_or_next(page)
            await self._scroll_page(page)

            if new_count == 0 and not clicked:
                stable_rounds += 1
            else:
                stable_rounds = 0

            if stable_rounds >= 2:
                break

        return raw_clips

    async def _collect_dom_clips(self, page: Any) -> list[dict[str, Any]]:
        """Extract media metadata from the current DOM."""

        clips = await page.evaluate(
            """
            () => {
              const mediaExtensions = [".mp4", ".m4v", ".mov", ".webm", ".m3u8"];
              const imageExtensions = [".jpg", ".jpeg", ".png", ".webp"];

              function absolute(value) {
                if (!value || typeof value !== "string") return null;
                if (value.startsWith("blob:") || value.startsWith("data:")) return null;
                try { return new URL(value, location.href).href; } catch { return null; }
              }

              function hasExt(value, exts) {
                if (!value) return false;
                const lower = value.toLowerCase();
                return exts.some(ext => lower.includes(ext));
              }

              function clean(text) {
                if (!text) return null;
                const value = String(text).replace(/\\s+/g, " ").trim();
                return value || null;
              }

              function nearbyText(node) {
                const container = node.closest("article, li, section, [class*='card'], [class*='clip'], [class*='result'], div");
                return clean((container || node).innerText || "");
              }

              function textLines(text) {
                if (!text) return [];
                return text.split("\\n").map(item => item.trim()).filter(Boolean);
              }

              function firstImage(node) {
                const container = node.closest("article, li, section, [class*='card'], [class*='clip'], [class*='result'], div") || document;
                const image = container.querySelector("img");
                if (!image) return null;
                return absolute(image.currentSrc || image.src || image.getAttribute("data-src"));
              }

              const clips = [];

              for (const video of Array.from(document.querySelectorAll("video"))) {
                const sources = [];
                for (const value of [video.currentSrc, video.src, video.poster]) {
                  const url = absolute(value);
                  if (url && hasExt(url, mediaExtensions)) sources.push(url);
                }
                for (const source of Array.from(video.querySelectorAll("source"))) {
                  const url = absolute(source.src || source.getAttribute("src"));
                  if (url && hasExt(url, mediaExtensions)) sources.push(url);
                }
                const text = nearbyText(video);
                const lines = textLines((video.closest("article, li, section, [class*='card'], [class*='clip'], [class*='result'], div") || video).innerText || "");
                clips.push({
                  title: clean(video.getAttribute("title")) || lines[0] || clean(document.title),
                  movie_name: lines.length > 1 ? lines[1] : null,
                  duration: Number.isFinite(video.duration) ? video.duration : null,
                  thumbnail: absolute(video.poster) || firstImage(video),
                  video_url: sources[0] || null,
                  download_url: sources[0] || null,
                  sources: [...new Set(sources)],
                  text
                });
              }

              const nodes = Array.from(document.querySelectorAll("a[href], [data-src], [data-video], [data-url], [data-href]"));
              for (const node of nodes) {
                const values = [];
                if (node.href) values.push(node.href);
                for (const attr of ["data-src", "data-video", "data-url", "data-href", "src"]) {
                  const value = node.getAttribute && node.getAttribute(attr);
                  if (value) values.push(value);
                }
                for (const item of values) {
                  const url = absolute(item);
                  if (!url || !hasExt(url, mediaExtensions)) continue;
                  const text = nearbyText(node);
                  const lines = textLines((node.closest("article, li, section, [class*='card'], [class*='clip'], [class*='result'], div") || node).innerText || "");
                  clips.push({
                    title: clean(node.getAttribute("title")) || clean(node.getAttribute("aria-label")) || lines[0] || clean(document.title),
                    movie_name: lines.length > 1 ? lines[1] : null,
                    duration: null,
                    thumbnail: firstImage(node),
                    video_url: url,
                    download_url: url,
                    sources: [url],
                    text
                  });
                }
              }

              for (const image of Array.from(document.querySelectorAll("img"))) {
                const src = absolute(image.currentSrc || image.src || image.getAttribute("data-src"));
                if (!src || !hasExt(src, imageExtensions)) continue;
                const container = image.closest("article, li, section, [class*='card'], [class*='clip'], [class*='result']");
                if (!container) continue;
                const mediaLinks = Array.from(container.querySelectorAll("a[href], video, source"))
                  .map(el => absolute(el.href || el.currentSrc || el.src || el.getAttribute("src")))
                  .filter(url => url && hasExt(url, mediaExtensions));
                if (!mediaLinks.length) continue;
                const lines = textLines(container.innerText || "");
                clips.push({
                  title: lines[0] || clean(document.title),
                  movie_name: lines.length > 1 ? lines[1] : null,
                  duration: null,
                  thumbnail: src,
                  video_url: mediaLinks[0],
                  download_url: mediaLinks[0],
                  sources: [...new Set(mediaLinks)],
                  text: clean(container.innerText || "")
                });
              }

              return clips;
            }
            """
        )
        return list(clips or [])

    async def _click_more_or_next(self, page: Any) -> bool:
        """Click common pagination controls if present."""

        selectors = [
            "button:has-text('Load more')",
            "button:has-text('More')",
            "button:has-text('Next')",
            "a:has-text('Load more')",
            "a:has-text('More')",
            "a:has-text('Next')",
            "[aria-label*='next' i]",
            "[aria-label*='more' i]",
            "[class*='next' i]",
            "[class*='more' i]",
        ]
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=800):
                    if await locator.is_enabled(timeout=800):
                        await locator.click(timeout=1500)
                        await self._quiet_network_idle(page)
                        logger.debug("Clicked pagination control %s", selector)
                        return True
            except PlaywrightError:
                continue
        return False

    @staticmethod
    async def _scroll_page(page: Any) -> None:
        """Scroll to trigger lazy-loaded results."""

        with_page = page
        try:
            await with_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except PlaywrightError:
            return

    def _build_result(
        self,
        *,
        phrase: str,
        source_url: str,
        raw_clips: list[dict[str, Any]],
        media_urls: dict[str, dict[str, Any]],
    ) -> SearchResult:
        """Convert raw scraper output into validated search results."""

        merged = [*raw_clips, *media_urls.values()]
        seen: set[str] = set()
        clips: list[ClipInfo] = []

        for raw in merged:
            sources = self._clean_sources(raw)
            if not sources:
                continue

            best_url = select_best_source(sources)
            key = best_url.split("#", maxsplit=1)[0]
            if key in seen:
                continue
            seen.add(key)

            title = normalize_whitespace(raw.get("title"))
            if title and title.lower() in {"playphrase.me", "playphrase"}:
                title = None

            source = normalize_whitespace(raw.get("source")) or "playphrase"
            movie_name = normalize_whitespace(raw.get("movie_name"))
            playphrase_id = normalize_whitespace(raw.get("playphrase_id"))
            source_page_url = normalize_whitespace(raw.get("source_page_url"))
            thumbnail = normalize_whitespace(raw.get("thumbnail"))
            subtitle_text = normalize_whitespace(raw.get("subtitle_text")) or title
            subtitle_cues = self._parse_subtitle_cues(raw.get("subtitle_cues"))
            duration = raw.get("duration")
            if not isinstance(duration, int | float):
                duration = None
            words = self._parse_word_timings(raw.get("words"))

            clips.append(
                ClipInfo(
                    index=len(clips) + 1,
                    source=source,
                    title=title,
                    movie_name=movie_name,
                    playphrase_id=playphrase_id,
                    source_page_url=source_page_url,
                    video_url=best_url,
                    download_url=best_url,
                    duration=duration,
                    thumbnail=thumbnail,
                    subtitle_text=subtitle_text,
                    subtitle_cues=subtitle_cues,
                    words=words,
                    sources=sources,
                )
            )

        return SearchResult(
            phrase=phrase,
            slug=slugify(phrase),
            source_url=source_url,
            created_at=utc_now_iso(),
            clips=clips,
        )

    @staticmethod
    def _clean_sources(raw: dict[str, Any]) -> list[str]:
        """Return unique media URLs from a raw clip object."""

        values: list[str] = []
        for key in ("download_url", "video_url"):
            value = raw.get(key)
            if isinstance(value, str):
                values.append(value)
        raw_sources = raw.get("sources") or []
        if isinstance(raw_sources, list):
            values.extend(item for item in raw_sources if isinstance(item, str))

        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            if is_media_url(value) and value not in seen:
                unique.append(value)
                seen.add(value)
        return unique

    @staticmethod
    def _raw_clip_key(raw: dict[str, Any]) -> str | None:
        """Return a stable key for a raw clip candidate."""

        sources = SearchService._clean_sources(raw)
        return select_best_source(sources) if sources else None

    @staticmethod
    def _parse_word_timings(value: Any) -> list[WordTiming]:
        """Validate PlayPhrase word timings without failing the whole search."""

        if not isinstance(value, list):
            return []

        words: list[WordTiming] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                words.append(WordTiming.model_validate(item))
            except ValueError:
                logger.debug("Ignoring invalid word timing: %s", item)
        return words

    @staticmethod
    def _parse_subtitle_cues(value: Any) -> list[SubtitleCue]:
        """Validate line-level subtitle cues without failing the whole search."""

        if not isinstance(value, list):
            return []

        cues: list[SubtitleCue] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                cues.append(SubtitleCue.model_validate(item))
            except ValueError:
                logger.debug("Ignoring invalid subtitle cue: %s", item)
        return cues


def select_best_source(sources: list[str]) -> str:
    """Choose the likely highest-quality source URL."""

    if not sources:
        raise ValueError("No sources provided")

    def score(url: str) -> tuple[int, int, int]:
        lower = url.lower()
        extension_score = 0
        if ".m3u8" in lower:
            extension_score = 400
        elif ".mp4" in lower or ".m4v" in lower:
            extension_score = 350
        elif ".webm" in lower:
            extension_score = 250
        elif ".mov" in lower:
            extension_score = 200

        resolution_score = 0
        for pattern in (r"(?P<h>[1-9][0-9]{2,3})p", r"(?P<w>[1-9][0-9]{2,3})x(?P<h>[1-9][0-9]{2,3})"):
            match = re.search(pattern, lower)
            if not match:
                continue
            if "h" in match.groupdict() and match.group("h"):
                resolution_score = max(resolution_score, int(match.group("h")))

        bitrate_score = 0
        bitrate = re.search(r"(?P<br>[1-9][0-9]{2,5})k", lower)
        if bitrate:
            bitrate_score = int(bitrate.group("br"))

        return extension_score, resolution_score, bitrate_score

    return max(sources, key=score)


def normalize_phrase_for_compare(value: str) -> str:
    """Normalize phrases before comparing requested and active PlayPhrase queries."""

    normalized = normalize_whitespace(value) or ""
    return re.sub(r"[^\w\s']+", "", normalized.lower()).strip()
