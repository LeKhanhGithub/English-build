"""Comb.io fallback source for public quote clips."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

from src.browser import BrowserSession, PlaywrightError, PlaywrightTimeoutError
from src.config import Settings
from src.search import ClipInfo, SubtitleCue
from src.subtitle import phrase_has_highlight_match
from src.utils import normalize_whitespace

logger = logging.getLogger(__name__)


class CombSearchService:
    """Search comb.io and create public MP4 clips from matching timeline rows."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search(
        self,
        phrase: str,
        *,
        start_index: int,
        max_clips: int | None = None,
    ) -> list[ClipInfo]:
        """Return up to COMB_MAX_CLIPS public comb.io clips."""

        if not self.settings.comb_enabled or self.settings.comb_max_clips <= 0:
            return []

        limit = max(0, min(max_clips or self.settings.comb_max_clips, self.settings.comb_max_clips))
        if limit <= 0:
            return []

        clips: list[ClipInfo] = []
        async with BrowserSession(self.settings) as page:
            try:
                await self._open_search(page, phrase)
                results = await self._collect_result_links(page)
                logger.info("Comb.io returned %s timeline candidates", len(results))

                for result in results:
                    if len(clips) >= limit:
                        break
                    clip = await self._create_clip_from_result(
                        page,
                        result,
                        phrase=phrase,
                        index=start_index + len(clips),
                    )
                    if clip:
                        clips.append(clip)
            except (PlaywrightError, PlaywrightTimeoutError) as exc:
                logger.warning("Comb.io source failed and will be skipped: %s", exc)

        logger.info("Comb.io added %s public clips", len(clips))
        return clips

    async def _open_search(self, page: Any, phrase: str) -> None:
        """Open comb.io and submit the phrase."""

        await page.goto(
            self.settings.comb_url,
            wait_until="domcontentloaded",
            timeout=self.settings.playwright_timeout,
        )
        await page.wait_for_timeout(1200)

        for selector in ("input[type='search']", "input[type='text']", "input"):
            locator = page.locator(selector).first
            if await locator.count():
                await locator.fill(phrase)
                await locator.press("Enter")
                await page.wait_for_timeout(4500)
                return

        # URL fallback. The UI usually handles search client-side, but this keeps the route explicit.
        await page.goto(
            f"{self.settings.comb_url}/?q={quote_plus(phrase)}",
            wait_until="domcontentloaded",
            timeout=self.settings.playwright_timeout,
        )
        await page.wait_for_timeout(4500)

    @staticmethod
    async def _collect_result_links(page: Any) -> list[dict[str, str]]:
        """Collect timeline result links from comb.io search results."""

        rows: list[dict[str, str]] = []
        seen: set[str] = set()

        for _round in range(4):
            for row in await CombSearchService._collect_visible_result_links(page):
                href = row.get("href")
                if not href or href in seen:
                    continue
                seen.add(href)
                rows.append(row)

            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(900)
            except PlaywrightError:
                break

        return rows

    @staticmethod
    async def _collect_visible_result_links(page: Any) -> list[dict[str, str]]:
        """Collect currently visible timeline result links from comb.io."""

        rows = await page.evaluate(
            """
            () => {
              const absolute = (value) => {
                if (!value) return null;
                try { return new URL(value, location.href).href; } catch { return null; }
              };
              return Array.from(document.querySelectorAll("a[href]"))
                .map((anchor) => ({
                  title: (anchor.innerText || anchor.textContent || "").replace(/\\s+/g, " ").trim(),
                  href: absolute(anchor.getAttribute("href")),
                  cls: String(anchor.className || "")
                }))
                .filter((item) => item.href && item.href.includes("/timeline/") && item.title);
            }
            """
        )

        unique: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            href = row.get("href")
            if not href or href in seen:
                continue
            seen.add(href)
            unique.append({"title": row.get("title") or "", "href": href})
        return unique

    async def _create_clip_from_result(
        self,
        page: Any,
        result: dict[str, str],
        *,
        phrase: str,
        index: int,
    ) -> ClipInfo | None:
        """Open a timeline row, submit Create Clip, and extract the generated MP4."""

        href = result["href"]
        title = normalize_whitespace(result.get("title")) or "Comb.io clip"

        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=self.settings.playwright_timeout)
            await page.wait_for_timeout(1500)
            cues = await self._extract_selected_cues(page)
            subtitle_text = "\n".join(cue.text for cue in cues) or title
            if not self._matches_requested_phrase(phrase, title, subtitle_text):
                logger.info(
                    "Skipping comb.io clip without requested phrase match: %s",
                    title,
                )
                return None

            button = page.locator("button[type='submit'], input[type='submit']").first
            if not await button.count():
                return None
            await button.click(timeout=5000)
            await page.wait_for_load_state("domcontentloaded", timeout=self.settings.playwright_timeout)
            await page.wait_for_timeout(2500)
            data = await self._extract_created_clip(page)
        except PlaywrightError as exc:
            logger.warning("Could not create comb.io clip from %s: %s", href, exc)
            return None

        video_url = data.get("video_url")
        if not video_url:
            return None

        duration = round(max((cue.end for cue in cues), default=0) / 1000, 3) or None

        return ClipInfo(
            index=index,
            source="comb",
            title=title,
            movie_name=data.get("movie_name"),
            source_page_url=data.get("page_url"),
            video_url=video_url,
            download_url=video_url,
            duration=duration,
            thumbnail=data.get("thumbnail"),
            subtitle_text=subtitle_text,
            subtitle_cues=cues,
            words=[],
            sources=[video_url],
        )

    @staticmethod
    def _matches_requested_phrase(phrase: str, title: str | None, subtitle_text: str | None) -> bool:
        """Return True when comb.io text contains the requested phrase/equivalent."""

        searchable_text = "\n".join(
            item for item in (title, subtitle_text) if item and item.strip()
        )
        return phrase_has_highlight_match(searchable_text, phrase)

    @staticmethod
    async def _extract_selected_cues(page: Any) -> list[SubtitleCue]:
        """Extract timed captions from the comb.io selected timeline span."""

        raw_cues = await page.evaluate(
            """
            () => {
              const clips = Array.from(document.querySelectorAll("#s .timeline-clip"))
                .map((clip) => {
                  const ts1Input = clip.querySelector("input[name='ts1']");
                  const ts2Input = clip.querySelector("input[name='ts2']");
                  return {
                    text: (clip.querySelector(".timeline-caption")?.innerText || "").replace(/\\s+/g, " ").trim(),
                    ts1: ts1Input ? Number(ts1Input.value) : null,
                    ts2: ts2Input ? Number(ts2Input.value) : null,
                    disabled: Boolean(ts1Input && ts1Input.disabled)
                  };
                })
                .filter((item) => !item.disabled && Number.isFinite(item.ts1) && Number.isFinite(item.ts2));
              const minStart = Math.min(...clips.map((item) => item.ts1));
              return clips
                .filter((item) => item.text)
                .map((item) => ({
                  text: item.text,
                  start: Math.max(0, Math.round(item.ts1 - minStart)),
                  end: Math.max(1, Math.round(item.ts2 - minStart))
                }));
            }
            """
        )

        cues: list[SubtitleCue] = []
        for item in raw_cues:
            if not isinstance(item, dict):
                continue
            try:
                cues.append(SubtitleCue.model_validate(item))
            except ValueError:
                logger.debug("Ignoring invalid comb.io cue: %s", item)
        return cues

    @staticmethod
    async def _extract_created_clip(page: Any) -> dict[str, str | None]:
        """Extract MP4 and metadata from a comb.io created clip page."""

        return await page.evaluate(
            """
            () => {
              const absolute = (value) => {
                if (!value) return null;
                try { return new URL(value, location.href).href; } catch { return null; }
              };
              const video = document.querySelector("video source[src], video[src]");
              const bodyLines = (document.body.innerText || "")
                .split("\\n")
                .map((line) => line.trim())
                .filter(Boolean);
              const title = document.title || "";
              const movieLine = bodyLines.find((line) => /^S\\d+E\\d+:/i.test(line))
                || bodyLines.find((line) => line && !["comb.io", "Create a Clip"].includes(line));
              return {
                page_url: location.href,
                video_url: absolute(video && (video.getAttribute("src") || video.src)),
                thumbnail: absolute(document.querySelector("video") && document.querySelector("video").getAttribute("poster")),
                movie_name: movieLine || title.replace(/^comb\\.io\\s*-\\s*/i, "") || null
              };
            }
            """
        )
