import pytest

from transcriptforge import (
    analyze_transcript,
    chunk_by_chars,
    chunk_by_time,
    extract_keywords,
    search_transcript,
    summarize,
    to_paragraphs,
)

from .helpers import HINDI, SAMPLE, make_transcript


# ------------------------------------------------------------------ segments
def test_paragraphs_split_on_pause():
    paragraphs = to_paragraphs(make_transcript(SAMPLE), max_gap=1.5)
    assert len(paragraphs) == 2
    assert paragraphs[0].text.startswith("Welcome to the channel.")
    assert paragraphs[0].start == 0.0 and paragraphs[0].end == 6.0
    assert paragraphs[1].start == 12.0
    assert paragraphs[1].link("GJLlxj_dtq8").endswith("?t=12")
    assert paragraphs[1].timestamp == "00:12"
    assert paragraphs[0].duration == 6.0
    assert paragraphs[0].to_dict()["index"] == 0


def test_paragraphs_split_on_sentence_end_and_max_chars():
    items = [
        ("First sentence is here.", 0, 1),
        ("Second one follows.", 1, 1),
        ("third", 2, 1),
    ]
    by_sentence = to_paragraphs(make_transcript(items), min_chars=30, max_gap=10)
    assert [p.text for p in by_sentence] == [
        "First sentence is here. Second one follows.",
        "third",
    ]
    by_size = to_paragraphs(
        make_transcript(items), min_chars=1000, max_chars=10, max_gap=10
    )
    assert len(by_size) == 3


def test_paragraphs_skip_blank_snippets_and_empty_transcripts():
    assert to_paragraphs(make_transcript([])) == []
    assert to_paragraphs(make_transcript([("  ", 0, 1)])) == []


def test_chunk_by_time():
    chunks = chunk_by_time(make_transcript(SAMPLE), window_seconds=10)
    assert [c.start for c in chunks] == [0.0, 12.0]
    assert "Python makes transcripts easy." in chunks[1].text


def test_chunk_by_time_overlap_repeats_boundary_snippets():
    t = make_transcript([("a", 0, 1), ("b", 6, 1), ("c", 11, 1)])
    chunks = chunk_by_time(t, window_seconds=10, overlap_seconds=5)
    texts = [c.text for c in chunks]
    assert "b" in texts[0] and "b" in texts[1]


def test_chunk_by_time_validation():
    t = make_transcript(SAMPLE)
    with pytest.raises(ValueError):
        chunk_by_time(t, window_seconds=0)
    with pytest.raises(ValueError):
        chunk_by_time(t, window_seconds=10, overlap_seconds=10)


