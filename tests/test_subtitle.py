from src.subtitle import (
    adaptive_font_size,
    build_even_karaoke_dialogue,
    build_highlighted_dialogue,
    build_karaoke_dialogue,
    escape_drawtext_text,
    highlight_ass_text,
    normalize_cue_items,
    video_base_filter,
    wrap_subtitle_text,
)


def test_escape_drawtext_text() -> None:
    assert escape_drawtext_text("it's 50%: ok") == "it\\'s 50\\%\\: ok"


def test_adaptive_font_size_bounds() -> None:
    assert adaptive_font_size(1920, 1080) <= 72
    assert adaptive_font_size(320, 180) >= 26


def test_video_base_filter_contains_target_size() -> None:
    assert "scale=1280:720" in video_base_filter(1280, 720)


def test_build_karaoke_dialogue_uses_word_timings() -> None:
    dialogue = build_karaoke_dialogue(
        text="Nice to meet you.",
        words=[
            {"text": "Nice", "start": 0, "end": 120},
            {"text": "to", "start": 120, "end": 220},
            {"text": "meet", "start": 220, "end": 400},
            {"text": "you.", "start": 400, "end": 700},
        ],
    )

    assert "{\\k12}Nice" in dialogue
    assert "{\\k18}meet" in dialogue


def test_build_even_karaoke_dialogue_for_cue_text() -> None:
    dialogue = build_even_karaoke_dialogue("Nice to meet you.", 2000)

    assert "{\\k" in dialogue
    assert "Nice" in dialogue
    assert "you." in dialogue


def test_build_highlighted_dialogue_is_not_fake_karaoke() -> None:
    dialogue = build_highlighted_dialogue(
        "Oh hi. Nice to meet you.",
        highlight_text="nice to meet you",
    )

    assert "{\\k" not in dialogue
    assert "{\\c&H0031D1FD&}Nice to meet you" in dialogue


def test_wrap_subtitle_text_limits_line_length() -> None:
    lines = wrap_subtitle_text(
        "Oh, you're gonna love it in Cuba, Marge. There's shredded pork everywhere!",
        max_chars=32,
    )

    assert len(lines) >= 2
    assert all(len(line) <= 64 for line in lines)


def test_highlight_ass_text_escapes_and_highlights() -> None:
    text = highlight_ass_text("Nice to meet you {friend}", highlight_text="nice to meet you")

    assert "{\\c&H0031D1FD&}Nice to meet you" in text
    assert "\\{friend\\}" in text


def test_normalize_cue_items() -> None:
    cues = normalize_cue_items(
        [
            {"text": "Nice to meet you.", "start": 1000, "end": 2500},
            {"text": "", "start": 0, "end": 500},
        ]
    )

    assert cues == [{"text": "Nice to meet you.", "start": 1000, "end": 2500}]
