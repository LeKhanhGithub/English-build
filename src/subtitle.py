"""Subtitle and title-card filter helpers for FFmpeg."""

from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Any

CONTRACTION_EXPANSIONS = {
    "i'm": ["i", "am"],
    "you're": ["you", "are"],
    "he's": ["he", "is"],
    "she's": ["she", "is"],
    "it's": ["it", "is"],
    "we're": ["we", "are"],
    "they're": ["they", "are"],
    "i've": ["i", "have"],
    "you've": ["you", "have"],
    "we've": ["we", "have"],
    "they've": ["they", "have"],
    "i'll": ["i", "will"],
    "you'll": ["you", "will"],
    "he'll": ["he", "will"],
    "she'll": ["she", "will"],
    "it'll": ["it", "will"],
    "we'll": ["we", "will"],
    "they'll": ["they", "will"],
    "i'd": ["i", "would"],
    "you'd": ["you", "would"],
    "he'd": ["he", "would"],
    "she'd": ["she", "would"],
    "it'd": ["it", "would"],
    "we'd": ["we", "would"],
    "they'd": ["they", "would"],
    "can't": ["can", "not"],
    "cannot": ["can", "not"],
    "won't": ["will", "not"],
    "don't": ["do", "not"],
    "doesn't": ["does", "not"],
    "didn't": ["did", "not"],
    "isn't": ["is", "not"],
    "aren't": ["are", "not"],
    "wasn't": ["was", "not"],
    "weren't": ["were", "not"],
}


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

    max_font_size = adaptive_font_size(width, height, title=True)
    min_font_size = max(34, min(width, height) // 18)

    for font_size in range(max_font_size, min_font_size - 1, -2):
        max_chars = max_chars_for_font(
            width,
            font_size,
            max_width_ratio=0.72,
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
) -> str:
    """Build an FFmpeg drawtext filter for centered or bottom-centered text."""

    escaped_text = escape_drawtext_text(text)
    resolved_font_size = font_size or adaptive_font_size(width, height, title=title)
    border = max(2, resolved_font_size // 14)
    font = find_font_file()
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

    return (
        "drawtext="
        f"{font_part}"
        f"{text_part}"
        "x=(w-text_w)/2:"
        f"y={resolved_y_expr}:"
        f"fontsize={resolved_font_size}:"
        "fontcolor=white:"
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
) -> str:
    """Build the video filter for an intro or outro title card."""

    lines, font_size = title_lines_and_font_size(text, width, height)
    line_spacing = max(8, font_size // 6)
    block_height = (len(lines) * font_size) + max(0, len(lines) - 1) * line_spacing
    line_step = font_size + line_spacing

    filters = ["format=yuv420p"]
    for index, line in enumerate(lines):
        y_expr = f"(h-{block_height})/2+{index * line_step}"
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
            )
        )
    return ",".join(filters)


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

    expanded_text_tokens = expand_token_spans(text_tokens)
    expanded_query_tokens = [
        token for token, _start, _end in expand_token_spans(token_spans(query))
    ]

    spans = phrase_highlight_spans(expanded_text_tokens, expanded_query_tokens)
    spans.extend(semantic_highlight_spans(text_tokens, query_tokens))
    return merge_spans(spans)


def phrase_highlight_spans(
    text_tokens: list[tuple[str, int, int]],
    query_tokens: list[str],
) -> list[tuple[int, int]]:
    """Return spans for direct phrase matches with small inflection tolerance."""

    spans: list[tuple[int, int]] = []
    query_length = len(query_tokens)
    index = 0

    while index <= len(text_tokens) - query_length:
        candidate = text_tokens[index : index + query_length]
        if all(
            subtitle_tokens_match(query_token, candidate_token)
            for query_token, (candidate_token, _start, _end) in zip(query_tokens, candidate)
        ):
            spans.append((candidate[0][1], candidate[-1][2]))
            index += query_length
            continue
        index += 1

    return spans


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
        parts = CONTRACTION_EXPANSIONS.get(token)
        if parts:
            expanded.extend((part, start, end) for part in parts)
        else:
            expanded.append((token, start, end))
    return expanded


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
