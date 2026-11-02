import html
import re
import unicodedata
from dataclasses import replace
from typing import List, Optional

from ._transcripts import FetchedTranscript, FetchedTranscriptSnippet

# [Music], [Applause], [संगीत], [तालियाँ] ... (short bracketed sound descriptions)
# not when glued to a word on the left (arr[i], text[1]): that is not a sound description
_SOUND_TAG_RE = re.compile(r"(?<![\w\u0900-\u097F])\[[^\[\]]{1,60}\]")
_MUSIC_NOTES_RE = re.compile(r"[\u266a\u266b\u266c\u2669]+")
_SPEAKER_MARKER_RE = re.compile(r"(?:^|\s)>>+\s*|^-\s+")
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
_WHITESPACE_RE = re.compile(r"\s+")
# zero-width space / BOM. NOTE: ZWJ (U+200D) and ZWNJ (U+200C) are deliberately kept,
# because Devanagari conjuncts (e.g. क्‍ष) depend on them.
_INVISIBLE_RE = re.compile("[\u200b\ufeff]")


def clean_text(
    text: str,
    remove_sound_tags: bool = True,
    remove_speaker_markers: bool = True,
    unescape_html: bool = True,
    strip_html_tags: bool = True,
    unicode_normalization: Optional[str] = "NFC",
) -> str:
    """Cleans a single caption string. See `clean_transcript` for the options."""
    if unescape_html:
        text = html.unescape(text)
    if strip_html_tags:
        text = _HTML_TAG_RE.sub("", text)
    if remove_sound_tags:
        text = _SOUND_TAG_RE.sub(" ", text)
        text = _MUSIC_NOTES_RE.sub(" ", text)
    if remove_speaker_markers:
        text = _SPEAKER_MARKER_RE.sub(" ", text)
    text = _INVISIBLE_RE.sub("", text)
    text = text.replace("\xa0", " ")
    if unicode_normalization:
        text = unicodedata.normalize(unicode_normalization, text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def clean_transcript(
    transcript: FetchedTranscript,
    remove_sound_tags: bool = True,
    remove_speaker_markers: bool = True,
    unescape_html: bool = True,
    strip_html_tags: bool = True,
    dedupe: bool = True,
    unicode_normalization: Optional[str] = "NFC",
) -> FetchedTranscript:
    """
    Returns a cleaned copy of the transcript (the input is never modified):

    - removes sound descriptions like ``[Music]`` / ``[संगीत]`` and ♪ symbols
    - removes ``>>`` speaker-change markers
    - unescapes HTML entities and strips leftover formatting tags
    - collapses whitespace and normalises Unicode (NFC by default, which keeps
      Devanagari text consistent)
    - drops snippets that became empty and merges immediately repeated lines
    """
    cleaned: List[FetchedTranscriptSnippet] = []
    for snippet in transcript:
        text = clean_text(
            snippet.text,
            remove_sound_tags=remove_sound_tags,
            remove_speaker_markers=remove_speaker_markers,
            unescape_html=unescape_html,
            strip_html_tags=strip_html_tags,
            unicode_normalization=unicode_normalization,
        )
        if not text:
            continue
        if dedupe and cleaned and cleaned[-1].text.casefold() == text.casefold():
            previous = cleaned[-1]
            end = max(
                previous.start + previous.duration, snippet.start + snippet.duration
            )
            cleaned[-1] = replace(previous, duration=round(end - previous.start, 3))
            continue
        cleaned.append(replace(snippet, text=text))
    return replace(transcript, snippets=cleaned)
