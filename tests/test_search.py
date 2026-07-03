from pathlib import Path

from src.config import Settings
from src.search import ClipInfo, SearchResult, SearchService, SubtitleCue, select_best_source


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


def test_apply_source_priority_reorders_and_reindexes(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
        SOURCE_PRIORITY="playphrase,clipcafe,comb",
    )
    result = SearchResult(
        phrase="hello",
        slug="hello",
        source_url="https://www.playphrase.me",
        created_at="2026-01-01T00:00:00+00:00",
        clips=[
            ClipInfo(index=1, source="playphrase", title="one", subtitle_text="one"),
            ClipInfo(index=2, source="comb", title="three", subtitle_text="three"),
            ClipInfo(index=3, source="clipcafe", title="two", subtitle_text="two"),
        ],
    )

    SearchService(settings)._apply_source_priority(result)

    assert [clip.source for clip in result.clips] == ["playphrase", "clipcafe", "comb"]
    assert [clip.index for clip in result.clips] == [1, 2, 3]


def test_should_keep_cached_result_when_fresh_loses_fallback_clips(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
        TARGET_TOTAL_CLIPS=10,
        SOURCE_PRIORITY="playphrase,clipcafe,comb",
    )
    service = SearchService(settings)
    cached = SearchResult(
        phrase="hello",
        slug="hello",
        source_url="https://www.playphrase.me",
        created_at="2026-01-01T00:00:00+00:00",
        source_status={
            "source_priority": ["playphrase", "clipcafe", "comb"],
            "comb": {"strict_phrase_match": True},
            "clipcafe": {"strict_phrase_match": True},
        },
        clips=[
            ClipInfo(
                index=index,
                source="clipcafe",
                title="hello",
                subtitle_text="hello",
                subtitle_cues=[SubtitleCue(text="hello", start=0, end=1000)],
            )
            for index in range(1, 11)
        ],
    )
    fresh = SearchResult(
        phrase="hello",
        slug="hello",
        source_url="https://www.playphrase.me",
        created_at="2026-01-01T00:00:00+00:00",
        clips=[ClipInfo(index=index, title="hello", subtitle_text="hello") for index in range(1, 6)],
    )

    assert service._should_keep_cached_result(cached, fresh)
