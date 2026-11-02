from dataclasses import asdict, dataclass
from typing import Dict, List

from ._text import ends_sentence
from ._transcripts import FetchedTranscript, FetchedTranscriptSnippet
from .utils import format_timestamp, timestamp_url


@dataclass
class Segment:
    """A time-ranged piece of a transcript (a paragraph or a chunk)."""

    index: int
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start

    def link(self, video_id: str) -> str:
        """Deep link to the start of this segment."""
        return timestamp_url(video_id, self.start)

    @property
    def timestamp(self) -> str:
        return format_timestamp(self.start)

    def to_dict(self) -> Dict:
        return asdict(self)


def _end(snippet: FetchedTranscriptSnippet) -> float:
    return snippet.start + snippet.duration


def to_paragraphs(
    transcript: FetchedTranscript,
    max_gap: float = 1.5,
    min_chars: int = 120,
    max_chars: int = 700,
) -> List[Segment]:
    """
    Groups the many tiny caption snippets into readable paragraphs.

    A new paragraph starts when there is a pause longer than `max_gap` seconds,
    when the text reached `max_chars`, or when a sentence ends (., ?, !, ।) and the
    paragraph already has at least `min_chars` characters.
    """
    paragraphs: List[Segment] = []
    parts: List[str] = []
    start = 0.0
    end = 0.0
    length = 0

    def flush() -> None:
        nonlocal parts, length
        if parts:
            paragraphs.append(Segment(len(paragraphs), start, end, " ".join(parts)))
        parts, length = [], 0

    for snippet in transcript:
        text = snippet.text.strip()
        if not text:
            continue
        if parts:
            gap = snippet.start - end
            if (
                gap > max_gap
                or length >= max_chars
                or (length >= min_chars and ends_sentence(parts[-1]))
            ):
                flush()
        if not parts:
            start = snippet.start
        parts.append(text)
        length += len(text) + 1
        end = max(end, _end(snippet)) if length > len(text) + 1 else _end(snippet)
    flush()
    return paragraphs


def chunk_by_time(
    transcript: FetchedTranscript,
    window_seconds: float = 60.0,
    overlap_seconds: float = 0.0,
) -> List[Segment]:
    """Splits a transcript into fixed time windows (optionally overlapping)."""
    if window_seconds <= 0:
        raise ValueError("window_seconds must be > 0")
    if not 0 <= overlap_seconds < window_seconds:
        raise ValueError("overlap_seconds must be >= 0 and < window_seconds")

    step = window_seconds - overlap_seconds
    windows: Dict[int, List[FetchedTranscriptSnippet]] = {}
    for snippet in transcript:
        if not snippet.text.strip():
            continue
        last = int(snippet.start // step)
        first = max(0, int((snippet.start - window_seconds) // step) + 1)
        for k in range(first, last + 1):
            if k * step <= snippet.start < k * step + window_seconds:
                windows.setdefault(k, []).append(snippet)

    chunks = []
    for k in sorted(windows):
        items = windows[k]
        chunks.append(
            Segment(
                len(chunks),
                items[0].start,
                max(_end(s) for s in items),
                " ".join(s.text.strip() for s in items),
            )
        )
    return chunks


def chunk_by_chars(
    transcript: FetchedTranscript, max_chars: int = 1000, overlap_chars: int = 0
) -> List[Segment]:
    """
    Splits a transcript into chunks of roughly `max_chars` characters that always
    break between snippets, each carrying its start/end timestamps. This is the
    layout you want for embeddings / RAG / LLM context windows.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    if not 0 <= overlap_chars < max_chars:
        raise ValueError("overlap_chars must be >= 0 and < max_chars")

    snippets = [s for s in transcript if s.text.strip()]
    chunks: List[Segment] = []
    i = 0
    while i < len(snippets):
        j = i
        length = 0
        while j < len(snippets) and (
            j == i or length + len(snippets[j].text) + 1 <= max_chars
        ):
            length += len(snippets[j].text) + 1
            j += 1
        group = snippets[i:j]
        chunks.append(
            Segment(
                len(chunks),
                group[0].start,
                max(_end(s) for s in group),
                " ".join(s.text.strip() for s in group),
            )
        )
        if j >= len(snippets):
            break
        # step back far enough to create the requested overlap, but always advance
        next_i = j
        carried = 0
        while (
            next_i - 1 > i
            and carried + len(snippets[next_i - 1].text) + 1 <= overlap_chars
        ):
            next_i -= 1
            carried += len(snippets[next_i].text) + 1
        i = next_i
    return chunks
