"""Creative video remixing for short-form social outputs."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.progress import Progress, TextColumn

from src.config import Settings
from src.flags import ensure_flag_assets, flag_asset_path
from src.subtitle import (
    escape_font_path,
    find_font_file,
    font_script_for_language,
    translation_line_parts,
    wrap_subtitle_text,
)
from src.translations import PhraseTranslations
from src.utils import AppError, console, ensure_directories, require_executable

logger = logging.getLogger(__name__)

REEL_WIDTH = 1080
REEL_HEIGHT = 1920
REEL_FPS = 30
BROLL_QUERY_GROUPS = {
    "romantic": [
        "couple walking",
        "holding hands walking",
        "people walking sunset",
        "couple beach walking",
        "city park walking",
    ],
    "greeting": [
        "friends greeting",
        "people waving",
        "people smiling street",
        "friends walking city",
        "train station people",
    ],
    "sad": [
        "person walking city",
        "rain street walking",
        "night city street",
        "person looking window",
        "empty street walking",
    ],
    "travel": [
        "city street walking",
        "street market people",
        "train station people",
        "airport walking",
        "people crossing street",
    ],
    "learning": [
        "student studying",
        "library walking",
        "writing notebook",
        "people reading park",
        "classroom students",
    ],
    "generic": [
        "city street walking",
        "friends walking city",
        "street market people",
        "people crossing street",
        "park walking",
        "cafe street",
        "train station people",
        "people smiling street",
    ],
}


class VideoEnhancer:
    """Render a more dynamic vertical Reel/Shorts version of a final video."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_reel(
        self,
        *,
        input_path: Path,
        phrase: str,
        output_path: Path,
        broll_path: Path | None = None,
        broll_credit: str | None = None,
        translations: PhraseTranslations | None = None,
    ) -> Path:
        """Create a vertical short-form edit from an existing final MP4."""

        require_executable("ffmpeg")
        if not input_path.is_file():
            raise AppError(f"Input video not found: {input_path}")

        ensure_directories(output_path.parent, self.settings.temp_folder)
        with TemporaryDirectory(prefix="enhance-", dir=self.settings.temp_folder) as temp_name:
            temp_dir = Path(temp_name)
            rendered: list[Path] = []

            progress = Progress(
                TextColumn("[bold green]{task.description}"),
                console=console,
                transient=False,
            )
            with progress:
                if broll_path and broll_path.is_file():
                    opener = temp_dir / "000-broll-opener.mp4"
                    task_id = progress.add_task("Rendering b-roll hook", total=None)
                    self._render_broll_hook(
                        broll_path=broll_path,
                        phrase=phrase,
                        output_path=opener,
                        temp_dir=temp_dir,
                        credit=broll_credit,
                        translations=translations,
                    )
                    progress.update(task_id, completed=1, total=1)
                    rendered.append(opener)

                main = temp_dir / "001-reel-main.mp4"
                task_id = progress.add_task("Rendering vertical reel", total=None)
                self._render_vertical_main(
                    input_path=input_path,
                    phrase=phrase,
                    output_path=main,
                    temp_dir=temp_dir,
                )
                progress.update(task_id, completed=1, total=1)
                rendered.append(main)

            final_temp = temp_dir / "final-reel.mp4"
            if len(rendered) == 1:
                rendered[0].replace(final_temp)
            else:
                self._concat(rendered, final_temp, temp_dir)
            final_temp.replace(output_path)

        logger.info("Enhanced reel video at %s", output_path)
        return output_path

    def _render_vertical_main(
        self,
        *,
        input_path: Path,
        phrase: str,
        output_path: Path,
        temp_dir: Path,
    ) -> None:
        """Render the main video into a polished 9:16 layout."""

        progress_duration = 60.0
        filters = [
            "[0:v]split=2[base][front]",
            (
                f"[base]scale={REEL_WIDTH}:{REEL_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={REEL_WIDTH}:{REEL_HEIGHT},boxblur=30:1,"
                "eq=brightness=-0.12:saturation=0.85[bg]"
            ),
            (
                "[front]scale=1000:-2:force_original_aspect_ratio=decrease,"
                "setsar=1[fg]"
            ),
            (
                "[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,"
                "drawbox=x=0:y=0:w=iw:h=330:color=black@0.28:t=fill,"
                "drawbox=x=0:y=1600:w=iw:h=320:color=black@0.18:t=fill,"
                "drawbox=x=72:y=1828:w=936:h=10:color=white@0.22:t=fill,"
                f"drawbox=x=72:y=1828:w=936*t/{progress_duration:.3f}:h=10:"
                "color=0xFDD131@0.95:t=fill"
            ),
        ]
        filters.extend(self._headline_filters(phrase, temp_dir, prefix="main"))
        filters.append("format=yuv420p[v]")
        filter_complex = ",".join(filters)

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(input_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-r",
            str(REEL_FPS),
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
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self._run(command)

    def _render_broll_hook(
        self,
        *,
        broll_path: Path,
        phrase: str,
        output_path: Path,
        temp_dir: Path,
        credit: str | None,
        translations: PhraseTranslations | None,
    ) -> None:
        """Render a short b-roll hook before the dialogue montage."""

        translation_lines = translations.display_lines() if translations else []
        flag_dir = ensure_flag_assets(self.settings.assets_folder) if translation_lines else None
        filters = [
            "[0:v]split=2[base][front]",
            (
                f"[base]scale={REEL_WIDTH}:{REEL_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={REEL_WIDTH}:{REEL_HEIGHT},boxblur=22:1,"
                "eq=brightness=-0.18:saturation=0.82[bg]"
            ),
            (
                "[front]scale=1000:1180:force_original_aspect_ratio=decrease,"
                f"fps={REEL_FPS},setsar=1[fg]"
            ),
            (
                "[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,"
                "drawbox=x=0:y=0:w=iw:h=380:color=black@0.32:t=fill,"
                "drawbox=x=0:y=1470:w=iw:h=450:color=black@0.26:t=fill[hookbase]"
            ),
        ]
        text_filters, text_output = self._hook_text_filters(
            phrase,
            temp_dir,
            credit=credit,
            translation_lines=translation_lines,
            input_label="hookbase",
            flag_dir=flag_dir,
        )
        filters.extend(text_filters)
        filters.append(f"[{text_output}]format=yuv420p[v]")

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-stream_loop",
            "-1",
            "-t",
            "2.40",
            "-i",
            str(broll_path),
            "-f",
            "lavfi",
            "-t",
            "2.40",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            "-r",
            str(REEL_FPS),
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

    def _headline_filters(self, phrase: str, temp_dir: Path, *, prefix: str) -> list[str]:
        """Return drawtext filters for the main vertical edit."""

        filters = [
            self._drawtext(
                "LISTEN FOR",
                temp_dir / f"{prefix}-eyebrow.txt",
                y="74",
                font_size=34,
                color="0xFDD131",
                border=2,
            )
        ]

        lines = wrap_subtitle_text(phrase, max_chars=20)[:3]
        line_height = 70
        start_y = 128
        for index, line in enumerate(lines):
            filters.append(
                self._drawtext(
                    line,
                    temp_dir / f"{prefix}-phrase-{index}.txt",
                    y=str(start_y + index * line_height),
                    font_size=58,
                    color="white",
                    border=4,
                )
            )

        filters.append(
            self._drawtext(
                "Listen -> Notice -> Repeat",
                temp_dir / f"{prefix}-footer.txt",
                y="1754",
                font_size=34,
                color="white",
                border=2,
            )
        )
        return filters

    def _hook_text_filters(
        self,
        phrase: str,
        temp_dir: Path,
        *,
        credit: str | None,
        translation_lines: list[str] | None = None,
        input_label: str = "hookbase",
        flag_dir: Path | None = None,
    ) -> tuple[list[str], str]:
        """Return drawtext filters for the b-roll opener."""

        translation_lines = [line for line in (translation_lines or []) if line.strip()][:6]
        panel_y = 260
        lines = wrap_subtitle_text(phrase, max_chars=16)[:3]
        start_y = 430
        row_step = 64 if len(translation_lines) > 3 else 66
        translation_start_y = start_y + len(lines) * 78 + 40
        promise_y = (
            str(translation_start_y + len(translation_lines) * row_step + 62)
            if translation_lines
            else "850"
        )
        panel_h = max(560, int(promise_y) + 80 - panel_y)
        panel_h = min(panel_h, 1120)
        filters: list[str] = []
        current_label = input_label
        step = 0

        def add_filter(filter_body: str) -> None:
            nonlocal current_label, step
            next_label = f"hooktext{step}"
            step += 1
            filters.append(f"[{current_label}]{filter_body}[{next_label}]")
            current_label = next_label

        add_filter(
            (
                f"drawbox=x=58:y={panel_y}:w={REEL_WIDTH - 116}:h={panel_h}:"
                "color=black@0.66:t=fill"
            )
        )
        add_filter(
            (
                f"drawbox=x=58:y={panel_y}:w={REEL_WIDTH - 116}:h={panel_h}:"
                "color=0xFDD131@0.88:t=4"
            )
        )
        add_filter(
            self._drawtext(
                "Daily English",
                temp_dir / "hook-brand.txt",
                y="318",
                font_size=42,
                color="white",
                border=3,
            )
        )
        for index, line in enumerate(lines):
            add_filter(
                self._drawtext(
                    line,
                    temp_dir / f"hook-phrase-{index}.txt",
                    y=str(start_y + index * 78),
                    font_size=66,
                    color="0xFDD131",
                    border=7,
                )
            )

        if translation_lines:
            for index, line in enumerate(translation_lines):
                flag_key, flag_text, translation_text = translation_line_parts(line)
                row_y = translation_start_y + index * row_step
                flag_x = 120
                flag_w = 54
                flag_h = 36
                flag_path = flag_asset_path(flag_dir, flag_key) if flag_dir else None
                flag_record = temp_dir / f"hook-flag-{index}.txt"
                if flag_path and flag_path.is_file():
                    flag_record.write_text(flag_path.name, encoding="utf-8")
                    flag_label = f"hookflag{index}"
                    filters.append(
                        f"movie='{escape_font_path(flag_path)}',"
                        f"scale={flag_w}:{flag_h}:flags=lanczos[{flag_label}]"
                    )
                    next_label = f"hooktext{step}"
                    step += 1
                    filters.append(
                        f"[{current_label}][{flag_label}]"
                        f"overlay={flag_x}:{row_y - 4}:format=auto[{next_label}]"
                    )
                    current_label = next_label
                else:
                    add_filter(
                        self._drawtext(
                            flag_text,
                            flag_record,
                            y=str(row_y - 4),
                            font_size=42,
                            color="white",
                            border=0,
                            emoji=True,
                            x_expr=str(flag_x),
                        )
                    )
                add_filter(
                    self._drawtext(
                        translation_text,
                        temp_dir / f"hook-translation-{index}.txt",
                        y=str(row_y),
                        font_size=34 if len(translation_lines) > 3 else 36,
                        color="0xEAF2FF",
                        border=3,
                        script=font_script_for_language(flag_key),
                        x_expr=str(flag_x + flag_w + 22),
                    )
                )

        add_filter(
            self._drawtext(
                "Hear it in real scenes",
                temp_dir / "hook-promise.txt",
                y=promise_y,
                font_size=38,
                color="white",
                border=4,
            )
        )
        if credit:
            add_filter(
                self._drawtext(
                    "B-roll: Wikimedia Commons",
                    temp_dir / "hook-credit.txt",
                    y="1810",
                    font_size=24,
                    color="white@0.82",
                    border=1,
                )
            )
        return filters, current_label

    @staticmethod
    def _drawtext(
        text: str,
        text_file: Path,
        *,
        y: str,
        font_size: int,
        color: str,
        border: int,
        multilingual: bool = False,
        x_expr: str | None = None,
        emoji: bool = False,
        script: str | None = None,
    ) -> str:
        """Build a centered drawtext filter using a text file."""

        text_file.write_text(text, encoding="utf-8")
        font = find_font_file(multilingual=multilingual, emoji=emoji, script=script)
        font_part = f"fontfile='{escape_font_path(font)}':" if font else ""
        return (
            "drawtext="
            f"{font_part}"
            f"textfile='{escape_font_path(text_file)}':"
            f"x={x_expr or '(w-text_w)/2'}:"
            f"y={y}:"
            f"fontsize={font_size}:"
            f"fontcolor={color}:"
            "bordercolor=black:"
            f"borderw={border}"
        )

    @staticmethod
    def _concat(paths: list[Path], output_path: Path, temp_dir: Path) -> None:
        """Concat already-normalized MP4 files."""

        concat_file = temp_dir / "concat.txt"
        with concat_file.open("w", encoding="utf-8") as file:
            for path in paths:
                escaped = path.resolve().as_posix().replace("'", "'\\''")
                file.write(f"file '{escaped}'\n")

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
        VideoEnhancer._run(command)

    @staticmethod
    def _run(command: list[str]) -> None:
        """Run FFmpeg and raise a compact user-facing error."""

        logger.debug("Running command: %s", " ".join(command))
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            details = stderr or stdout or "FFmpeg exited with a non-zero status."
            raise AppError(details[-2500:])


def default_broll_query(phrase: str) -> str:
    """Return a broad visual b-roll query for a phrase."""

    return default_broll_queries(phrase)[0]


def default_broll_queries(phrase: str) -> list[str]:
    """Return varied b-roll search queries for a phrase."""

    lowered = phrase.lower()
    if any(word in lowered for word in ("love", "miss", "falling", "meet", "heart")):
        key = "romantic"
    elif any(word in lowered for word in ("hello", "hi", "nice to meet", "how are you")):
        key = "greeting"
    elif any(word in lowered for word in ("alone", "sad", "sorry", "miss you")):
        key = "sad"
    elif any(word in lowered for word in ("go", "come", "leave", "arrive", "where", "around")):
        key = "travel"
    elif any(word in lowered for word in ("learn", "study", "practice", "repeat", "listen")):
        key = "learning"
    else:
        key = "generic"

    primary = rotated_broll_queries(BROLL_QUERY_GROUPS[key], phrase)
    fallback = rotated_broll_queries(BROLL_QUERY_GROUPS["generic"], phrase)
    return unique_queries([*primary, *fallback])


def rotated_broll_queries(queries: list[str], phrase: str) -> list[str]:
    """Rotate query order deterministically so phrases do not all use one scene type."""

    if not queries:
        return []
    offset = sum((index + 1) * ord(char) for index, char in enumerate(phrase.lower()))
    offset %= len(queries)
    return [*queries[offset:], *queries[:offset]]


def unique_queries(queries: list[str]) -> list[str]:
    """Return non-empty query strings without duplicates."""

    unique: list[str] = []
    for query in queries:
        normalized = " ".join(query.split()).strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique
