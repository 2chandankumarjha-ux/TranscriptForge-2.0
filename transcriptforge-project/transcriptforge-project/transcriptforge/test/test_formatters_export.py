import csv
import io
import json

import pytest

from transcriptforge import FormatterLoader, save_many, save_transcript
from transcriptforge.export import FORMAT_EXTENSIONS, format_transcript
from transcriptforge.formatters import (
    CSVFormatter,
    HTMLFormatter,
    JSONLinesFormatter,
    MarkdownFormatter,
    ParagraphTextFormatter,
    TimestampedTextFormatter,
)

from .helpers import HINDI, SAMPLE, make_transcript


@pytest.fixture
def t():
    return make_transcript(SAMPLE)


@pytest.fixture
def t2():
    return make_transcript(
        HINDI,
        video_id="abcdefghijk",
        language="Hindi",
        language_code="hi",
        is_generated=True,
    )


def test_all_new_formats_are_registered_and_have_extensions():
    for name in ("timestamped", "paragraphs", "markdown", "csv", "jsonl", "html"):
        assert name in FormatterLoader.TYPES
    for name in FormatterLoader.TYPES:
        assert name in FORMAT_EXTENSIONS


def test_timestamped(t):
    lines = TimestampedTextFormatter().format_transcript(t).splitlines()
    assert lines[0] == "[00:00] Welcome to the channel."
    assert lines[3] == "[00:12] Python makes transcripts easy."
    assert (
        TimestampedTextFormatter()
        .format_transcript(t, always_hours=True)
        .startswith("[0:00:00]")
    )
    assert "\n\n\n" in TimestampedTextFormatter().format_transcripts([t, t])


def test_paragraph_text(t):
    text = ParagraphTextFormatter().format_transcript(t)
    assert text.split("\n\n") == [
        "Welcome to the channel. Today we talk about python and about transcripts.",
        "Python makes transcripts easy. Thanks for watching!",
    ]
    assert (
        len(
            ParagraphTextFormatter()
            .format_transcript(t, max_gap=100, min_chars=10**6)
            .split("\n\n")
        )
        == 1
    )


def test_markdown_has_links_and_metadata(t, t2):
    md = MarkdownFormatter().format_transcript(t)
    assert md.startswith("# Transcript: GJLlxj_dtq8")
    assert "**[00:12](https://youtu.be/GJLlxj_dtq8?t=12)**" in md
    both = MarkdownFormatter().format_transcripts([t, t2])
    assert "\n---\n" in both and "auto-generated" in both and "कृष्ण" in both


def test_csv_roundtrip(t, t2):
    rows = list(csv.reader(io.StringIO(CSVFormatter().format_transcripts([t, t2]))))
    assert rows[0] == CSVFormatter.COLUMNS
    assert len(rows) == 1 + len(t) + len(t2)
    assert (
        rows[1][:2] == ["GJLlxj_dtq8", "en"]
        and rows[1][-1] == "Welcome to the channel."
    )
    assert rows[-1][-1].startswith("कृष्ण")
    commas = make_transcript([('He said, "hi"', 0, 1)])
    assert (
        list(csv.reader(io.StringIO(CSVFormatter().format_transcript(commas))))[1][-1]
        == 'He said, "hi"'
    )


def test_jsonl(t, t2):
    lines = JSONLinesFormatter().format_transcripts([t, t2]).splitlines()
    assert len(lines) == len(t) + len(t2)
    first = json.loads(lines[0])
    assert first == {
        "video_id": "GJLlxj_dtq8",
        "language_code": "en",
        "text": "Welcome to the channel.",
        "start": 0.0,
        "duration": 2.0,
    }
    assert "कृष्ण" in lines[-1]  # not \u escaped


def test_html_is_escaped_and_complete(t2):
    evil = make_transcript([("<script>alert(1)</script> & more", 0, 1)], video_id='x"y')
    page = HTMLFormatter().format_transcript(evil)
    assert "<script>" not in page.replace("<style>", "")
    assert "&lt;script&gt;" in page and "&amp; more" in page
    assert page.startswith("<!DOCTYPE html>") and page.rstrip().endswith("</html>")
    hindi = HTMLFormatter().format_transcripts([t2])
    assert 'lang="hi"' in hindi and "कृष्ण" in hindi
    assert "2 transcripts" in HTMLFormatter().format_transcripts([t2, t2])
    assert HTMLFormatter().format_transcripts([]).count("<section") == 0


def test_export_format_keeps_hindi_in_json(t2):
    assert "कृष्ण" in format_transcript(t2, "json")
    assert "कृष्ण" in format_transcript(t2, "jsonl")


def test_save_transcript_and_save_many(tmp_path, t, t2):
    path = save_transcript(t, tmp_path / "out", "srt")
    assert path.name == "GJLlxj_dtq8.en.srt" and path.read_text(
        encoding="utf-8"
    ).startswith("1\n")
    custom = save_transcript(t, tmp_path / "out", "webvtt", filename="my video")
    assert custom.name == "my video.vtt"
    paths = save_many([t, t2], tmp_path / "many", ["text", "markdown", "json"])
    assert sorted(p.name for p in paths) == sorted(
        [
            "GJLlxj_dtq8.en.txt",
            "GJLlxj_dtq8.en.md",
            "GJLlxj_dtq8.en.json",
            "abcdefghijk.hi.txt",
            "abcdefghijk.hi.md",
            "abcdefghijk.hi.json",
        ]
    )
    assert "कृष्ण" in (tmp_path / "many" / "abcdefghijk.hi.txt").read_text(
        encoding="utf-8"
    )


def test_unsafe_names_are_sanitised(tmp_path):
    weird = make_transcript(SAMPLE, video_id="../../etc/pw", language_code="en/US")
    path = save_transcript(weird, tmp_path, "text")
    assert path.parent == tmp_path and "/" not in path.name and ".." not in path.name
