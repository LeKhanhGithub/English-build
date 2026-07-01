from src.clipcafe import (
    extract_clip_title,
    extract_movie_name,
    looks_like_clip_result,
    parse_vtt_cues,
)


def test_parse_vtt_cues_cleans_caption_text() -> None:
    cues = parse_vtt_cues(
        """WEBVTT

00:00:00.120 --> 00:00:01.400
<c>I'm falling for you.</c>

00:00:01.500 --> 00:00:03.000
Too.
"""
    )

    assert len(cues) == 2
    assert cues[0].text == "I'm falling for you."
    assert cues[0].start == 120
    assert cues[0].end == 1400


def test_looks_like_clip_result_requires_duration_label() -> None:
    assert looks_like_clip_result(
        "/a-christmas-treasure-2021/im-falling-you-too/",
        "I'm falling for you, too 00:05",
    )
    assert not looks_like_clip_result("/login/", "Login 00:01")
    assert not looks_like_clip_result("/a-christmas-treasure-2021/im-falling-you-too/", "Clip")


def test_extract_clip_metadata_from_page_html() -> None:
    page_html = """
    <meta property="og:title" content="I'm falling for you, too | A Christmas Treasure Clip">
    <script>window.movieData = { id: 1, name: "A Christmas Treasure" };</script>
    """

    assert extract_clip_title(page_html) == "I'm falling for you, too"
    assert extract_movie_name(page_html) == "A Christmas Treasure"
