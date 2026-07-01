"""Subtitle and title-card filter helpers for FFmpeg."""

from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Any


def find_font_file() -> Path | None:
    """Return a common font path for Windows, macOS, or Linux."""

    candidates: list[Path]
    system = platform.system().lower()

    if system == "windows":
        candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/calibri.ttf"),
        ]
    elif system == "darwin":
        candidates = [
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Helvetica.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        ]

    for path in candidates:
        if path.exists():
            return path
    return None


def escape_drawtext_text(text: str) -> str:
    """Escape a string for FFmpeg drawtext."""

    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def escape_font_path(path: Path) -> str:
    """Escape a font path for FFmpeg drawtext."""

    return path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def adaptive_font_size(width: int, height: int, *, title: bool = False) -> int:
    """Choose a readable font size for the output resolution."""

    base = min(width // (10 if title else 18), height // (5 if title else 11))
    minimum = 34 if title else 26
    maximum = 120 if title else 72
    return max(minimum, min(maximum, base))


def drawtext_filter(
    text: str,
    width: int,
    height: int,
    *,
    position: str,
    title: bool = False,
) -> str:
    """Build an FFmpeg drawtext filter for centered or bottom-centered text."""

    escaped_text = escape_drawtext_text(text)
    font_size = adaptive_font_size(width, height, title=title)
    border = max(2, font_size // 14)
    font = find_font_file()
    font_part = f"fontfile='{escape_font_path(font)}':" if font else ""

    if position == "center":
        y_expr = "(h-text_h)/2"
    else:
        y_expr = f"h-text_h-{max(32, height // 14)}"

    return (
        "drawtext="
        f"{font_part}"
        f"text='{escaped_text}':"
        "x=(w-text_w)/2:"
        f"y={y_expr}:"
        f"fontsize={font_size}:"
        "fontcolor=white:"
        "bordercolor=black:"
        f"borderw={border}:"
        "line_spacing=8"
    )


def video_base_filter(width: int, height: int) -> str:
    """Build the standard normalize filter for all clip inputs."""

    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1,"
        "format=yuv420p"
    )


def clip_filter(
    width: int,
    height: int,
    subtitle: str | None,
    subtitle_file: Path | None = None,
) -> str:
    """Build the normalize filter, optionally with ASS karaoke subtitles."""

    filters = [video_base_filter(width, height)]
    if subtitle_file and subtitle_file.exists():
        filters.append(ass_subtitle_filter(subtitle_file))
    elif subtitle:
        filters.append(drawtext_filter(subtitle, width, height, position="bottom"))
    return ",".join(filters)


def title_card_filter(text: str, width: int, height: int) -> str:
    """Build the video filter for an intro or outro title card."""

    return ",".join(
        [
            "format=yuv420p",
            drawtext_filter(text, width, height, position="center", title=True),
        ]
    )


def ass_subtitle_filter(path: Path) -> str:
    """Build an FFmpeg subtitles filter for an ASS subtitle file."""

    escaped = path.resolve().as_posix().replace("\\", "/")
    escaped = (
        escaped.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
    return f"subtitles='{escaped}'"


def write_karaoke_ass(
    path: Path,
    *,
    text: str,
    words: list[Any],
    play_res_x: int = 1920,
    play_res_y: int = 1080,
) -> None:
    """Write an ASS karaoke subtitle file from PlayPhrase word timings."""

    path.parent.mkdir(parents=True, exist_ok=True)
    font_name = (find_font_file().stem if find_font_file() else "Arial").replace(",", "")
    font_size = adaptive_font_size(play_res_x, play_res_y)
    margin_v = max(70, play_res_y // 13)
    dialogue = build_karaoke_dialogue(text=text, words=words)
    end_time = ass_time(max(extract_end_ms(words), 1500) / 1000)

    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                f"Style: Default,{font_name},{font_size},&H0031D1FD,&H00FFFFFF,"
                "&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,4,0,2,"
                f"60,60,{margin_v},1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            f"Dialogue: 0,0:00:00.00,{end_time},Default,,0,0,0,,{dialogue}",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")


def write_cued_ass(
    path: Path,
    *,
    cues: list[Any],
    fallback_text: str,
    highlight_text: str | None = None,
    play_res_x: int = 1920,
    play_res_y: int = 1080,
) -> None:
    """Write timed line subtitles, highlighting the searched text when present."""

    normalized_cues = normalize_cue_items(cues)
    if not normalized_cues:
        write_karaoke_ass(
            path,
            text=fallback_text,
            words=[],
            play_res_x=play_res_x,
            play_res_y=play_res_y,
        )
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    font_name = (find_font_file().stem if find_font_file() else "Arial").replace(",", "")
    font_size = adaptive_font_size(play_res_x, play_res_y)
    margin_v = max(70, play_res_y // 13)
    events = []
    for cue in normalized_cues:
        dialogue = build_highlighted_dialogue(cue["text"], highlight_text=highlight_text)
        events.append(
            f"Dialogue: 0,{ass_time(cue['start'] / 1000)},{ass_time(cue['end'] / 1000)},"
            f"Default,,0,0,0,,{dialogue}"
        )

    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H0031D1FD,"
                "&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,4,0,2,"
                f"60,60,{margin_v},1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")


def write_plain_text_subtitle(path: Path, text: str) -> None:
    """Write a plain sidecar subtitle text file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{text.strip()}\n", encoding="utf-8")


def build_karaoke_dialogue(*, text: str, words: list[Any]) -> str:
    """Return ASS karaoke override text."""

    normalized_words = normalize_word_items(words)
    if not normalized_words:
        return ass_escape_text(text)

    pieces: list[str] = []
    for index, word in enumerate(normalized_words):
        start = word["start"]
        next_start = (
            normalized_words[index + 1]["start"]
            if index + 1 < len(normalized_words)
            else word["end"]
        )
        duration_ms = max(80, next_start - start)
        centiseconds = max(1, round(duration_ms / 10))
        suffix = " " if index + 1 < len(normalized_words) else ""
        pieces.append(f"{{\\k{centiseconds}}}{ass_escape_text(word['text'])}{suffix}")
    return "".join(pieces)


def normalize_word_items(words: list[Any]) -> list[dict[str, Any]]:
    """Convert Pydantic models or dicts into sorted word timing dictionaries."""

    normalized: list[dict[str, Any]] = []
    for item in words:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        start = item.get("start")
        end = item.get("end")
        if not isinstance(text, str) or not isinstance(start, int | float) or not isinstance(end, int | float):
            continue
        if end <= start:
            end = start + 120
        normalized.append({"text": text, "start": int(start), "end": int(end)})
    return sorted(normalized, key=lambda word: word["start"])


def normalize_cue_items(cues: list[Any]) -> list[dict[str, Any]]:
    """Convert Pydantic models or dicts into sorted subtitle cue dictionaries."""

    normalized: list[dict[str, Any]] = []
    for item in cues:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        start = item.get("start")
        end = item.get("end")
        if not isinstance(text, str) or not isinstance(start, int | float) or not isinstance(end, int | float):
            continue
        text = text.strip()
        if not text:
            continue
        if end <= start:
            end = start + 1000
        normalized.append({"text": text, "start": int(start), "end": int(end)})
    return sorted(normalized, key=lambda cue: cue["start"])


def build_even_karaoke_dialogue(text: str, duration_ms: int) -> str:
    """Build approximate word-level karaoke for a line without per-word timings."""

    words = [word for word in text.split() if word]
    if not words:
        return ass_escape_text(text)

    duration_cs = max(len(words), round(max(300, duration_ms) / 10))
    base = max(1, duration_cs // len(words))
    remainder = max(0, duration_cs - (base * len(words)))

    pieces: list[str] = []
    for index, word in enumerate(words):
        centiseconds = base + (1 if index < remainder else 0)
        suffix = " " if index + 1 < len(words) else ""
        pieces.append(f"{{\\k{centiseconds}}}{ass_escape_text(word)}{suffix}")
    return "".join(pieces)


def build_highlighted_dialogue(
    text: str,
    *,
    highlight_text: str | None = None,
    max_chars: int = 42,
) -> str:
    """Build non-karaoke ASS text with wrapping and searched-text highlighting."""

    return r"\N".join(
        highlight_ass_text(line, highlight_text=highlight_text)
        for line in wrap_subtitle_text(text, max_chars=max_chars)
    )


def wrap_subtitle_text(text: str, *, max_chars: int = 42) -> list[str]:
    """Wrap subtitle text to reduce the chance of overflowing the video frame."""

    normalized = " ".join(text.split())
    if not normalized:
        return [""]

    lines: list[str] = []
    current = ""

    for word in normalized.split():
        for chunk in split_long_word(word, max_chars):
            candidate = chunk if not current else f"{current} {chunk}"
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = chunk

    if current:
        lines.append(current)

    return lines


def split_long_word(word: str, max_chars: int) -> list[str]:
    """Split a very long token so it cannot force one huge subtitle line."""

    if len(word) <= max_chars:
        return [word]
    return [word[index : index + max_chars] for index in range(0, len(word), max_chars)]


def highlight_ass_text(text: str, *, highlight_text: str | None = None) -> str:
    """Escape ASS text and color the searched phrase yellow."""

    query = " ".join((highlight_text or "").split()).strip()
    if not query:
        return ass_escape_text(text)

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    parts: list[str] = []
    last = 0

    for match in pattern.finditer(text):
        if match.start() > last:
            parts.append(ass_escape_text(text[last : match.start()]))
        parts.append(r"{\c&H0031D1FD&}")
        parts.append(ass_escape_text(match.group(0)))
        parts.append(r"{\c&H00FFFFFF&}")
        last = match.end()

    if last < len(text):
        parts.append(ass_escape_text(text[last:]))

    return "".join(parts) if parts else ass_escape_text(text)


def extract_end_ms(words: list[Any]) -> int:
    """Return the maximum word end offset in milliseconds."""

    normalized = normalize_word_items(words)
    if not normalized:
        return 0
    return max(word["end"] for word in normalized)


def ass_escape_text(text: str) -> str:
    """Escape text for ASS subtitle events."""

    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
        .strip()
    )


def ass_time(seconds: float) -> str:
    """Format seconds as an ASS timestamp."""

    total_centiseconds = max(0, round(seconds * 100))
    centiseconds = total_centiseconds % 100
    total_seconds = total_centiseconds // 100
    secs = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"
