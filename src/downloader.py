"""Parallel clip downloading with retries and resume support."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import httpx
from pydantic import BaseModel, Field
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from src.config import Settings
from src.search import ClipInfo, SearchResult, SearchService
from src.subtitle import write_cued_ass, write_karaoke_ass, write_plain_text_subtitle
from src.utils import (
    DownloadError,
    console,
    is_hls_url,
    read_json,
    remove_file,
    require_executable,
    write_json,
)

logger = logging.getLogger(__name__)


class DownloadedClip(BaseModel):
    """A downloaded clip on disk."""

    index: int
    source_url: str
    path: str
    subtitle_ass: str | None = None
    subtitle_text: str | None = None
    skipped: bool = False


class DownloadReport(BaseModel):
    """Download report saved after each download run."""

    phrase: str
    slug: str
    clips: list[DownloadedClip] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


class DownloadManager:
    """Download all clips from a search result."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.search_service = SearchService(settings)
        self._semaphore = asyncio.Semaphore(settings.max_parallel)

    async def download_all(self, result: SearchResult) -> DownloadReport:
        """Download every clip in a search result."""

        if not result.clips:
            raise DownloadError("The search result has no clips to download.")

        clip_dir = self.search_service.clip_root_for(result)
        clip_dir.mkdir(parents=True, exist_ok=True)
        self.search_service.subtitle_root_for(result).mkdir(parents=True, exist_ok=True)

        progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        )

        downloaded: list[DownloadedClip] = []
        failed: list[str] = []
        required_failed: list[str] = []
        previous_sources = self._load_previous_sources(result)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=30.0),
            headers=self._default_headers(),
        ) as client:
            with progress:
                clips_to_download = list(result.clips)
                tasks = [
                    self._download_clip(client, progress, result, clip, previous_sources)
                    for clip in clips_to_download
                ]
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for clip, outcome in zip(clips_to_download, outcomes):
            if isinstance(outcome, DownloadedClip):
                downloaded.append(outcome)
            else:
                failed.append(str(outcome))
                if clip.source == "playphrase":
                    required_failed.append(str(outcome))
                logger.error("Download failed: %s", outcome)

        report = DownloadReport(
            phrase=result.phrase,
            slug=result.slug,
            clips=sorted(downloaded, key=lambda item: item.index),
            failed=failed,
        )
        write_json(
            self.settings.download_folder / result.slug / "download-report.json",
            report.model_dump(mode="json"),
        )

        if required_failed or (failed and not downloaded):
            raise DownloadError(
                f"Downloaded {len(downloaded)} clips, but {len(failed)} failed. "
                "See logs and download-report.json for details."
            )
        if failed:
            logger.warning(
                "Skipped %s optional source clips after download failures; continuing with %s clips.",
                len(failed),
                len(downloaded),
            )

        self._remove_stale_clip_files(result)
        return report

    async def _download_clip(
        self,
        client: httpx.AsyncClient,
        progress: Progress,
        result: SearchResult,
        clip: ClipInfo,
        previous_sources: dict[int, str],
    ) -> DownloadedClip:
        """Download one clip with retry handling."""

        async with self._semaphore:
            url = clip.download_url or clip.video_url
            if not url:
                raise DownloadError(f"Clip {clip.index:03d} has no downloadable URL.")

            output_path = self.search_service.clip_root_for(result) / f"{clip.index:03d}.mp4"
            if output_path.exists() and output_path.stat().st_size > 0:
                if previous_sources.get(clip.index) == url:
                    task_id = progress.add_task(f"{clip.index:03d}.mp4 exists", total=1)
                    progress.update(task_id, completed=1)
                    subtitle_ass, subtitle_text = self._write_subtitle_sidecars(result, clip)
                    return DownloadedClip(
                        index=clip.index,
                        source_url=url,
                        path=str(output_path),
                        subtitle_ass=str(subtitle_ass) if subtitle_ass else None,
                        subtitle_text=str(subtitle_text) if subtitle_text else None,
                        skipped=True,
                    )

                logger.info(
                    "Clip %03d exists but source changed or is unknown; downloading again",
                    clip.index,
                )
                remove_file(output_path)
                remove_file(output_path.with_suffix(output_path.suffix + ".part"))

            last_error: Exception | None = None
            for attempt in range(1, self.settings.retries + 1):
                try:
                    headers = self._headers_for_clip(clip)
                    if is_hls_url(url):
                        await self._download_hls(progress, clip.index, url, output_path, headers=headers)
                    elif self._is_mp4_like_url(url):
                        await self._download_http(
                            client,
                            progress,
                            clip.index,
                            url,
                            output_path,
                            headers=headers,
                        )
                    else:
                        source_path = self._source_path_for(output_path, url)
                        await self._download_http(
                            client,
                            progress,
                            clip.index,
                            url,
                            source_path,
                            headers=headers,
                        )
                        await self._convert_to_mp4(progress, clip.index, source_path, output_path)
                        remove_file(source_path)

                    subtitle_ass, subtitle_text = self._write_subtitle_sidecars(result, clip)
                    return DownloadedClip(
                        index=clip.index,
                        source_url=url,
                        path=str(output_path),
                        subtitle_ass=str(subtitle_ass) if subtitle_ass else None,
                        subtitle_text=str(subtitle_text) if subtitle_text else None,
                    )
                except Exception as exc:  # noqa: BLE001 - converted to user-facing DownloadError
                    last_error = exc
                    logger.warning(
                        "Clip %s attempt %s/%s failed: %s",
                        clip.index,
                        attempt,
                        self.settings.retries,
                        exc,
                    )
                    if attempt < self.settings.retries:
                        await asyncio.sleep(self.settings.retry_backoff * attempt)

            raise DownloadError(f"Clip {clip.index:03d} failed: {last_error}") from last_error

    async def _download_http(
        self,
        client: httpx.AsyncClient,
        progress: Progress,
        index: int,
        url: str,
        output_path: Path,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Download a direct media URL with HTTP range resume."""

        part_path = output_path.with_suffix(output_path.suffix + ".part")
        resume_at = part_path.stat().st_size if part_path.exists() else 0
        request_headers = dict(headers or self._default_headers())
        if resume_at:
            request_headers["Range"] = f"bytes={resume_at}-"

        task_id = progress.add_task(f"{index:03d}.mp4", total=None)
        mode = "ab" if resume_at else "wb"

        async with client.stream("GET", url, headers=request_headers) as response:
            if response.status_code == 416 and resume_at:
                part_path.replace(output_path)
                progress.update(task_id, completed=1, total=1)
                return

            if response.status_code >= 400:
                raise DownloadError(f"HTTP {response.status_code} for {url}")

            if resume_at and response.status_code != 206:
                remove_file(part_path)
                resume_at = 0
                mode = "wb"

            content_length = int(response.headers.get("Content-Length") or 0)
            total = content_length + resume_at if content_length else None
            progress.update(task_id, total=total, completed=resume_at)

            async with aiofiles.open(part_path, mode) as file:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    await file.write(chunk)
                    progress.update(task_id, advance=len(chunk))

        if not part_path.exists() or part_path.stat().st_size == 0:
            raise DownloadError(f"Downloaded file for clip {index:03d} is empty.")

        part_path.replace(output_path)
        progress.update(task_id, description=f"{index:03d}.mp4 done")

    async def _download_hls(
        self,
        progress: Progress,
        index: int,
        url: str,
        output_path: Path,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Download an HLS stream to MP4 through FFmpeg."""

        require_executable("ffmpeg")
        task_id = progress.add_task(f"{index:03d}.mp4 hls", total=None)
        temp_path = output_path.with_suffix(".hls.part.mp4")
        remove_file(temp_path)
        request_headers = headers or self._default_headers()
        ffmpeg_headers = "".join(
            f"{key}: {value}\r\n"
            for key, value in request_headers.items()
            if key.lower() in {"referer", "user-agent", "accept"}
        )

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-protocol_whitelist",
            "file,http,https,tcp,tls,crypto",
            "-headers",
            ffmpeg_headers,
            "-i",
            url,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temp_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.debug("FFmpeg stdout: %s", stdout.decode("utf-8", errors="replace"))
            raise DownloadError(stderr.decode("utf-8", errors="replace").strip())

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            raise DownloadError(f"FFmpeg produced an empty file for clip {index:03d}.")

        temp_path.replace(output_path)
        progress.update(task_id, completed=1, total=1, description=f"{index:03d}.mp4 done")

    async def _convert_to_mp4(
        self,
        progress: Progress,
        index: int,
        source_path: Path,
        output_path: Path,
    ) -> None:
        """Convert or remux a non-MP4 media file into MP4."""

        require_executable("ffmpeg")
        task_id = progress.add_task(f"{index:03d}.mp4 convert", total=None)
        temp_output = output_path.with_suffix(".convert.part.mp4")
        remove_file(temp_output)

        copy_command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(source_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temp_output),
        ]
        process = await asyncio.create_subprocess_exec(
            *copy_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.debug("FFmpeg copy remux failed: %s", stderr.decode("utf-8", errors="replace"))
            transcode_command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-y",
                "-i",
                str(source_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(temp_output),
            ]
            process = await asyncio.create_subprocess_exec(
                *transcode_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise DownloadError(stderr.decode("utf-8", errors="replace").strip())

        if not temp_output.exists() or temp_output.stat().st_size == 0:
            raise DownloadError(f"FFmpeg produced an empty MP4 for clip {index:03d}.")

        temp_output.replace(output_path)
        progress.update(task_id, completed=1, total=1, description=f"{index:03d}.mp4 converted")

    @staticmethod
    def _default_headers() -> dict[str, str]:
        """Return browser-like headers for media requests."""

        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Referer": "https://www.playphrase.me/",
        }

    def _headers_for_clip(self, clip: ClipInfo) -> dict[str, str]:
        """Return browser-like headers with a source-appropriate Referer."""

        headers = self._default_headers()
        if clip.source == "clipcafe":
            headers["Referer"] = clip.source_page_url or f"{self.settings.clipcafe_url}/"
            headers["Origin"] = self.settings.clipcafe_url
        elif clip.source == "comb":
            headers["Referer"] = clip.source_page_url or f"{self.settings.comb_url}/"
            headers["Origin"] = self.settings.comb_url
        elif clip.source_page_url:
            headers["Referer"] = clip.source_page_url
        return headers

    def _load_previous_sources(self, result: SearchResult) -> dict[int, str]:
        """Load source URLs from the previous download report for safe skip checks."""

        report_path = self.settings.download_folder / result.slug / "download-report.json"
        if not report_path.exists():
            return {}

        try:
            report = DownloadReport.model_validate(read_json(report_path))
        except Exception as exc:  # noqa: BLE001 - stale report should not block downloads
            logger.warning("Ignoring invalid previous download report %s: %s", report_path, exc)
            return {}

        return {clip.index: clip.source_url for clip in report.clips}

    def _remove_stale_clip_files(self, result: SearchResult) -> None:
        """Remove clip files that are not part of the current search result."""

        clip_dir = self.search_service.clip_root_for(result)
        expected = {f"{clip.index:03d}.mp4" for clip in result.clips}

        for path in clip_dir.glob("*.mp4"):
            if path.name not in expected:
                logger.info("Removing stale clip file %s", path)
                remove_file(path)

        subtitle_dir = self.search_service.subtitle_root_for(result)
        expected_subtitles = {
            f"{clip.index:03d}{suffix}"
            for clip in result.clips
            for suffix in (".ass", ".txt", ".json")
        }
        for path in subtitle_dir.glob("*"):
            if path.is_file() and path.name not in expected_subtitles:
                logger.info("Removing stale subtitle file %s", path)
                remove_file(path)

    def _write_subtitle_sidecars(
        self,
        result: SearchResult,
        clip: ClipInfo,
    ) -> tuple[Path | None, Path | None]:
        """Write ASS karaoke and plain text subtitles for a clip."""

        text = clip.subtitle_text or clip.title
        if not text:
            return None, None

        subtitle_dir = self.search_service.subtitle_root_for(result)
        ass_path = subtitle_dir / f"{clip.index:03d}.ass"
        text_path = subtitle_dir / f"{clip.index:03d}.txt"
        json_path = subtitle_dir / f"{clip.index:03d}.json"

        if clip.subtitle_cues:
            write_cued_ass(
                ass_path,
                cues=clip.subtitle_cues,
                fallback_text=text,
                highlight_text=result.phrase,
            )
            plain_text = "\n".join(cue.text for cue in clip.subtitle_cues)
        else:
            write_karaoke_ass(ass_path, text=text, words=clip.words)
            plain_text = text
        write_plain_text_subtitle(text_path, plain_text)
        write_json(
            json_path,
            {
                "index": clip.index,
                "source": clip.source,
                "text": text,
                "subtitle_cues": [cue.model_dump(mode="json") for cue in clip.subtitle_cues],
                "words": [word.model_dump(mode="json") for word in clip.words],
                "source_url": clip.download_url or clip.video_url,
                "source_page_url": clip.source_page_url,
                "playphrase_id": clip.playphrase_id,
                "movie_name": clip.movie_name,
            },
        )
        return ass_path, text_path

    @staticmethod
    def _is_mp4_like_url(url: str) -> bool:
        """Return True when a direct URL is already an MP4-family file."""

        lower = url.lower()
        return ".mp4" in lower or ".m4v" in lower

    @staticmethod
    def _source_path_for(output_path: Path, url: str) -> Path:
        """Return a temporary source path for non-MP4 direct downloads."""

        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in {".webm", ".mov", ".mkv", ".avi"}:
            suffix = ".media"
        return output_path.with_name(f"{output_path.stem}.source{suffix}")
