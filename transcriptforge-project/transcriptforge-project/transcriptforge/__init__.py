# ruff: noqa: F401
from ._api import TranscriptForge
from ._transcripts import (
    TranscriptList,
    Transcript,
    FetchedTranscript,
    FetchedTranscriptSnippet,
)
from ._errors import (
    TranscriptForgeError,
    CookieError,
    CookiePathInvalid,
    CookieInvalid,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
    VideoUnavailable,
    VideoUnplayable,
    IpBlocked,
    RequestBlocked,
    NotTranslatable,
    TranslationLanguageNotAvailable,
    FailedToCreateConsentCookie,
    YouTubeRequestFailed,
    InvalidVideoId,
    AgeRestricted,
    YouTubeDataUnparsable,
    PoTokenRequired,
)
from .analysis import TranscriptStats, analyze_transcript, extract_keywords, summarize
from .batch import BatchReport, BatchResult, afetch_many, fetch_many
from .cache import (
    TranscriptCache,
    load_transcript_json,
    save_transcript_json,
)
from .cleaning import clean_text, clean_transcript
from .export import make_zip, save_many, save_transcript, write_report_csv
from .formatters import FormatterLoader
from .proxies import GenericProxyConfig, WebshareProxyConfig
from .search import SearchHit, search_transcript
from .segments import Segment, chunk_by_chars, chunk_by_time, to_paragraphs
from .sources import SourceError, expand_source
from .utils import extract_video_id, extract_video_ids, format_timestamp, timestamp_url

__version__ = "2.0.0"

# Backwards compatible names of the upstream `youtube-transcript-api` project.
YouTubeTranscriptApi = TranscriptForge
YouTubeTranscriptApiException = TranscriptForgeError

__all__ = [
    "TranscriptForge",
    "TranscriptList",
    "Transcript",
    "FetchedTranscript",
    "FetchedTranscriptSnippet",
    "TranscriptForgeError",
    "CookieError",
    "CookiePathInvalid",
    "CookieInvalid",
    "TranscriptsDisabled",
    "NoTranscriptFound",
    "CouldNotRetrieveTranscript",
    "VideoUnavailable",
    "VideoUnplayable",
    "IpBlocked",
    "RequestBlocked",
    "NotTranslatable",
    "TranslationLanguageNotAvailable",
    "FailedToCreateConsentCookie",
    "YouTubeRequestFailed",
    "InvalidVideoId",
    "AgeRestricted",
    "YouTubeDataUnparsable",
    "PoTokenRequired",
    "TranscriptStats",
    "analyze_transcript",
    "extract_keywords",
    "summarize",
    "BatchReport",
    "BatchResult",
    "afetch_many",
    "fetch_many",
    "TranscriptCache",
    "load_transcript_json",
    "save_transcript_json",
    "clean_text",
    "clean_transcript",
    "make_zip",
    "save_many",
    "save_transcript",
    "write_report_csv",
    "FormatterLoader",
    "GenericProxyConfig",
    "WebshareProxyConfig",
    "SearchHit",
    "search_transcript",
    "Segment",
    "chunk_by_chars",
    "chunk_by_time",
    "to_paragraphs",
    "SourceError",
    "expand_source",
    "extract_video_id",
    "extract_video_ids",
    "format_timestamp",
    "timestamp_url",
    "YouTubeTranscriptApi",
    "YouTubeTranscriptApiException",
]
