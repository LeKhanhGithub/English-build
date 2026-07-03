from src.flags import ensure_flag_assets
from src.subtitle import (
    adaptive_font_size,
    build_even_karaoke_dialogue,
    build_highlighted_dialogue,
    build_karaoke_dialogue,
    escape_drawtext_text,
    highlight_ass_text,
    normalize_cue_items,
    phrase_has_highlight_match,
    title_card_filter,
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


def test_build_karaoke_dialogue_wraps_long_playphrase_lines() -> None:
    words = [
        {"text": token, "start": index * 120, "end": (index + 1) * 120}
        for index, token in enumerate(
            "You mean the world to me but well then take your choice right now".split()
        )
    ]
    dialogue = build_karaoke_dialogue(
        text="You mean the world to me but well then take your choice right now",
        words=words,
        max_chars=30,
    )

    assert r"\N" in dialogue
    assert "{\\k12}You" in dialogue


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


def test_highlight_ass_text_matches_close_inflections() -> None:
    text = highlight_ass_text(
        "Oh, I missed you so much, boy.",
        highlight_text="i miss you so much",
    )

    assert "Oh, " in text
    assert "{\\c&H0031D1FD&}I missed you so much" in text
    assert "{\\c&H00FFFFFF&}, boy." in text


def test_phrase_match_accepts_requested_phrase_but_rejects_loose_comb_results() -> None:
    assert phrase_has_highlight_match("I think I'm falling for you.", "I'm falling for you")
    assert phrase_has_highlight_match("I think I am falling for you.", "I'm falling for you")
    assert not phrase_has_highlight_match(
        "I think I'm falling in love with you.",
        "I'm falling for you",
    )
    assert not phrase_has_highlight_match(
        "I think Calculon's falling for you.",
        "I'm falling for you",
    )
    assert not phrase_has_highlight_match(
        "You think I'm dumb enough to fall for that?",
        "I'm falling for you",
    )


def test_phrase_match_accepts_contracted_and_expanded_variants_case_insensitively() -> None:
    assert phrase_has_highlight_match("HOW HAVE YOU BEEN?", "how've you been")
    assert phrase_has_highlight_match("How've you been?", "how have you been")
    assert phrase_has_highlight_match("He's been here before.", "he has been here")
    assert phrase_has_highlight_match("He is ready.", "he's ready")
    assert phrase_has_highlight_match("I do not know.", "I don't know")
    assert phrase_has_highlight_match("I don't know.", "i do not know")


def test_highlight_ass_text_matches_mean_world_idiom_variants() -> None:
    direct = highlight_ass_text(
        "That woman means the world to me.",
        highlight_text="you mean the world to me",
    )
    recipient_variant = highlight_ass_text(
        "You know, it would mean the world to her if she could get her job back.",
        highlight_text="you mean the world to me",
    )
    unrelated = highlight_ass_text(
        "You have revealed to me a world of faith beyond the world of science.",
        highlight_text="you mean the world to me",
    )

    assert "{\\c&H0031D1FD&}means the world to me" in direct
    assert "{\\c&H0031D1FD&}mean the world to her" in recipient_variant
    assert "\\c&H0031D1FD" not in unrelated


def test_build_highlighted_dialogue_keeps_highlighted_phrase_together() -> None:
    dialogue = build_highlighted_dialogue(
        "Before before I missed you so much.",
        highlight_text="i miss you so much",
        max_chars=24,
    )

    assert r"\N{\c&H0031D1FD&}I missed you so much" in dialogue


def test_title_card_filter_wraps_long_intro_text(tmp_path) -> None:
    filters = title_card_filter(
        "It's Good To See You",
        640,
        360,
        text_dir=tmp_path,
        file_prefix="intro",
    )

    assert filters.count("drawtext=") >= 2
    assert "fontsize=" in filters
    assert "textfile=" in filters
    assert "It's" not in filters
    assert (tmp_path / "intro-00.txt").read_text(encoding="utf-8")


def test_title_card_filter_writes_translation_lines(tmp_path) -> None:
    flag_dir = ensure_flag_assets(tmp_path / "assets", force=True)
    filters = title_card_filter(
        "Nice To Meet You",
        1280,
        720,
        text_dir=tmp_path,
        file_prefix="intro",
        translation_lines=[
            "🇨🇳 很高兴认识你",
            "🇯🇵 はじめまして",
            "🇻🇳 Rất vui được gặp bạn",
            "🇰🇷 만나서 반가워요",
            "🇪🇸 Mucho gusto",
            "🇮🇳 आपसे मिलकर खुशी हुई",
        ],
        flag_dir=flag_dir,
        output_label="v",
    )

    assert "drawbox=" in filters
    assert "textfile=" in filters
    assert "movie=" in filters
    assert "overlay=" in filters
    assert "fontcolor=0xFDD131" in filters
    assert "fontcolor=0xEAF2FF" in filters
    assert "很高兴认识你" not in filters
    assert (tmp_path / "intro-flag-0.txt").read_text(encoding="utf-8") == "cn.png"
    assert (tmp_path / "intro-translation-0.txt").read_text(encoding="utf-8") == "很高兴认识你"
    assert (tmp_path / "intro-flag-2.txt").read_text(encoding="utf-8") == "vn.png"
    vietnamese_line = (tmp_path / "intro-translation-2.txt").read_text(encoding="utf-8")
    assert vietnamese_line == "Rất vui được gặp bạn"
    assert "Tiếng Việt" not in vietnamese_line
    assert (tmp_path / "intro-flag-5.txt").read_text(encoding="utf-8") == "in.png"
    assert (tmp_path / "intro-translation-5.txt").read_text(encoding="utf-8") == "आपसे मिलकर खुशी हुई"


def test_normalize_cue_items() -> None:
    cues = normalize_cue_items(
        [
            {"text": "Nice to meet you.", "start": 1000, "end": 2500},
            {"text": "", "start": 0, "end": 500},
        ]
    )

    assert cues == [{"text": "Nice to meet you.", "start": 1000, "end": 2500}]
