from pathlib import Path

import pytest

from src.main import _normalize_phrase_arguments, _run_phrase_batch
from src.utils import AppError


def test_normalize_phrase_arguments_accepts_quoted_and_semicolon_lists() -> None:
    phrases = _normalize_phrase_arguments(
        [" nice to meet you ", "how are you; see you soon\nthank you"]
    )

    assert phrases == ["nice to meet you", "how are you", "see you soon", "thank you"]


def test_normalize_phrase_arguments_limits_batches_to_five() -> None:
    with pytest.raises(AppError, match="at most 5 phrases"):
        _normalize_phrase_arguments(["one; two; three; four; five; six"])


def test_normalize_phrase_arguments_can_allow_latest_fallback() -> None:
    assert _normalize_phrase_arguments(None, allow_empty=True) == []


def test_normalize_phrase_arguments_rejects_empty_phrase_text() -> None:
    with pytest.raises(AppError, match="non-empty"):
        _normalize_phrase_arguments([" ; "], allow_empty=True)


def test_run_phrase_batch_continues_after_one_phrase_fails() -> None:
    calls: list[str] = []

    def worker(phrase: str) -> Path:
        calls.append(phrase)
        if phrase == "bad phrase":
            raise AppError("boom")
        return Path(f"{phrase}.mp4")

    with pytest.raises(AppError, match="1 of 3 phrases failed"):
        _run_phrase_batch(
            ["first phrase", "bad phrase", "last phrase"],
            action_name="Video",
            worker=worker,
        )

    assert calls == ["first phrase", "bad phrase", "last phrase"]
