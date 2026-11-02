from typing import Iterable, List, Optional

from ._errors import NoTranscriptFound
from ._transcripts import Transcript, TranscriptList


def select_transcript(
    transcript_list: TranscriptList,
    languages: Iterable[str],
    exclude_generated: bool = False,
    exclude_manually_created: bool = False,
    translate_to: Optional[str] = None,
    best_effort: bool = False,
) -> Transcript:
    """
    Picks the transcript to fetch from a `TranscriptList`.

    :param best_effort: if none of the requested languages exists, fall back to
        translating an available transcript into the first requested language (when
        YouTube offers that translation) and, failing that, to any available
        transcript. Without this flag `NoTranscriptFound` is raised, as before.
    """
    if exclude_generated and exclude_manually_created:
        raise ValueError(
            "exclude_generated and exclude_manually_created cannot both be set: "
            "that would exclude every transcript"
        )
    languages = list(languages)
    try:
        if exclude_manually_created:
            transcript = transcript_list.find_generated_transcript(languages)
        elif exclude_generated:
            transcript = transcript_list.find_manually_created_transcript(languages)
        else:
            transcript = transcript_list.find_transcript(languages)
    except NoTranscriptFound:
        if not best_effort:
            raise
        transcript = _best_effort(
            transcript_list, languages, exclude_generated, exclude_manually_created
        )

    if translate_to and transcript.language_code != translate_to:
        transcript = transcript.translate(translate_to)
    return transcript


def _best_effort(
    transcript_list: TranscriptList,
    languages: List[str],
    exclude_generated: bool,
    exclude_manually_created: bool,
) -> Transcript:
    candidates = [
        t
        for t in transcript_list
        if not (exclude_generated and t.is_generated)
        and not (exclude_manually_created and not t.is_generated)
    ]
    # manually created transcripts are more accurate, so they are tried first
    candidates.sort(key=lambda t: t.is_generated)

    for target in languages:
        for candidate in candidates:
            if candidate.is_translatable and target in {
                language.language_code for language in candidate.translation_languages
            }:
                return candidate.translate(target)

    if candidates:
        return candidates[0]
    # nothing usable: re-raise the original "no transcript" error in a natural way
    raise NoTranscriptFound(
        getattr(transcript_list, "video_id", ""), languages, transcript_list
    )
