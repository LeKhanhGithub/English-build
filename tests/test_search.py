from src.search import SearchResult, select_best_source


def test_select_best_source_prefers_hls_playlist() -> None:
    sources = [
        "https://example.com/clip-480p.mp4",
        "https://example.com/master.m3u8",
    ]
    assert select_best_source(sources) == "https://example.com/master.m3u8"


def test_search_result_model_roundtrip() -> None:
    result = SearchResult(
        phrase="hello",
        slug="hello",
        source_url="https://www.playphrase.me",
        created_at="2026-01-01T00:00:00+00:00",
        clips=[],
    )
    assert SearchResult.model_validate(result.model_dump()).phrase == "hello"

