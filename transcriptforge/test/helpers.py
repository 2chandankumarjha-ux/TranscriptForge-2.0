from typing import List, Tuple

from transcriptforge import FetchedTranscript, FetchedTranscriptSnippet


def make_transcript(
    items: List[Tuple[str, float, float]],
    video_id: str = "GJLlxj_dtq8",
    language: str = "English",
    language_code: str = "en",
    is_generated: bool = False,
) -> FetchedTranscript:
    """items: (text, start, duration)"""
    return FetchedTranscript(
        snippets=[FetchedTranscriptSnippet(t, s, d) for t, s, d in items],
        video_id=video_id,
        language=language,
        language_code=language_code,
        is_generated=is_generated,
    )


SAMPLE = [
    ("Welcome to the channel.", 0.0, 2.0),
    ("Today we talk about python", 2.0, 2.0),
    ("and about transcripts.", 4.0, 2.0),
    ("Python makes transcripts easy.", 12.0, 3.0),
    ("Thanks for watching!", 15.0, 2.0),
]

HINDI = [
    ("नमस्ते दोस्तों", 0.0, 2.0),
    ("आज हम कृष्ण की कथा सुनेंगे।", 2.0, 3.0),
    ("कृष्ण भगवान की लीला अद्भुत है", 5.0, 3.0),
]
