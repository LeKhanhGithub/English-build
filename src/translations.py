"""Phrase translation helpers for intro and b-roll overlays."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from src.config import Settings
from src.utils import read_json, slugify, write_json

logger = logging.getLogger(__name__)

GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
TARGET_LANGUAGES = {
    "zh": ("zh-CN", "🇨🇳", "Simplified Chinese"),
    "ja": ("ja", "🇯🇵", "Japanese"),
    "vi": ("vi", "🇻🇳", "Vietnamese"),
    "ko": ("ko", "🇰🇷", "Korean"),
    "es": ("es", "🇪🇸", "Spanish"),
    "hi": ("hi", "🇮🇳", "Hindi"),
    "ar": ("ar", "🇸🇦", "Arabic"),
}
PHRASEBOOK = {
    "hello": ("你好", "こんにちは", "Xin chào", "안녕하세요", "Hola", "नमस्ते", "مرحبًا"),
    "hi": ("你好", "こんにちは", "Xin chào", "안녕하세요", "Hola", "नमस्ते", "أهلًا"),
    "thank you": ("谢谢", "ありがとう", "Cảm ơn", "감사합니다", "Gracias", "धन्यवाद", "شكرًا"),
    "sorry": ("对不起", "ごめんなさい", "Xin lỗi", "미안해요", "Lo siento", "माफ़ कीजिए", "آسف"),
    "nice to meet you": (
        "很高兴认识你",
        "はじめまして",
        "Rất vui được gặp bạn",
        "만나서 반가워요",
        "Mucho gusto",
        "आपसे मिलकर खुशी हुई",
        "سعيد بلقائك",
    ),
    "good to see you": (
        "很高兴见到你",
        "会えてうれしい",
        "Rất vui được gặp bạn",
        "만나서 반가워요",
        "Me alegra verte",
        "आपसे मिलकर अच्छा लगा",
        "سعيد برؤيتك",
    ),
    "how are you": (
        "你好吗",
        "お元気ですか",
        "Bạn khỏe không",
        "어떻게 지내요?",
        "¿Cómo estás?",
        "आप कैसे हैं?",
        "كيف حالك؟",
    ),
    "how have you been": (
        "你最近怎么样",
        "最近どうしていましたか",
        "Dạo này bạn thế nào",
        "요즘 어떻게 지냈어요?",
        "¿Cómo has estado?",
        "आप कैसे रहे हैं?",
        "كيف كانت أحوالك؟",
    ),
    "how've you been": (
        "你最近怎么样",
        "最近どうしていましたか",
        "Dạo này bạn thế nào",
        "요즘 어떻게 지냈어요?",
        "¿Cómo has estado?",
        "आप कैसे रहे हैं?",
        "كيف كانت أحوالك؟",
    ),
    "what is going on": (
        "怎么回事",
        "何が起きているの",
        "Chuyện gì đang xảy ra",
        "무슨 일이야?",
        "¿Qué está pasando?",
        "क्या हो रहा है?",
        "ما الذي يحدث؟",
    ),
    "what's going on": (
        "怎么回事",
        "何が起きているの",
        "Chuyện gì đang xảy ra",
        "무슨 일이야?",
        "¿Qué está pasando?",
        "क्या हो रहा है?",
        "ما الذي يحدث؟",
    ),
    "see you soon": (
        "一会儿见",
        "また近いうちに",
        "Hẹn gặp lại sớm",
        "곧 봐요",
        "Nos vemos pronto",
        "जल्द मिलते हैं",
        "أراك قريبًا",
    ),
    "see you around": (
        "回头见",
        "またどこかで",
        "Hẹn gặp lại",
        "또 봐요",
        "Nos vemos",
        "फिर मिलते हैं",
        "أراك لاحقًا",
    ),
    "i love you": (
        "我爱你",
        "愛してる",
        "Tôi yêu bạn",
        "사랑해요",
        "Te quiero",
        "मैं तुमसे प्यार करता/करती हूँ",
        "أحبك",
    ),
    "i miss you": (
        "我想你",
        "会いたい",
        "Tôi nhớ bạn",
        "보고 싶어요",
        "Te extraño",
        "मुझे तुम्हारी याद आती है",
        "اشتقت إليك",
    ),
    "i am falling for you": (
        "我喜欢上你了",
        "あなたを好きになってきた",
        "Tôi đang phải lòng bạn",
        "너에게 마음이 가고 있어",
        "Me estoy enamorando de ti",
        "मैं तुम्हें पसंद करने लगा/लगी हूँ",
        "بدأت أقع في حبك",
    ),
    "i'm falling for you": (
        "我喜欢上你了",
        "あなたを好きになってきた",
        "Tôi đang phải lòng bạn",
        "너에게 마음이 가고 있어",
        "Me estoy enamorando de ti",
        "मैं तुम्हें पसंद करने लगा/लगी हूँ",
        "بدأت أقع في حبك",
    ),
}


class PhraseTranslations(BaseModel):
    """Translations for one English phrase."""

    phrase: str
    zh: str | None = None
    ja: str | None = None
    vi: str | None = None
    ko: str | None = None
    es: str | None = None
    hi: str | None = None
    ar: str | None = None
    source: str = "unknown"

    @property
    def has_any(self) -> bool:
        """Return True when at least one translation is available."""

        return any(getattr(self, key) for key in TARGET_LANGUAGES)

    def display_lines(self) -> list[str]:
        """Return compact flag-prefixed translation lines for video overlays."""

        lines: list[str] = []
        for key, _language_code_flag_and_name in TARGET_LANGUAGES.items():
            flag = TARGET_LANGUAGES[key][1]
            value = getattr(self, key)
            if value:
                lines.append(f"{flag} {value}")
        return lines


class TranslationService:
    """Translate short English phrases with cache and graceful fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get(self, phrase: str) -> PhraseTranslations | None:
        """Return translations for a phrase, or None when unavailable."""

        normalized_phrase = normalize_phrase_key(phrase)
        if not self.settings.translations_enabled or not normalized_phrase:
            return None

        cached = self._load_cached(phrase)
        if cached and cached.has_any and self._can_use_cached(cached):
            cached.source = cached.source or "cache"
            return cached

        if self.settings.translation_provider in {"off", "none", "phrasebook"}:
            phrasebook = self._from_phrasebook(phrase, normalized_phrase)
            if phrasebook:
                self._save(phrase, phrasebook)
            return phrasebook

        if self.settings.translation_provider == "gemini":
            translated = self._from_gemini(phrase)
            if translated and translated.has_any:
                self._save(phrase, translated)
                return translated

        phrasebook = self._from_phrasebook(phrase, normalized_phrase)
        if phrasebook:
            self._save(phrase, phrasebook)
            return phrasebook

        translated = self._from_mymemory(phrase)
        if translated and translated.has_any:
            self._save(phrase, translated)
            return translated
        return None

    def _can_use_cached(self, cached: PhraseTranslations) -> bool:
        """Return True when a cached translation still matches the requested provider quality."""

        if any(not getattr(cached, key) for key in TARGET_LANGUAGES):
            return False
        return not (
            self.settings.translation_provider == "gemini"
            and bool(self.settings.gemini_api_key)
            and cached.source != "gemini"
        )

    def _from_phrasebook(
        self,
        phrase: str,
        normalized_phrase: str,
    ) -> PhraseTranslations | None:
        values = PHRASEBOOK.get(normalized_phrase)
        if not values:
            return None
        translations = dict(zip(TARGET_LANGUAGES, values, strict=False))
        return PhraseTranslations(phrase=phrase, source="phrasebook", **translations)

    def _from_gemini(self, phrase: str) -> PhraseTranslations | None:
        if not self.settings.gemini_api_key:
            logger.info("GEMINI_API_KEY is not set; falling back to non-LLM translations")
            return None

        prompt = (
            "Translate this English phrase naturally, like a native speaker would say it. "
            "Preserve the meaning and tone, not word-for-word literalness. "
            "Return ONLY compact JSON with exactly these keys: zh, ja, vi, ko, es, hi, ar. "
            "Use Simplified Chinese for zh, natural Japanese for ja, natural Vietnamese for vi, "
            "natural Korean for ko, natural Spanish for es, natural Hindi in Devanagari for hi, "
            "and natural Modern Standard Arabic for ar. "
            f"English phrase: {phrase!r}"
        )
        payload = {
            "model": self.settings.gemini_model,
            "system_instruction": (
                "You are a careful native-quality phrase translator for short language-learning "
                "video overlays. Do not add explanations, romanization, labels, or markdown."
            ),
            "input": prompt,
            "generation_config": {
                "temperature": 0.2,
            },
        }
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key,
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(20.0, connect=8.0)) as client:
                response = client.post(GEMINI_INTERACTIONS_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - translations should never block rendering
            logger.warning("Gemini translation failed for %r: %s", phrase, exc)
            return None

        text = gemini_response_text(data)
        parsed = parse_translation_json(text)
        if not parsed:
            logger.warning("Gemini returned an unusable translation payload for %r: %r", phrase, text)
            return None
        return PhraseTranslations(
            phrase=phrase,
            **{
                key: clean_translation_text(parsed.get(key) or "", phrase)
                for key in TARGET_LANGUAGES
            },
            source="gemini",
        )

    def _from_mymemory(self, phrase: str) -> PhraseTranslations | None:
        translations: dict[str, str | None] = {key: None for key in TARGET_LANGUAGES}
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=httpx.Timeout(8.0, connect=4.0),
            ) as client:
                for key, (language_code, _flag, _name) in TARGET_LANGUAGES.items():
                    translations[key] = self._fetch_mymemory_translation(
                        client,
                        phrase,
                        language_code,
                    )
        except Exception as exc:  # noqa: BLE001 - translations should never block rendering
            logger.warning("Phrase translation failed for %r: %s", phrase, exc)
            return None

        return PhraseTranslations(phrase=phrase, source="mymemory", **translations)

    def _fetch_mymemory_translation(
        self,
        client: httpx.Client,
        phrase: str,
        target_language: str,
    ) -> str | None:
        params = {
            "q": phrase,
            "langpair": f"en|{target_language}",
            "mt": "1",
        }
        if self.settings.translation_contact_email:
            params["de"] = self.settings.translation_contact_email

        response = client.get(MYMEMORY_URL, params=params)
        response.raise_for_status()
        data = response.json()
        response_data = data.get("responseData") if isinstance(data, dict) else None
        if not isinstance(response_data, dict):
            return None
        translated = response_data.get("translatedText")
        if not isinstance(translated, str):
            return None
        return clean_translation_text(translated, phrase)

    def _cache_path(self, phrase: str) -> Path:
        return self.settings.download_folder / slugify(phrase) / "translations.json"

    def _load_cached(self, phrase: str) -> PhraseTranslations | None:
        path = self._cache_path(phrase)
        if not path.is_file():
            return None
        try:
            return PhraseTranslations.model_validate(read_json(path))
        except Exception as exc:  # noqa: BLE001 - stale cache should not stop rendering
            logger.warning("Ignoring invalid translation cache %s: %s", path, exc)
            return None

    def _save(self, phrase: str, translations: PhraseTranslations) -> None:
        write_json(self._cache_path(phrase), translations.model_dump(mode="json"))


def normalize_phrase_key(phrase: str) -> str:
    """Normalize phrasebook keys."""

    return re.sub(r"\s+", " ", phrase.strip().lower().replace("’", "'"))


def clean_translation_text(value: str, source_phrase: str) -> str | None:
    """Clean machine-translation output for short video overlays."""

    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    if normalize_phrase_key(text) == normalize_phrase_key(source_phrase):
        return None
    return text


def gemini_response_text(data: dict[str, Any]) -> str:
    """Extract text from a Gemini Interactions API response."""

    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()

    pieces: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str):
                pieces.append(text)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(data.get("steps"))
    if not pieces:
        collect(data)
    return "\n".join(piece.strip() for piece in pieces if piece.strip()).strip()


def parse_translation_json(text: str) -> dict[str, str] | None:
    """Parse a compact JSON object returned by an LLM translation provider."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    translations: dict[str, str] = {}
    for key in TARGET_LANGUAGES:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            translations[key] = value.strip()
    return translations or None
