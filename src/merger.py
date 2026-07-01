"""FFmpeg video merging, normalization, and title-card generation."""

from __future__ import annotations

import json
import logging
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.progress import Progress, TextColumn

from src.config import Settings
from src.search import SearchResult, SearchService
from src.subtitle import clip_filter, title_card_filter
from src.utils import (
    AppError,
    console,
    ensure_directories,
    remove_file,
    require_executable,
    title_case_phrase,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VideoSpec:
    """A small subset of FFprobe metadata needed for normalization."""

    width: int
    height: int
    fps: float
    duration: float | None
    has_audio: bool
    video_codec: str | None


class VideoMerger:
    """Merge downloaded clips into one upload-ready MP4."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.search_service = SearchService(settings)

    def merge_result(
        self,
        result: SearchResult,
        *,
        output_path: Path | None = None,
        add_intro: bool = True,
        add_outro: bool = False,
        subtitles: bool = True,
    ) -> Path:
        """Merge all downloaded clips for a search result."""

        clip_paths = self.discover_clip_paths(result)
        if not clip_paths:
            raise AppError(
                f"No downloaded clips found for {result.phrase!r}. "
                "Run `python main.py download` first."
            )

        destination = output_path or self.settings.output_folder / f"{result.slug}.mp4"
        subtitle_paths = self.discover_subtitle_paths(result)
        return self.merge_files(
            clip_paths=clip_paths,
            subtitle_paths=subtitle_paths,
            phrase=result.phrase,
            output_path=destination,
            add_intro=add_intro,
            add_outro=add_outro,
            subtitles=subtitles,
        )

    def discover_clip_paths(self, result: SearchResult) -> list[Path]:
        """Return downloaded clip files that belong to the current search result."""

        clip_dir = self.search_service.clip_root_for(result)
        paths = [clip_dir / f"{clip.index:03d}.mp4" for clip in result.clips]
        return [path for path in paths if path.is_file()]

    def discover_subtitle_paths(self, result: SearchResult) -> list[Path | None]:
        """Return ASS subtitle files aligned to current search-result clip indexes."""

        clip_dir = self.search_service.clip_root_for(result)
        subtitle_dir = self.search_service.subtitle_root_for(result)
        paths: list[Path | None] = []
        for clip in result.clips:
            clip_path = clip_dir / f"{clip.index:03d}.mp4"
            if not clip_path.is_file():
                continue
            path = subtitle_dir / f"{clip.index:03d}.ass"
            paths.append(path if path.is_file() else None)
        return paths

    def merge_files(
        self,
        *,
        clip_paths: list[Path],
        subtitle_paths: list[Path | None] | None = None,
        phrase: str,
        output_path: Path,
        add_intro: bool = True,
        add_outro: bool = False,
        subtitles: bool = True,
    ) -> Path:
        """Merge explicit clip paths into an MP4 output."""

        require_executable("ffmpeg")
        require_executable("ffprobe")
        ensure_directories(output_path.parent, self.settings.temp_folder)

        clip_paths = [path.resolve() for path in clip_paths if path.exists() and path.stat().st_size > 0]
        if not clip_paths:
            raise AppError("No non-empty MP4 files are available to merge.")

        with TemporaryDirectory(prefix="merge-", dir=self.settings.temp_folder) as temp_name:
            temp_dir = Path(temp_name)
            if not subtitles and not add_intro and not add_outro:
                copy_output = temp_dir / "copy-final.mp4"
                if self._try_concat_copy(clip_paths, copy_output, temp_dir):
                    copy_output.replace(output_path)
                    return output_path

            first_spec = self.probe_video(clip_paths[0])
            target = self._target_spec(first_spec)
            aligned_subtitle_paths = self._align_subtitle_paths(clip_paths, subtitle_paths)
            normalized_paths = self._render_sequence(
                clip_paths=clip_paths,
                subtitle_paths=aligned_subtitle_paths,
                phrase=phrase,
                target=target,
                temp_dir=temp_dir,
                add_intro=add_intro,
                add_outro=add_outro,
                subtitles=subtitles,
            )

            final_temp = temp_dir / "final.mp4"
            self._concat_copy(normalized_paths, final_temp, temp_dir)
            final_temp.replace(output_path)

        logger.info("Merged final video at %s", output_path)
        return output_path

    def _render_sequence(
        self,
        *,
        clip_paths: list[Path],
        subtitle_paths: list[Path | None],
        phrase: str,
        target: VideoSpec,
        temp_dir: Path,
        add_intro: bool,
        add_outro: bool,
        subtitles: bool,
    ) -> list[Path]:
        """Normalize clips and optional title cards into concat-ready files."""

        rendered: list[Path] = []
        title = title_case_phrase(phrase)

        progress = Progress(
            TextColumn("[bold green]{task.description}"),
            console=console,
            transient=False,
        )
        with progress:
            if add_intro:
                intro_path = temp_dir / "000-intro.mp4"
                task_id = progress.add_task("Rendering intro", total=None)
                self._generate_title_card(title, target, intro_path)
                progress.update(task_id, completed=1, total=1)
                rendered.append(intro_path)

            for index, clip_path in enumerate(clip_paths, start=1):
                output = temp_dir / f"{index:03d}-normalized.mp4"
                task_id = progress.add_task(f"Normalizing {clip_path.name}", total=None)
                spec = self.probe_video(clip_path)
                self._normalize_clip(
                    input_path=clip_path,
                    output_path=output,
                    source_spec=spec,
                    target=target,
                    subtitle=phrase if subtitles else None,
                    subtitle_file=subtitle_paths[index - 1] if subtitles else None,
                )
                progress.update(task_id, completed=1, total=1)
                rendered.append(output)

            if add_outro:
                outro_path = temp_dir / "999-outro.mp4"
                task_id = progress.add_task("Rendering outro", total=None)
                self._generate_title_card("Follow for Daily English", target, outro_path)
                progress.update(task_id, completed=1, total=1)
                rendered.append(outro_path)

        return rendered

    def _normalize_clip(
        self,
        *,
        input_path: Path,
        output_path: Path,
        source_spec: VideoSpec,
        target: VideoSpec,
        subtitle: str | None,
        subtitle_file: Path | None = None,
    ) -> None:
        """Transcode one clip into the shared output profile."""

        filters = clip_filter(target.width, target.height, subtitle, subtitle_file)
        fps = self._format_fps(target.fps)
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(input_path),
        ]

        if source_spec.has_audio:
            command.extend(["-map", "0:v:0", "-map", "0:a:0"])
        else:
            duration = source_spec.duration or 1.0
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    f"{duration:.3f}",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                ]
            )

        command.extend(
            [
                "-vf",
                filters,
                "-r",
                fps,
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
                "-ar",
                "48000",
                "-ac",
                "2",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        self._run(command)

    def _generate_title_card(self, text: str, target: VideoSpec, output_path: Path) -> None:
        """Generate a two-second intro or outro screen."""

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x111111:s={target.width}x{target.height}:r={self._format_fps(target.fps)}:d=2",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            title_card_filter(
                text,
                target.width,
                target.height,
                text_dir=output_path.parent,
                file_prefix=output_path.stem,
            ),
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self._run(command)

    def _try_concat_copy(self, clip_paths: list[Path], output_path: Path, temp_dir: Path) -> bool:
        """Try a fast concat without re-encoding."""

        try:
            self._concat_copy(clip_paths, output_path, temp_dir)
            return True
        except AppError as exc:
            logger.info("Stream-copy concat failed, normalizing clips: %s", exc)
            remove_file(output_path)
            return False

    def _concat_copy(self, clip_paths: list[Path], output_path: Path, temp_dir: Path) -> None:
        """Concat already-compatible MP4 files using FFmpeg copy mode."""

        concat_file = temp_dir / "concat.txt"
        self._write_concat_file(clip_paths, concat_file)
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self._run(command)

    @staticmethod
    def _write_concat_file(clip_paths: list[Path], concat_file: Path) -> None:
        """Write an FFmpeg concat demuxer list."""

        with concat_file.open("w", encoding="utf-8") as file:
            for path in clip_paths:
                escaped = path.resolve().as_posix().replace("'", "'\\''")
                file.write(f"file '{escaped}'\n")

    @staticmethod
    def probe_video(path: Path) -> VideoSpec:
        """Read video metadata using FFprobe."""

        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,r_frame_rate,codec_name:format=duration",
            "-of",
            "json",
            str(path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise AppError(f"Could not probe {path}: {completed.stderr.strip()}")

        data = json.loads(completed.stdout or "{}")
        streams = data.get("streams") or []
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if not video:
            raise AppError(f"{path} does not contain a video stream.")

        audio = any(stream.get("codec_type") == "audio" for stream in streams)
        duration = None
        with suppress(TypeError, ValueError):
            duration = float((data.get("format") or {}).get("duration"))

        fps = 30.0
        frame_rate = video.get("r_frame_rate")
        if frame_rate and frame_rate != "0/0":
            with suppress(ZeroDivisionError, ValueError):
                fps = float(Fraction(frame_rate))

        width = int(video.get("width") or 1920)
        height = int(video.get("height") or 1080)
        return VideoSpec(
            width=max(2, width),
            height=max(2, height),
            fps=fps if 1 <= fps <= 120 else 30.0,
            duration=duration,
            has_audio=audio,
            video_codec=video.get("codec_name"),
        )

    @staticmethod
    def _target_spec(spec: VideoSpec) -> VideoSpec:
        """Normalize target dimensions to encoder-compatible even values."""

        width = spec.width if spec.width % 2 == 0 else spec.width - 1
        height = spec.height if spec.height % 2 == 0 else spec.height - 1
        return VideoSpec(
            width=max(2, width),
            height=max(2, height),
            fps=spec.fps,
            duration=None,
            has_audio=True,
            video_codec="h264",
        )

    @staticmethod
    def _format_fps(value: float) -> str:
        """Format FPS for FFmpeg command arguments."""

        rounded = round(value)
        if abs(value - rounded) < 0.01:
            return str(rounded)
        return f"{value:.3f}"

    @staticmethod
    def _run(command: list[str]) -> None:
        """Run an FFmpeg command and raise a concise application error."""

        logger.debug("Running command: %s", " ".join(command))
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            details = stderr or stdout or "FFmpeg exited with a non-zero status."
            raise AppError(details[-2500:])

    @staticmethod
    def _align_subtitle_paths(
        clip_paths: list[Path],
        subtitle_paths: list[Path | None] | None,
    ) -> list[Path | None]:
        """Return subtitle paths aligned to clip paths."""

        if not subtitle_paths:
            return [None for _ in clip_paths]
        aligned = list(subtitle_paths[: len(clip_paths)])
        while len(aligned) < len(clip_paths):
            aligned.append(None)
        return aligned
