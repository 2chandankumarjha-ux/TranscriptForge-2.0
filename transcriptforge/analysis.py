from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from ._text import tokenize
from ._transcripts import FetchedTranscript
from .segments import Segment, to_paragraphs

ENGLISH_STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for
    from further had has have having he her here hers him his how i if in into is it its
    just me more most my no nor not now of off on once only or other our out over own same
    she should so some such than that the their them then there these they this those
    through to too under until up very was we were what when where which while who whom
    why will with would you your yours yeah okay um uh like don't it's i'm that's""".split()
)

HINDI_STOPWORDS = frozenset(
    """का की के को में से पर और या तो भी है हैं था थी थे हो हूँ हूं होता होती होते कर करना
    करके किया करते करती गया गयी गए गई जो जा जब तब कि कुछ यह ये वह वे इस उस इन उन एक
    ही नहीं ना न मैं हम तुम आप तू वो मेरा मेरी मेरे हमारा हमारी हमारे तुम्हारा आपका आपकी
    आपके अपना अपनी अपने लिए साथ बाद पहले लेकिन मगर क्योंकि अगर तक सब सभी बहुत कैसे क्या
    क्यों कौन कहाँ कहां रहा रही रहे जी अच्छा तो""".split()
)

DEFAULT_STOPWORDS = ENGLISH_STOPWORDS | HINDI_STOPWORDS


@dataclass
class TranscriptStats:
    video_id: str
    language_code: str
    is_generated: bool
    snippet_count: int
    word_count: int
    unique_word_count: int
    char_count: int
    duration_seconds: float
    words_per_minute: float
    lexical_diversity: float
    """unique words / total words (0..1); higher means a richer vocabulary."""
    longest_pause_seconds: float
    top_keywords: List[Tuple[str, int]] = field(default_factory=list)
    top_phrases: List[Tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        data = dict(self.__dict__)
        data["top_keywords"] = [list(item) for item in self.top_keywords]
        data["top_phrases"] = [list(item) for item in self.top_phrases]
        return data


def _content_tokens(
    text: str, stopwords: Iterable[str], min_word_length: int
) -> List[str]:
    stop = set(stopwords)
    return [
        token
        for token in tokenize(text)
        if len(token) >= min_word_length and token not in stop and not token.isdigit()
    ]


def extract_keywords(
    text: str,
    top_n: int = 15,
    stopwords: Optional[Iterable[str]] = None,
    min_word_length: int = 2,
) -> List[Tuple[str, int]]:
    """Most frequent non-stopword words (English + Hindi stopwords by default)."""
    stopwords = DEFAULT_STOPWORDS if stopwords is None else stopwords
    return Counter(_content_tokens(text, stopwords, min_word_length)).most_common(top_n)


def analyze_transcript(
    transcript: FetchedTranscript,
    top_n: int = 15,
    stopwords: Optional[Iterable[str]] = None,
    min_word_length: int = 2,
) -> TranscriptStats:
    """Computes word counts, speaking pace, pauses, keywords and frequent phrases."""
    stopwords = DEFAULT_STOPWORDS if stopwords is None else set(stopwords)
    text = " ".join(snippet.text for snippet in transcript)
    tokens = tokenize(text)

    duration = max((s.start + s.duration for s in transcript), default=0.0)
    longest_pause = 0.0
    for current, following in zip(transcript.snippets, transcript.snippets[1:]):
        longest_pause = max(
            longest_pause, following.start - (current.start + current.duration)
        )

    content = _content_tokens(text, stopwords, min_word_length)
    bigrams = Counter(zip(content, content[1:]))
    phrases = [
        (" ".join(pair), count) for pair, count in bigrams.most_common() if count >= 2
    ][:top_n]

    return TranscriptStats(
        video_id=transcript.video_id,
        language_code=transcript.language_code,
        is_generated=transcript.is_generated,
        snippet_count=len(transcript),
        word_count=len(tokens),
        unique_word_count=len(set(tokens)),
        char_count=len(text),
        duration_seconds=round(duration, 2),
        words_per_minute=round(len(tokens) / (duration / 60), 1)
        if duration > 0
        else 0.0,
        lexical_diversity=round(len(set(tokens)) / len(tokens), 3) if tokens else 0.0,
        longest_pause_seconds=round(max(longest_pause, 0.0), 2),
        top_keywords=Counter(content).most_common(top_n),
        top_phrases=phrases,
    )


def summarize(
    transcript: FetchedTranscript,
    passages: int = 5,
    stopwords: Optional[Iterable[str]] = None,
    max_chars: int = 300,
) -> List[Segment]:
    """
    Extractive summary: returns the `passages` most information-dense passages
    (scored by the frequency of their keywords), in the order they occur in the
    video. No model or API key needed, and it works for Hindi too.
    """
    stopwords = DEFAULT_STOPWORDS if stopwords is None else stopwords
    units = to_paragraphs(transcript, min_chars=max_chars // 2, max_chars=max_chars)
    frequencies = Counter(
        _content_tokens(" ".join(u.text for u in units), stopwords, 2)
    )

    def score(unit: Segment) -> float:
        tokens = _content_tokens(unit.text, stopwords, 2)
        if not tokens:
            return 0.0
        return sum(frequencies[t] for t in tokens) / (len(tokens) ** 0.5)

    best = sorted(units, key=score, reverse=True)[:passages]
    return sorted(best, key=lambda u: u.start)
