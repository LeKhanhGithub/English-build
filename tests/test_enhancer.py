from pathlib import Path

from src.config import Settings
from src.enhancer import (
    REEL_BROLL_FRONT_MAX_HEIGHT,
    REEL_BROLL_FRONT_WIDTH,
    REEL_EYEBROW_Y,
    REEL_FOOTER_Y,
    REEL_MAIN_FRONT_WIDTH,
    REEL_SKIP_INTRO_SECONDS,
    VideoEnhancer,
    default_broll_queries,
    default_broll_query,
)
from src.flags import ensure_flag_assets


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
    )


def test_default_broll_query_for_romantic_phrase() -> None:
    queries = default_broll_queries("I'm falling for you")

    assert default_broll_query("I'm falling for you") == queries[0]
    assert len(queries) >= 5
    assert "people conversation" not in queries
    assert "couple walking" in queries


def test_default_broll_queries_vary_by_phrase() -> None:
    assert default_broll_query("I'm falling for you") != default_broll_query("What is going on")


def test_headline_filters_use_text_files_for_apostrophes(tmp_path: Path) -> None:
    enhancer = VideoEnhancer(make_settings(tmp_path))
    filters = enhancer._headline_filters("I'm falling for you", tmp_path, prefix="test")
    combined = ",".join(filters)

    assert "textfile=" in combined
    assert "I'm falling for you" not in combined
    assert f"y={REEL_EYEBROW_Y}" in combined
    assert f"y={REEL_FOOTER_Y}" in combined
    assert (tmp_path / "test-phrase-0.txt").read_text(encoding="utf-8") == "I'm falling for you"


def test_render_vertical_main_skips_intro_for_reel(tmp_path: Path, monkeypatch) -> None:
    enhancer = VideoEnhancer(make_settings(tmp_path))
    captured: list[list[str]] = []

    monkeypatch.setattr(VideoEnhancer, "_run", staticmethod(lambda command: captured.append(command)))

    enhancer._render_vertical_main(
        input_path=tmp_path / "input.mp4",
        phrase="nice to meet you",
        output_path=tmp_path / "reel-main.mp4",
        temp_dir=tmp_path,
    )

    assert captured
    command = captured[0]
    seek_index = command.index("-ss")
    input_index = command.index("-i")
    assert seek_index < input_index
    assert command[seek_index + 1] == f"{REEL_SKIP_INTRO_SECONDS:.3f}"
    filter_complex = command[command.index("-filter_complex") + 1]
    assert f"scale={REEL_MAIN_FRONT_WIDTH}:-2" in filter_complex


def test_render_broll_hook_uses_larger_front_video(tmp_path: Path, monkeypatch) -> None:
    enhancer = VideoEnhancer(make_settings(tmp_path))
    captured: list[list[str]] = []

    monkeypatch.setattr(VideoEnhancer, "_run", staticmethod(lambda command: captured.append(command)))

    enhancer._render_broll_hook(
        broll_path=tmp_path / "broll.mp4",
        phrase="nice to meet you",
        output_path=tmp_path / "broll-hook.mp4",
        temp_dir=tmp_path,
        credit=None,
        translations=None,
    )

    assert captured
    command = captured[0]
    filter_complex = command[command.index("-filter_complex") + 1]
    assert f"scale={REEL_BROLL_FRONT_WIDTH}:{REEL_BROLL_FRONT_MAX_HEIGHT}" in filter_complex


def test_hook_text_filters_include_translation_lines(tmp_path: Path) -> None:
    enhancer = VideoEnhancer(make_settings(tmp_path))
    flag_dir = ensure_flag_assets(tmp_path / "assets", force=True)
    filters, output_label = enhancer._hook_text_filters(
        "nice to meet you",
        tmp_path,
        credit=None,
        translation_lines=[
            "🇨🇳 很高兴认识你",
            "🇯🇵 はじめまして",
            "🇻🇳 Rất vui được gặp bạn",
            "🇰🇷 만나서 반가워요",
            "🇪🇸 Mucho gusto",
            "🇮🇳 आपसे मिलकर खुशी हुई",
            "🇸🇦 سعيد بلقائك",
        ],
        input_label="base",
        flag_dir=flag_dir,
    )
    combined = ";".join(filters)

    assert output_label.startswith("hooktext")
    assert "textfile=" in combined
    assert "movie=" in combined
    assert "overlay=" in combined
    assert "color=black@0.66" in combined
    assert "fontcolor=0xFDD131" in combined
    assert "fontcolor=0xEAF2FF" in combined
    assert "很高兴认识你" not in combined
    assert (tmp_path / "hook-flag-0.txt").read_text(encoding="utf-8") == "cn.png"
    assert (tmp_path / "hook-translation-0.txt").read_text(encoding="utf-8") == "很高兴认识你"
    assert (tmp_path / "hook-flag-2.txt").read_text(encoding="utf-8") == "vn.png"
    vietnamese_line = (tmp_path / "hook-translation-2.txt").read_text(encoding="utf-8")
    assert vietnamese_line == "Rất vui được gặp bạn"
    assert "Tiếng Việt" not in vietnamese_line
    assert (tmp_path / "hook-flag-5.txt").read_text(encoding="utf-8") == "in.png"
    assert (tmp_path / "hook-translation-5.txt").read_text(encoding="utf-8") == "आपसे मिलकर खुशी हुई"
    assert (tmp_path / "hook-flag-6.txt").read_text(encoding="utf-8") == "sa.png"
    assert (tmp_path / "hook-translation-6.txt").read_text(encoding="utf-8") == "سعيد بلقائك"
