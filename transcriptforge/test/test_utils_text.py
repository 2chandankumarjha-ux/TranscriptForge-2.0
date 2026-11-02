import pytest

from transcriptforge import InvalidVideoId, extract_video_id, extract_video_ids
from transcriptforge._text import ends_sentence, tokenize
from transcriptforge.utils import (
    extract_playlist_id,
    format_timestamp,
    is_video_id,
    normalize_video_id,
    timestamp_url,
    unique,
)

VID = "GJLlxj_dtq8"


@pytest.mark.parametrize(
    "value",
    [
        VID,
        "  %s  " % VID,
        "https://www.youtube.com/watch?v=" + VID,
        "https://www.youtube.com/watch?v=%s&t=30s&list=PLabc" % VID,
        "http://youtube.com/watch?feature=share&v=" + VID,
        "https://m.youtube.com/watch?v=" + VID,
        "https://music.youtube.com/watch?v=" + VID,
        "https://youtu.be/%s?si=xyz" % VID,
        "youtu.be/" + VID,
        "www.youtube.com/watch?v=" + VID,
        "https://www.youtube.com/shorts/" + VID,
        "https://www.youtube.com/embed/" + VID,
        "https://www.youtube-nocookie.com/embed/" + VID,
        "https://www.youtube.com/live/" + VID,
        "https://www.youtube.com/v/" + VID,
    ],
)
def test_extract_video_id(value):
    assert extract_video_id(value) == VID


@pytest.mark.parametrize(
    "value",
    ["", "short", "https://example.com/watch?v=" + VID, "https://www.youtube.com/"],
)
def test_extract_video_id_invalid(value):
    with pytest.raises(InvalidVideoId):
        extract_video_id(value)


def test_normalize_keeps_unknown_values():
    assert normalize_video_id("v1") == "v1"
    assert normalize_video_id("https://youtu.be/" + VID) == VID


def test_extract_video_ids_from_text_dedupes_and_ignores_words():
    text = (
        "see https://youtu.be/%s and (https://www.youtube.com/watch?v=abcdefghijk). transcripts again https://youtu.be/%s,"
        % (VID, VID)
    )
    assert extract_video_ids(text) == [VID, "abcdefghijk"]


def test_is_video_id():
    assert is_video_id(VID)
    assert not is_video_id("tooshort")
    assert not is_video_id("")


def test_playlist_id():
    assert extract_playlist_id("https://www.youtube.com/playlist?list=PL123") == "PL123"
    assert extract_playlist_id("https://example.com/?list=PL123") is None
    assert extract_playlist_id("https://www.youtube.com/watch?v=" + VID) is None


def test_timestamps():
    assert format_timestamp(75.4) == "01:15"
    assert format_timestamp(3725) == "1:02:05"
    assert format_timestamp(5, always_hours=True) == "0:00:05"
    assert format_timestamp(-3) == "00:00"
    assert timestamp_url(VID, 75.9) == "https://youtu.be/%s?t=75" % VID


def test_unique_keeps_order():
    assert unique(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_tokenize_keeps_devanagari_words_intact():
    tokens = tokenize("नमस्ते दोस्तों, कृष्ण की कथा। don't stop 2024")
    assert tokens == ["नमस्ते", "दोस्तों", "कृष्ण", "की", "कथा", "don't", "stop", "2024"]


def test_ends_sentence():
    assert ends_sentence("Hello.")
    assert ends_sentence('He said "stop!"')
    assert ends_sentence("यह कथा है।")
    assert not ends_sentence("and then")
    assert not ends_sentence("")


def test_listing_url_detection_and_free_text_with_non_video_links():
    from transcriptforge.sources import is_listing_url

    assert is_listing_url("https://www.youtube.com/playlist?list=PL1")
    assert is_listing_url("https://www.youtube.com/@channel")
    assert is_listing_url("https://www.youtube.com/channel/UC123")
    assert not is_listing_url("https://www.youtube.com/")
    assert not is_listing_url("https://www.youtube.com/watch?v=" + VID)
    assert not is_listing_url("https://example.com/@channel")
    text = "channel https://www.youtube.com/@someone and https://youtu.be/" + VID
    assert extract_video_ids(text) == [VID]