def test_chunk_by_chars_basic_and_overlap():
    items = [("x" * 10, float(i), 1.0) for i in range(6)]
    t = make_transcript(items)
    plain = chunk_by_chars(t, max_chars=25)
    assert [c.text.count("x") // 10 for c in plain] == [2, 2, 2]
    assert plain[1].start == 2.0

    overlapped = chunk_by_chars(t, max_chars=25, overlap_chars=11)
    assert len(overlapped) > len(plain)
    assert overlapped[1].start < plain[1].start
    # always terminates and covers everything
    assert overlapped[-1].end == 6.0


def test_chunk_by_chars_single_long_snippet_still_progresses():
    t = make_transcript([("y" * 50, 0, 1), ("z", 1, 1)])
    chunks = chunk_by_chars(t, max_chars=10, overlap_chars=5)
    assert [c.text for c in chunks] == ["y" * 50, "z"]


def test_chunk_by_chars_validation():
    t = make_transcript(SAMPLE)
    with pytest.raises(ValueError):
        chunk_by_chars(t, max_chars=0)
    with pytest.raises(ValueError):
        chunk_by_chars(t, max_chars=10, overlap_chars=10)


# -------------------------------------------------------------------- search
def test_search_plain_case_insensitive_with_context():
    hits = search_transcript(make_transcript(SAMPLE), "PYTHON", context=1)
    assert [h.snippet_index for h in hits] == [1, 3]
    assert hits[0].before == ["Welcome to the channel."]
    assert hits[0].after == ["and about transcripts."]
    assert hits[0].match == "python"
    assert hits[1].url == "https://youtu.be/GJLlxj_dtq8?t=12"
    assert hits[1].timestamp == "00:12"
    assert hits[0].to_dict()["url"].endswith("?t=2")


def test_search_case_sensitive_whole_word_and_max_hits():
    t = make_transcript(SAMPLE)
    assert len(search_transcript(t, "python", case_sensitive=True)) == 1
    assert search_transcript(t, "transcript", whole_word=True) == []
    assert len(search_transcript(t, "transcripts", whole_word=True)) == 2
    assert len(search_transcript(t, "python", max_hits=1)) == 1


def test_search_across_snippet_boundary():
    hits = search_transcript(make_transcript(SAMPLE), "python and about")
    assert len(hits) == 1 and hits[0].snippet_index == 1


def test_search_regex_and_errors():
    t = make_transcript(SAMPLE)
    assert len(search_transcript(t, r"trans\w+", regex=True)) == 2
    assert search_transcript(t, r"x*", regex=True) == []  # empty matches ignored
    with pytest.raises(ValueError):
        search_transcript(t, "")
    import re

    with pytest.raises(re.error):
        search_transcript(t, "(", regex=True)


def test_search_hindi_whole_word_respects_matras():
    t = make_transcript(HINDI, language_code="hi")
    assert len(search_transcript(t, "कृष्ण", whole_word=True)) == 2
    # "कृ" is a prefix of a longer word, so a whole word search must not match it
    assert search_transcript(t, "कृ", whole_word=True) == []
    assert len(search_transcript(t, "कृ")) == 2


# ------------------------------------------------------------------ analysis
def test_extract_keywords_ignores_stopwords():
    keywords = dict(
        extract_keywords("the python and the python code is about code code")
    )
    assert keywords == {"python": 2, "code": 3}


def test_analyze_transcript_numbers():
    stats = analyze_transcript(make_transcript(SAMPLE))
    assert stats.snippet_count == 5
    assert stats.word_count == 19
    assert stats.duration_seconds == 17.0
    assert stats.words_per_minute == 67.1
    assert stats.longest_pause_seconds == 6.0
    assert stats.top_keywords[0][0] in {"python", "transcripts"}
    assert 0 < stats.lexical_diversity <= 1
    data = stats.to_dict()
    assert data["video_id"] == "GJLlxj_dtq8" and isinstance(
        data["top_keywords"][0], list
    )


def test_analyze_transcript_phrases_and_empty():
    t = make_transcript(
        [("machine learning is fun", 0, 2), ("machine learning rocks", 2, 2)]
    )
    assert analyze_transcript(t).top_phrases[0] == ("machine learning", 2)
    empty = analyze_transcript(make_transcript([]))
    assert (
        empty.word_count == 0
        and empty.words_per_minute == 0.0
        and empty.lexical_diversity == 0.0
    )


def test_analyze_hindi_keywords():
    stats = analyze_transcript(make_transcript(HINDI, language_code="hi"))
    assert stats.top_keywords[0] == ("कृष्ण", 2)
    assert all(word not in {"की", "हम"} for word, _ in stats.top_keywords)


def test_summarize_returns_passages_in_time_order():
    items = (
        [("python python python rocks", 0, 2)]
        + [("w%da w%db w%dc" % (i, i, i), float(i * 5), 1) for i in range(1, 8)]
        + [("python rocks again python", 60, 2)]
    )
    passages = summarize(make_transcript(items), passages=2, max_chars=30)
    assert [p.text for p in passages] == [
        "python python python rocks",
        "python rocks again python",
    ]
    assert passages[0].start < passages[1].start


def test_summarize_handles_stopword_only_passages():
    items = [("the and of to", 0, 1), ("python rocks python", 10, 1)]
    passages = summarize(make_transcript(items), passages=1, max_chars=30)
    assert [p.text for p in passages] == ["python rocks python"]


def test_chunk_by_time_skips_blank_snippets():
    t = make_transcript([("  ", 0, 1), ("hello", 1, 1)])
    assert [c.text for c in chunk_by_time(t, window_seconds=10)] == ["hello"]
