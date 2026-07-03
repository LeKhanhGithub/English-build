from pathlib import Path

from src.commons import (
    CommonsBrollService,
    build_credit,
    clean_metadata_text,
    normalize_search_queries,
    normalized_tokens,
)
from src.config import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        DOWNLOAD_FOLDER=Path("downloads"),
        OUTPUT_FOLDER=Path("outputs"),
        LOGS_FOLDER=Path("logs"),
        ASSETS_FOLDER=Path("assets"),
        TEMP_FOLDER=Path(".tmp"),
        COMMONS_MAX_BYTES=80_000_000,
    )


def test_clean_metadata_text_strips_html() -> None:
    assert clean_metadata_text("<span>Jane Doe</span><br>Creator") == "Jane Doe Creator"


def test_build_credit_includes_source_title_artist_and_license() -> None:
    credit = build_credit("File:Example.webm", "Jane Doe", "CC BY-SA 4.0")

    assert credit == "Wikimedia Commons | Example.webm | Jane Doe | CC BY-SA 4.0"


def test_video_from_page_accepts_video_under_size_limit(tmp_path: Path) -> None:
    service = CommonsBrollService(make_settings(tmp_path))
    page = {
        "title": "File:Couple walking.webm",
        "imageinfo": [
            {
                "mime": "video/webm",
                "url": "https://upload.wikimedia.org/example.webm",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Couple_walking.webm",
                "size": 10_000_000,
                "width": 1920,
                "height": 1080,
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "Artist": {"value": "<b>Jane Doe</b>"},
                },
            }
        ],
    }

    video = service._video_from_page(page)

    assert video is not None
    assert video.title == "Couple walking.webm"
    assert video.mime == "video/webm"
    assert video.artist == "Jane Doe"
    assert "CC BY-SA 4.0" in (video.credit or "")


def test_candidate_score_prefers_query_title_match(tmp_path: Path) -> None:
    service = CommonsBrollService(make_settings(tmp_path))
    matching = service._video_from_page(
        {
            "title": "File:Couple holding hands.webm",
            "imageinfo": [
                {
                    "mime": "video/webm",
                    "url": "https://upload.wikimedia.org/couple.webm",
                    "size": 10_000_000,
                    "width": 1920,
                    "height": 1080,
                }
            ],
        }
    )
    noisy = service._video_from_page(
        {
            "title": "File:Geese on beach.webm",
            "imageinfo": [
                {
                    "mime": "video/webm",
                    "url": "https://upload.wikimedia.org/geese.webm",
                    "size": 20_000_000,
                    "width": 1920,
                    "height": 1080,
                }
            ],
        }
    )

    assert matching is not None
    assert noisy is not None
    tokens = normalized_tokens("couple walking")
    assert service._candidate_score(matching, tokens) > service._candidate_score(noisy, tokens)


def test_candidate_score_discourages_meeting_broll_by_default(tmp_path: Path) -> None:
    service = CommonsBrollService(make_settings(tmp_path))
    casual = service._video_from_page(
        {
            "title": "File:Friends walking city street.webm",
            "imageinfo": [
                {
                    "mime": "video/webm",
                    "url": "https://upload.wikimedia.org/casual.webm",
                    "size": 12_000_000,
                    "width": 1920,
                    "height": 1080,
                }
            ],
        }
    )
    meeting = service._video_from_page(
        {
            "title": "File:Business meeting office presentation.webm",
            "imageinfo": [
                {
                    "mime": "video/webm",
                    "url": "https://upload.wikimedia.org/meeting.webm",
                    "size": 12_000_000,
                    "width": 1920,
                    "height": 1080,
                }
            ],
        }
    )

    assert casual is not None
    assert meeting is not None
    default_tokens = normalized_tokens("friends walking city")
    explicit_tokens = normalized_tokens("business meeting")
    assert service._candidate_score(casual, default_tokens) > service._candidate_score(
        meeting,
        default_tokens,
    )
    assert service._is_discouraged_default_broll(meeting, default_tokens)
    assert not service._is_discouraged_default_broll(meeting, explicit_tokens)


def test_normalize_search_queries_deduplicates_and_caps() -> None:
    queries = normalize_search_queries(
        [
            " city street walking ",
            "city street walking",
            "friends walking",
            "park walking",
            "people waving",
            "train station",
            "cafe street",
        ]
    )

    assert queries == [
        "city street walking",
        "friends walking",
        "park walking",
        "people waving",
        "train station",
        "cafe street",
    ]
