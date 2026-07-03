"""Subtitle and title-card filter helpers for FFmpeg."""

from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Any

from src.flags import flag_asset_path

CONTRACTION_EXPANSIONS = {
    "can't": ["can", "not"],
    "cannot": ["can", "not"],
    "won't": ["will", "not"],
    "shan't": ["shall", "not"],
    "let's": ["let", "us"],
    "y'all": ["you", "all"],
}

CONTRACTION_SUFFIX_EXPANSIONS = {
    "'m": [["am"]],
    "'re": [["are"]],
    "'ve": [["have"]],
    "'ll": [["will"]],
    "'d": [["would"], ["had"], ["did"]],
    "'s": [["is"], ["has"]],
}
NEGATIVE_CONTRACTION_BASES = {
    "ain": ["is"],
    "ca": ["can"],
    "wo": ["will"],
    "sha": ["shall"],
}
MAX_QUERY_EXPANSION_VARIANTS = 32
TRANSLATION_FLAG_KEYS = {
    "🇨🇳": "zh",
    "🇯🇵": "ja",
    "🇻🇳": "vi",
    "🇰🇷": "ko",
    "🇪🇸": "es",
    "🇮🇳": "hi",
    "🇸🇦": "ar",
}


def find_font_file(
    *,
    multilingual: bool = False,
    emoji: bool = False,
    script: str | None = None,
) -> Path | None:
    """Return a common font path for Windows, macOS, or Linux."""

    candidates: list[Path]
    system = platform.system().lower()

    if system == "windows":
        base_candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/calibri.ttf"),
        ]
        multilingual_candidates = [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/meiryo.ttc"),
            Path("C:/Windows/Fonts/YuGothM.ttc"),
            Path("C:/Windows/Fonts/msgothic.ttc"),
            Path("C:/Windows/Fonts/simsun.ttc"),
        ]
        korean_candidates = [
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/malgunbd.ttf"),
            Path("C:/Windows/Fonts/malgunsl.ttf"),
        ]
        devanagari_candidates = [
            Path("C:/Windows/Fonts/Nirmala.ttc"),
            Path("C:/Windows/Fonts/Nirmala.ttf"),
            Path("C:/Windows/Fonts/NirmalaB.ttf"),
            Path("C:/Windows/Fonts/mangal.ttf"),
        ]
        arabic_candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/tahoma.ttf"),
            Path("C:/Windows/Fonts/arabtype.ttf"),
            Path("C:/Windows/Fonts/majalla.ttf"),
            Path("C:/Windows/Fonts/trado.ttf"),
        ]
        emoji_candidates = [
            Path("C:/Windows/Fonts/seguiemj.ttf"),
            Path("C:/Windows/Fonts/seguisym.ttf"),
        ]
    elif system == "darwin":
        base_candidates = [
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Helvetica.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
        ]
        multilingual_candidates = [
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        ]
        korean_candidates = [
            Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
            Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
        ]
        devanagari_candidates = [
            Path("/System/Library/Fonts/Devanagari Sangam MN.ttc"),
            Path("/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"),
            Path("/System/Library/Fonts/Kohinoor.ttc"),
        ]
        arabic_candidates = [
            Path("/System/Library/Fonts/GeezaPro.ttc"),
            Path("/System/Library/Fonts/Supplemental/Geeza Pro.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        ]
        emoji_candidates = [
            Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
            Path("/System/Library/Fonts/Supplemental/Apple Color Emoji.ttc"),
        ]
    else:
        base_candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        ]
        multilingual_candidates = [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
        ]
        korean_candidates = [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        ]
        devanagari_candidates = [
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
            Path("/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"),
        ]
        arabic_candidates = [
            Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        emoji_candidates = [
            Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoColorEmoji.ttf"),
        ]

    if script == "devanagari":
        candidates = [*devanagari_candidates, *base_candidates, *multilingual_candidates]
    elif script == "arabic":
        candidates = [*arabic_candidates, *base_candidates, *multilingual_candidates]
    elif script == "korean":
        candidates = [*korean_candidates, *multilingual_candidates, *base_candidates]
    elif script == "cjk":
        candidates = [*multilingual_candidates, *base_candidates]
    elif emoji:
        candidates = [*emoji_candidates, *base_candidates, *multilingual_candidates]
    elif multilingual:
        candidates = [*multilingual_candidates, *base_candidates]
    else:
        candidates = [*base_candidates, *multilingual_candidates]

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


def max_chars_for_font(
    width: int,
    font_size: int,
    *,
    max_width_ratio: float = 0.86,
    average_char_ratio: float = 0.58,
    minimum: int = 12,
    maximum: int = 48,
) -> int:
    """Estimate how many subtitle characters can fit safely on one line."""

    available_width = max(1, int(width * max_width_ratio))
    estimated = int(available_width / max(1, font_size * average_char_ratio))
    return max(minimum, min(maximum, estimated))


def subtitle_max_chars(width: int, height: int) -> int:
    """Return a conservative subtitle line length for the output resolution."""

    font_size = adaptive_font_size(width, height)
    return max_chars_for_font(width, font_size, minimum=18, maximum=42)


def title_lines_and_font_size(text: str, width: int, height: int) -> tuple[list[str], int]:
    """Choose wrapped title-card lines and a font size that fit the frame."""

    max_font_size = min(168, int(adaptive_font_size(width, height, title=True) * 1.16))
    min_font_size = max(34, min(width, height) // 18)

    for font_size in range(max_font_size, min_font_size - 1, -2):
        max_chars = max_chars_for_font(
            width,
            font_size,
            max_width_ratio=0.78,
            average_char_ratio=0.62,
            minimum=8,
            maximum=28,
        )
        lines = wrap_subtitle_text(text, max_chars=max_chars)
        line_spacing = max(8, font_size // 6)
        block_height = (len(lines) * font_size) + max(0, len(lines) - 1) * line_spacing
        if len(lines) <= 4 and block_height <= height * 0.62:
            return lines, font_size

    fallback_font = min_font_size
    fallback_chars = max_chars_for_font(
        width,
        fallback_font,
        max_width_ratio=0.72,
        average_char_ratio=0.62,
        minimum=8,
        maximum=24,
    )
    return wrap_subtitle_text(text, max_chars=fallback_chars), fallback_font


def drawtext_filter(
    text: str,
    width: int,
    height: int,
    *,
    position: str,
    title: bool = False,
    font_size: int | None = None,
    y_expr: str | None = None,
    line_spacing: int = 8,
    text_file: Path | None = None,
    color: str = "white",
    multilingual: bool = False,
    x_expr: str | None = None,
    emoji: bool = False,
    script: str | None = None,
) -> str:
    """Build an FFmpeg drawtext filter for centered or bottom-centered text."""

    escaped_text = escape_drawtext_text(text)
    resolved_font_size = font_size or adaptive_font_size(width, height, title=title)
    border = max(2, resolved_font_size // 14)
    font = find_font_file(multilingual=multilingual, emoji=emoji, script=script)
    font_part = f"fontfile='{escape_font_path(font)}':" if font else ""
    text_part = (
        f"textfile='{escape_font_path(text_file)}':"
        if text_file
        else f"text={escaped_text}:"
    )

    if y_expr is not None:
        resolved_y_expr = y_expr
    elif position == "center":
        resolved_y_expr = "(h-text_h)/2"
    else:
        resolved_y_expr = f"h-text_h-{max(32, height // 14)}"
    resolved_x_expr = x_expr or "(w-text_w)/2"

    return (
        "drawtext="
        f"{font_part}"
        f"{text_part}"
        f"x={resolved_x_expr}:"
        f"y={resolved_y_expr}:"
        f"fontsize={resolved_font_size}:"
        f"fontcolor={color}:"
        "bordercolor=black:"
        f"borderw={border}:"
        f"line_spacing={line_spacing}"
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


def title_card_filter(
    text: str,
    width: int,
    height: int,
    *,
    text_dir: Path | None = None,
    file_prefix: str = "title",
    translation_lines: list[str] | None = None,
    flag_dir: Path | None = None,
    output_label: str | None = None,
) -> str:
    """Build the video filter for an intro or outro title card."""

    lines, font_size = title_lines_and_font_size(text, width, height)
    line_spacing = max(8, font_size // 6)
    block_height = (len(lines) * font_size) + max(0, len(lines) - 1) * line_spacing
    line_step = font_size + line_spacing
    translation_lines = [line for line in (translation_lines or []) if line.strip()][:7]
    translation_rows = [translation_line_parts(line) for line in translation_lines]

    filters = [
        "format=yuv420p",
        f"drawbox=x=0:y=0:w={width}:h={height}:color=0x101820@1:t=fill",
        f"drawbox=x=0:y=0:w={width}:h={max(90, height // 5)}:color=0x1F2A44@0.72:t=fill",
        f"drawbox=x=0:y={height - max(110, height // 5)}:w={width}:h={max(110, height // 5)}:color=0x0B1320@0.82:t=fill",
        (
            f"drawbox=x={max(36, width // 18)}:y={max(36, height // 18)}:"
            f"w={max(140, width // 5)}:h={max(5, height // 160)}:"
            "color=0xFDD131@0.95:t=fill"
        ),
    ]

    brand_file = None
    if text_dir:
        brand_file = text_dir / f"{file_prefix}-brand.txt"
        brand_file.write_text("Daily English", encoding="utf-8")
    filters.append(
        drawtext_filter(
            "Daily English",
            width,
            height,
            position="center",
            title=False,
            font_size=max(24, min(42, height // 22)),
            y_expr=str(max(48, height // 13)),
            text_file=brand_file,
            color="0xFDD131",
        )
    )

    has_dense_translations = len(translation_rows) > 4 and width >= 960
    title_top = max(height // 3 - block_height // 2, height // 7 if has_dense_translations else height // 5)
    for index, line in enumerate(lines):
        y_expr = str(title_top + index * line_step)
        text_file = None
        if text_dir:
            text_file = text_dir / f"{file_prefix}-{index:02d}.txt"
            text_file.write_text(line, encoding="utf-8")
        filters.append(
            drawtext_filter(
                line,
                width,
                height,
                position="center",
                title=True,
                font_size=font_size,
                y_expr=y_expr,
                line_spacing=line_spacing,
                text_file=text_file,
                multilingual=False,
                color="0xFDD131",
            )
        )

    if translation_lines:
        translation_columns = 2 if len(translation_rows) > 4 and width >= 960 else 1
        rows_per_column = (len(translation_rows) + translation_columns - 1) // translation_columns
        translation_font = max(20, min(32 if len(translation_rows) > 4 else 38, height // 28))
        row_gap = max(16 if len(translation_rows) > 3 else 12, height // 45)
        translation_gap = translation_font + row_gap
        translation_block = rows_per_column * translation_font + max(0, rows_per_column - 1) * row_gap
        translation_top = min(
            height - max(80, height // 10) - translation_block,
            title_top + block_height + max(34, height // 18),
        )
        panel_y = max(0, translation_top - max(20, height // 45))
        panel_h = min(height - panel_y, translation_block + max(48, height // 14))
        filters.append(
            f"drawbox=x={max(32, width // 20)}:y={panel_y}:"
            f"w={width - max(64, width // 10)}:h={panel_h}:"
            "color=0xFFFFFF@0.09:t=fill"
        )

        if flag_dir:
            return title_card_complex_filter(
                filters,
                translation_rows=translation_rows,
                width=width,
                height=height,
                translation_top=translation_top,
                translation_gap=translation_gap,
                translation_font=translation_font,
                translation_columns=translation_columns,
                text_dir=text_dir,
                file_prefix=file_prefix,
                flag_dir=flag_dir,
                output_label=output_label or "v",
            )

        flag_w = max(34, min(58, width // 22))
        flag_x = max(52, width // 12)
        content_width = width - (flag_x * 2)
        column_width = content_width // translation_columns
        for index, (flag_key, flag_text, translation_text) in enumerate(translation_rows):
            column = index // rows_per_column
            row = index % rows_per_column
            row_flag_x = flag_x + column * column_width
            text_file = None
            flag_file = None
            if text_dir:
                text_file = text_dir / f"{file_prefix}-translation-{index}.txt"
                text_file.write_text(translation_text, encoding="utf-8")
                flag_file = text_dir / f"{file_prefix}-flag-{index}.txt"
                flag_file.write_text(flag_text, encoding="utf-8")
            row_y = translation_top + row * translation_gap
            filters.append(
                drawtext_filter(
                    flag_text,
                    width,
                    height,
                    position="center",
                    title=False,
                    font_size=max(translation_font + 3, 26),
                    y_expr=str(row_y - 3),
                    text_file=flag_file,
                    color="white",
                    x_expr=str(row_flag_x),
                    emoji=True,
                )
            )
            filters.append(
                drawtext_filter(
                    translation_text,
                    width,
                    height,
                    position="center",
                    title=False,
                    font_size=translation_font,
                    y_expr=str(row_y),
                    text_file=text_file,
                    color="0xEAF2FF",
                    script=font_script_for_language(flag_key),
                    x_expr=str(row_flag_x + flag_w + max(14, width // 90)),
                )
            )
    return ",".join(filters)


def title_card_complex_filter(
    base_filters: list[str],
    *,
    translation_rows: list[tuple[str, str, str]],
    width: int,
    height: int,
    translation_top: int,
    translation_gap: int,
    translation_font: int,
    translation_columns: int,
    text_dir: Path | None,
    file_prefix: str,
    flag_dir: Path,
    output_label: str,
) -> str:
    """Build a labelled filter graph for title cards that overlay PNG flag assets."""

    chains: list[str] = [f"[0:v]{','.join(base_filters)}[titlebase0]"]
    current_label = "titlebase0"
    step = 1
    flag_w = max(34, min(58, width // 22))
    flag_h = max(22, round(flag_w * 2 / 3))
    flag_x = max(52, width // 12)
    rows_per_column = (len(translation_rows) + translation_columns - 1) // translation_columns
    content_width = width - (flag_x * 2)
    column_width = content_width // translation_columns

    def add_filter(filter_body: str) -> None:
        nonlocal current_label, step
        next_label = f"titlebase{step}"
        step += 1
        chains.append(f"[{current_label}]{filter_body}[{next_label}]")
        current_label = next_label

    for index, (flag_key, flag_text, translation_text) in enumerate(translation_rows):
        column = index // rows_per_column
        row = index % rows_per_column
        row_flag_x = flag_x + column * column_width
        text_file = None
        if text_dir:
            text_file = text_dir / f"{file_prefix}-translation-{index}.txt"
            text_file.write_text(translation_text, encoding="utf-8")
            flag_record = text_dir / f"{file_prefix}-flag-{index}.txt"
            flag_record.write_text(flag_asset_path(flag_dir, flag_key).name, encoding="utf-8")

        row_y = translation_top + row * translation_gap
        flag_path = flag_asset_path(flag_dir, flag_key)
        if flag_path.is_file():
            flag_label = f"titleflag{index}"
            chains.append(
                f"movie='{escape_font_path(flag_path)}',"
                f"scale={flag_w}:{flag_h}:flags=lanczos[{flag_label}]"
            )
            next_label = f"titlebase{step}"
            step += 1
            flag_y = max(0, row_y - max(0, (flag_h - translation_font) // 2) - 2)
            chains.append(
                f"[{current_label}][{flag_label}]"
                f"overlay={row_flag_x}:{flag_y}:format=auto[{next_label}]"
            )
            current_label = next_label
        else:
            flag_file = None
            if text_dir:
                flag_file = text_dir / f"{file_prefix}-flag-{index}.txt"
                flag_file.write_text(flag_text, encoding="utf-8")
            add_filter(
                drawtext_filter(
                    flag_text,
                    width,
                    height,
                    position="center",
                    title=False,
                    font_size=max(translation_font + 3, 26),
                    y_expr=str(row_y - 3),
                    text_file=flag_file,
                    color="white",
                    x_expr=str(row_flag_x),
                    emoji=True,
                )
            )

        add_filter(
            drawtext_filter(
                translation_text,
                width,
                height,
                position="center",
                title=False,
                font_size=translation_font,
                y_expr=str(row_y),
                text_file=text_file,
                color="0xEAF2FF",
                script=font_script_for_language(flag_key),
                x_expr=str(row_flag_x + flag_w + max(14, width // 90)),
            )
        )

    chains.append(f"[{current_label}]format=yuv420p[{output_label}]")
    return ";".join(chains)


def translation_line_parts(line: str) -> tuple[str, str, str]:
    """Return flag key, flag emoji, and translation text for a display line."""

    stripped = line.strip()
    for flag, key in TRANSLATION_FLAG_KEYS.items():
        if stripped.startswith(flag):
            return key, flag, stripped.removeprefix(flag).strip()
    return "generic", "🏳️", stripped


def translation_flag_key(line: str) -> str:
    """Return the flag style key for a display line."""

    return translation_line_parts(line)[0]


def font_script_for_language(language_key: str) -> str | None:
    """Return the preferred font script group for a translation language key."""

    if language_key in {"zh", "ja"}:
        return "cjk"
    if language_key == "ko":
        return "korean"
    if language_key == "hi":
        return "devanagari"
    if language_key == "ar":
        return "arabic"
    return None


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
    max_chars = subtitle_max_chars(play_res_x, play_res_y)
    dialogue = build_karaoke_dialogue(text=text, words=words, max_chars=max_chars)
    end_time = ass_time(max(extract_end_ms(words), 1500) / 1000)

    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
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
                f"90,90,{margin_v},1"
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
    max_chars = subtitle_max_chars(play_res_x, play_res_y)
    for cue in normalized_cues:
        dialogue = build_highlighted_dialogue(
            cue["text"],
            highlight_text=highlight_text,
            max_chars=max_chars,
        )
        events.append(
            f"Dialogue: 0,{ass_time(cue['start'] / 1000)},{ass_time(cue['end'] / 1000)},"
            f"Default,,0,0,0,,{dialogue}"
        )

    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
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
                f"90,90,{margin_v},1"
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


def build_karaoke_dialogue(*, text: str, words: list[Any], max_chars: int = 42) -> str:
    """Return ASS karaoke override text."""

    normalized_words = normalize_word_items(words)
    if not normalized_words:
        return r"\N".join(ass_escape_text(line) for line in wrap_subtitle_text(text, max_chars=max_chars))

    pieces: list[str] = []
    line_chars = 0
    for index, word in enumerate(normalized_words):
        start = word["start"]
        next_start = (
            normalized_words[index + 1]["start"]
            if index + 1 < len(normalized_words)
            else word["end"]
        )
        duration_ms = max(80, next_start - start)
        centiseconds = max(1, round(duration_ms / 10))
        visible_text = word["text"]
        visible_len = max(1, len(visible_text))
        should_wrap = bool(pieces) and line_chars + 1 + visible_len > max_chars
        separator = r"\N" if should_wrap else (" " if pieces else "")
        pieces.append(f"{separator}{{\\k{centiseconds}}}{ass_escape_text(visible_text)}")
        line_chars = visible_len if should_wrap else (line_chars + (1 if pieces[:-1] else 0) + visible_len)
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

    protected_text = protect_highlight_spaces(text, highlight_text=highlight_text)
    return r"\N".join(
        highlight_ass_text(line.replace("\x00", " "), highlight_text=highlight_text)
        for line in wrap_subtitle_text(protected_text, max_chars=max_chars)
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

    spans = highlight_spans(text, query)
    if not spans:
        return ass_escape_text(text)

    parts: list[str] = []
    last = 0

    for start, end in spans:
        if start > last:
            parts.append(ass_escape_text(text[last:start]))
        parts.append(r"{\c&H0031D1FD&}")
        parts.append(ass_escape_text(text[start:end]))
        parts.append(r"{\c&H00FFFFFF&}")
        last = end

    if last < len(text):
        parts.append(ass_escape_text(text[last:]))

    return "".join(parts)


def phrase_has_highlight_match(text: str | None, highlight_text: str | None) -> bool:
    """Return True when text contains the searched phrase or a supported equivalent."""

    query = " ".join((highlight_text or "").split()).strip()
    if not text or not query:
        return False
    return bool(highlight_spans(text, query))


def protect_highlight_spaces(text: str, *, highlight_text: str | None = None) -> str:
    """Protect spaces inside the highlighted phrase so wrapping keeps it together."""

    query = " ".join((highlight_text or "").split()).strip()
    if not query:
        return text

    spans = highlight_spans(text, query)
    if not spans:
        return text

    parts: list[str] = []
    last = 0
    for start, end in spans:
        parts.append(text[last:start])
        parts.append(text[start:end].replace(" ", "\x00"))
        last = end
    parts.append(text[last:])
    return "".join(parts)


def highlight_spans(text: str, query: str) -> list[tuple[int, int]]:
    """Return character spans that should be highlighted in ASS subtitles."""

    text_tokens = token_spans(text)
    query_tokens = [normalize_match_token(token) for token, _start, _end in token_spans(query)]
    if not text_tokens or not query_tokens:
        return []

    spans: list[tuple[int, int]] = []
    for query_sequence in expanded_token_sequences(query_tokens):
        spans.extend(phrase_highlight_spans(text_tokens, query_sequence))
    spans.extend(semantic_highlight_spans(text_tokens, query_tokens))
    return merge_spans(spans)


def expanded_token_sequences(tokens: list[str]) -> list[list[str]]:
    """Return possible token sequences after expanding contractions."""

    sequences: list[list[str]] = [[]]
    for token in tokens:
        next_sequences: list[list[str]] = []
        for sequence in sequences:
            for variant in token_expansion_variants(token):
                candidate = [*sequence, *variant]
                if candidate not in next_sequences:
                    next_sequences.append(candidate)
                if len(next_sequences) >= MAX_QUERY_EXPANSION_VARIANTS:
                    break
            if len(next_sequences) >= MAX_QUERY_EXPANSION_VARIANTS:
                break
        sequences = next_sequences
    return sequences


def phrase_highlight_spans(
    text_tokens: list[tuple[str, int, int]],
    query_tokens: list[str],
) -> list[tuple[int, int]]:
    """Return spans for direct phrase matches with small inflection tolerance."""

    spans: list[tuple[int, int]] = []
    index = 0

    while index < len(text_tokens):
        end_index = expanded_match_end_index(text_tokens, index, query_tokens)
        if end_index is not None:
            spans.append((text_tokens[index][1], text_tokens[end_index - 1][2]))
            index = end_index
            continue
        index += 1

    return spans


def expanded_match_end_index(
    text_tokens: list[tuple[str, int, int]],
    start_index: int,
    query_tokens: list[str],
) -> int | None:
    """Return the exclusive text-token end index when a phrase variant matches."""

    def match_from(text_index: int, query_index: int) -> int | None:
        if query_index == len(query_tokens):
            return text_index
        if text_index >= len(text_tokens):
            return None

        text_token = text_tokens[text_index][0]
        for variant in token_expansion_variants(text_token):
            end_query_index = query_index + len(variant)
            if end_query_index > len(query_tokens):
                continue
            if not all(
                subtitle_tokens_match(query_token, text_variant_token)
                for query_token, text_variant_token in zip(
                    query_tokens[query_index:end_query_index],
                    variant,
                )
            ):
                continue
            end_text_index = match_from(text_index + 1, end_query_index)
            if end_text_index is not None:
                return end_text_index
        return None

    return match_from(start_index, 0)


def semantic_highlight_spans(
    text_tokens: list[tuple[str, int, int]],
    query_tokens: list[str],
) -> list[tuple[int, int]]:
    """Return spans for a few conservative phrase-equivalent subtitle patterns."""

    if not query_asks_for_mean_world_idiom(query_tokens):
        return []

    tokens = [token for token, _start, _end in text_tokens]
    spans: list[tuple[int, int]] = []
    index = 0

    while index < len(tokens):
        if is_mean_token(tokens[index]):
            end_index = mean_idiom_end_index(tokens, index)
            if end_index is not None:
                spans.append((text_tokens[index][1], text_tokens[end_index][2]))
                index = end_index + 1
                continue

        important_end = important_idiom_end_index(tokens, index)
        if important_end is not None:
            spans.append((text_tokens[index][1], text_tokens[important_end][2]))
            index = important_end + 1
            continue

        index += 1

    return spans


def query_asks_for_mean_world_idiom(query_tokens: list[str]) -> bool:
    """Return True for searches such as 'you mean the world to me'."""

    stems = [simple_english_stem(token) for token in query_tokens]
    if not any(stem == "mean" for stem in stems):
        return False
    if "world" in stems or "everything" in stems:
        return True
    joined = " ".join(stems)
    return "so much" in joined or "a lot" in joined


def mean_idiom_end_index(tokens: list[str], mean_index: int) -> int | None:
    """Return the last token index for mean-world style idioms."""

    if tokens_match_at(tokens, mean_index + 1, ["the", "world", "to"]):
        return mean_index + 4 if mean_index + 4 < len(tokens) else None
    if tokens_match_at(tokens, mean_index + 1, ["everything", "to"]):
        return mean_index + 3 if mean_index + 3 < len(tokens) else None
    if tokens_match_at(tokens, mean_index + 1, ["so", "much", "to"]):
        return mean_index + 4 if mean_index + 4 < len(tokens) else None
    if tokens_match_at(tokens, mean_index + 1, ["a", "lot", "to"]):
        return mean_index + 4 if mean_index + 4 < len(tokens) else None
    return None


def important_idiom_end_index(tokens: list[str], index: int) -> int | None:
    """Return the last token index for 'nothing is more important than you'."""

    if tokens_match_at(tokens, index, ["nothing", "is", "more", "important", "than"]):
        return index + 5 if index + 5 < len(tokens) else None
    return None


def tokens_match_at(tokens: list[str], start: int, expected: list[str]) -> bool:
    """Return True when normalized tokens match an expected sequence."""

    if start < 0 or start + len(expected) > len(tokens):
        return False
    return tokens[start : start + len(expected)] == expected


def is_mean_token(token: str) -> bool:
    """Return True for mean/means/meant/meaning variants."""

    return simple_english_stem(token) == "mean" or token in {"meant", "meaning"}


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort and merge overlapping highlight spans."""

    if not spans:
        return []

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return merged


def token_spans(text: str) -> list[tuple[str, int, int]]:
    """Return normalized word-like tokens with original character offsets."""

    return [
        (normalize_match_token(match.group(0)), match.start(), match.end())
        for match in re.finditer(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?", text)
    ]


def expand_token_spans(tokens: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Expand common contractions while preserving original character spans."""

    expanded: list[tuple[str, int, int]] = []
    for token, start, end in tokens:
        variants = token_expansion_variants(token)
        parts = next((variant for variant in variants if variant != [token]), [token])
        expanded.extend((part, start, end) for part in parts)
    return expanded


def token_expansion_variants(token: str) -> list[list[str]]:
    """Return exact and expanded variants for a normalized token."""

    normalized = normalize_match_token(token)
    variants = [[normalized]]
    explicit = CONTRACTION_EXPANSIONS.get(normalized)
    if explicit:
        variants.append(explicit)
    variants.extend(inferred_contraction_expansions(normalized))
    return unique_token_sequences(variants)


def inferred_contraction_expansions(token: str) -> list[list[str]]:
    """Infer common contraction expansions from normalized token suffixes."""

    if token.endswith("n't") and len(token) > 3:
        base = token[:-3]
        base_tokens = NEGATIVE_CONTRACTION_BASES.get(base, [base])
        return [[base_token, "not"] for base_token in base_tokens]

    for suffix, suffix_variants in CONTRACTION_SUFFIX_EXPANSIONS.items():
        if not token.endswith(suffix) or len(token) <= len(suffix):
            continue
        base = token[: -len(suffix)]
        return [[base, *variant] for variant in suffix_variants]

    return []


def unique_token_sequences(sequences: list[list[str]]) -> list[list[str]]:
    """Return token sequences without duplicates while preserving order."""

    unique: list[list[str]] = []
    for sequence in sequences:
        if sequence and sequence not in unique:
            unique.append(sequence)
    return unique


def subtitle_tokens_match(query_token: str, caption_token: str) -> bool:
    """Return True when two subtitle tokens are close enough for phrase highlighting."""

    if query_token == caption_token:
        return True
    if len(query_token) <= 2 or len(caption_token) <= 2:
        return False
    return simple_english_stem(query_token) == simple_english_stem(caption_token)


def normalize_match_token(token: str) -> str:
    """Normalize a token for subtitle phrase matching."""

    return token.lower().replace("’", "'").strip("'")


def simple_english_stem(token: str) -> str:
    """Reduce common English inflections for conservative subtitle highlighting."""

    word = normalize_match_token(token)
    for suffix, min_length in (("ing", 6), ("ied", 5), ("ed", 5), ("es", 5), ("s", 4)):
        if suffix == "s" and word.endswith("ss"):
            continue
        if word.endswith(suffix) and len(word) >= min_length:
            if suffix == "ied":
                return f"{word[:-3]}y"
            return word[: -len(suffix)]
    return word


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
