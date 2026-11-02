from transcriptforge import clean_text, clean_transcript

from .helpers import make_transcript


def test_clean_text_removes_sound_tags_markers_and_whitespace():
    assert clean_text("[Music] >> Hello   world ♪") == "Hello world"
    assert clean_text("[संगीत] नमस्ते") == "नमस्ते"
    assert (
        clean_text("a&nbsp;b &amp; c") == "a b & c"
        or clean_text("a&nbsp;b &amp; c") == "a b & c"
    )


def test_clean_text_strips_html_tags_but_not_comparisons():
    assert clean_text("this is <i>important</i>") == "this is important"
    assert clean_text("if a < b and c > d") == "if a < b and c > d"


def test_clean_text_keeps_zwj_and_normalizes_nfc():
    zwj = "क्\u200dष"
    assert clean_text(zwj) == zwj
    decomposed = "e\u0301"  # e + combining acute
    assert clean_text(decomposed) == "\u00e9"
    assert clean_text(decomposed, unicode_normalization=None) == decomposed


def test_clean_text_options_can_be_disabled():
    assert clean_text("[Music] hi", remove_sound_tags=False) == "[Music] hi"
    assert (
        clean_text("&amp; <b>x</b>", unescape_html=False, strip_html_tags=False)
        == "&amp; <b>x</b>"
    )
    assert clean_text(">> hi", remove_speaker_markers=False) == ">> hi"


def test_clean_transcript_drops_empty_and_merges_duplicates():
    original = make_transcript(
        [
            ("[Music]", 0.0, 2.0),
            ("Hello", 2.0, 1.0),
            ("hello", 3.0, 1.0),
            ("World", 4.0, 1.0),
        ]
    )
    cleaned = clean_transcript(original)
    assert [s.text for s in cleaned] == ["Hello", "World"]
    assert cleaned[0].start == 2.0 and cleaned[0].duration == 2.0
    # original untouched
    assert len(original) == 4 and original[0].text == "[Music]"
    assert cleaned.video_id == original.video_id


def test_clean_transcript_without_dedupe():
    cleaned = clean_transcript(
        make_transcript([("a", 0, 1), ("a", 1, 1)]), dedupe=False
    )
    assert len(cleaned) == 2
