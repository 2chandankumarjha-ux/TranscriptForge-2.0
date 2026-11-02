import re
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ._text import WORD_CHARS
from ._transcripts import FetchedTranscript
from .utils import format_timestamp, timestamp_url


@dataclass
class SearchHit:
    video_id: str
    snippet_index: int
    start: float
    text: str
    """The text of the caption snippet the match starts in."""
    match: str
    """The exact matched text."""
    before: List[str] = field(default_factory=list)
    after: List[str] = field(default_factory=list)

    @property
    def timestamp(self) -> str:
        return format_timestamp(self.start)

    @property
    def url(self) -> str:
        return timestamp_url(self.video_id, self.start)

    def to_dict(self) -> Dict:
        return {
            "video_id": self.video_id,
            "snippet_index": self.snippet_index,
            "start": self.start,
            "timestamp": self.timestamp,
            "url": self.url,
            "match": self.match,
            "text": self.text,
            "before": self.before,
            "after": self.after,
        }


def search_transcript(
    transcript: FetchedTranscript,
    query: str,
    regex: bool = False,
    case_sensitive: bool = False,
    whole_word: bool = False,
    context: int = 0,
    max_hits: Optional[int] = None,
) -> List[SearchHit]:
    """
    Finds `query` in a transcript and returns every hit with its timestamp, a deep
    link and optional surrounding snippets. Matches may span snippet boundaries,
    since the transcript is searched as one continuous text.

    :param regex: treat `query` as a regular expression (re.error is raised if it
        is invalid).
    :param whole_word: only match whole words. This is Devanagari-aware, so a Hindi
        word is not matched in the middle of a longer word.
    :param context: number of snippets to include before and after the hit.
    """
    if not query:
        raise ValueError("query must not be empty")

    pattern = query if regex else re.escape(query)
    if whole_word:
        pattern = "(?<![{w}])(?:{p})(?![{w}])".format(w=WORD_CHARS, p=pattern)
    compiled = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)

    texts = [snippet.text for snippet in transcript]
    offsets = []
    position = 0
    for text in texts:
        offsets.append(position)
        position += len(text) + 1
    joined = " ".join(texts)

    hits: List[SearchHit] = []
    for found in compiled.finditer(joined):
        if not found.group(0):
            continue
        index = bisect_right(offsets, found.start()) - 1
        snippet = transcript[index]
        hits.append(
            SearchHit(
                video_id=transcript.video_id,
                snippet_index=index,
                start=snippet.start,
                text=snippet.text,
                match=found.group(0),
                before=texts[max(0, index - context) : index] if context else [],
                after=texts[index + 1 : index + 1 + context] if context else [],
            )
        )
        if max_hits is not None and len(hits) >= max_hits:
            break
    return hits
