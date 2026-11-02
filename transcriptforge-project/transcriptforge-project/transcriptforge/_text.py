"""Unicode-aware text helpers shared by the analysis, search and cleaning modules.

Python's ``\\w`` does not match Devanagari vowel signs (matras) and other combining
marks, so naive tokenizing splits Hindi/Sanskrit words in the middle. The character
class below fixes that while still excluding the danda (।) and double danda (॥),
which are sentence punctuation, not letters.
"""

import re
from typing import List

#: Characters that can be part of a word (Latin, Devanagari incl. matras, digits, ...).
WORD_CHARS = r"\w\u0900-\u0963\u0966-\u097F"

#: A word, optionally containing inner apostrophes ("don't", "it's").
WORD_RE = re.compile("[" + WORD_CHARS + "]+(?:['\u2019][" + WORD_CHARS + "]+)*")

#: Characters that end a sentence (Latin + Devanagari danda + ellipsis).
SENTENCE_END_CHARS = ".?!\u0964\u0965\u2026"


def tokenize(text: str, lowercase: bool = True) -> List[str]:
    """Splits text into word tokens in a Unicode/Devanagari-safe way."""
    return WORD_RE.findall(text.lower() if lowercase else text)


def ends_sentence(text: str) -> bool:
    stripped = text.rstrip().rstrip("\"')]\u201d\u2019")
    return bool(stripped) and stripped[-1] in SENTENCE_END_CHARS
