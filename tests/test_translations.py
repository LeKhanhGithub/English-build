from pathlib import Path

from src.config import Settings
from src.translations import (
    TranslationService,
    clean_translation_text,
    gemini_response_text,
    normalize_phrase_key,
    parse_translation_json,
)


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
        TRANSLATION_PROVIDER="phrasebook",
    )


def test_translation_service_uses_phrasebook_and_cache(tmp_path: Path) -> None:
    service = TranslationService(make_settings(tmp_path))

    translations = service.get("Nice to meet you")

    assert translations is not None
    assert translations.zh == "很高兴认识你"
    assert translations.ja == "はじめまして"
    assert translations.vi == "Rất vui được gặp bạn"
    assert translations.ko == "만나서 반가워요"
    assert translations.es == "Mucho gusto"
    assert translations.hi == "आपसे मिलकर खुशी हुई"
    assert translations.ar == "سعيد بلقائك"
    assert translations.display_lines() == [
        "🇨🇳 很高兴认识你",
        "🇯🇵 はじめまして",
        "🇻🇳 Rất vui được gặp bạn",
        "🇰🇷 만나서 반가워요",
        "🇪🇸 Mucho gusto",
        "🇮🇳 आपसे मिलकर खुशी हुई",
        "🇸🇦 سعيد بلقائك",
    ]
    assert (tmp_path / "downloads" / "nice-to-meet-you" / "translations.json").is_file()


def test_translation_text_cleaning_rejects_unchanged_source() -> None:
    assert clean_translation_text("  Hello   world  ", "hello world") is None
    assert clean_translation_text("Xin chào", "hello") == "Xin chào"
    assert normalize_phrase_key(" How've   you been ") == "how've you been"


def test_gemini_translation_json_helpers_accept_compact_payloads() -> None:
    response_text = gemini_response_text(
        {
            "steps": [
                {
                    "output": {
                        "content": [
                            {
                        "text": (
                                    '```json\n{"zh":"你最近怎么样","ja":"最近どうしてた？",'
                                    '"vi":"Dạo này bạn thế nào?","ko":"요즘 어떻게 지냈어?",'
                                    '"es":"¿Cómo has estado?","hi":"तुम कैसे रहे?",'
                                    '"ar":"كيف حالك مؤخرًا؟"}\n```'
                                )
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert parse_translation_json(response_text) == {
        "zh": "你最近怎么样",
        "ja": "最近どうしてた？",
        "vi": "Dạo này bạn thế nào?",
        "ko": "요즘 어떻게 지냈어?",
        "es": "¿Cómo has estado?",
        "hi": "तुम कैसे रहे?",
        "ar": "كيف حالك مؤخرًا؟",
    }
