from src.utils import normalize_whitespace, slugify, title_case_phrase


def test_slugify_phrase() -> None:
    assert slugify("Nice to Meet You!") == "nice-to-meet-you"


def test_slugify_empty_fallback() -> None:
    assert slugify("!!!") == "phrase"


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("  nice   to\nmeet   you  ") == "nice to meet you"


def test_title_case_phrase() -> None:
    assert title_case_phrase("nice to meet you") == "Nice To Meet You"

