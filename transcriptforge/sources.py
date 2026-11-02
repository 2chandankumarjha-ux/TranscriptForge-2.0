import re
from typing import List, Optional

from requests import RequestException, Session

from ._errors import InvalidVideoId, TranscriptForgeError
from .utils import _is_youtube_host, _parse, extract_video_id, unique

_RENDERER_RE = re.compile(
    r'"(?:playlistVideoRenderer|gridVideoRenderer|videoRenderer|reelItemRenderer)"'
    r'\s*:\s*\{\s*"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"'
)
_ANY_VIDEO_ID_RE = re.compile(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"')
_CHANNEL_PREFIXES = ("channel", "c", "user")


class SourceError(TranscriptForgeError):
    """Raised when a playlist / channel page could not be expanded into video ids."""


def is_listing_url(value: str) -> bool:
    """True for playlist and channel/handle URLs (which contain many videos)."""
    parsed = _parse(value.strip())
    if not _is_youtube_host(parsed.hostname):
        return False
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return False
    return (
        segments[0] == "playlist"
        or segments[0].startswith("@")
        or segments[0] in _CHANNEL_PREFIXES
    )


def _listing_page_url(value: str) -> str:
    parsed = _parse(value.strip())
    segments = [s for s in parsed.path.split("/") if s]
    if segments and segments[0] == "playlist":
        url = "https://www.youtube.com/playlist"
        return url + "?" + parsed.query if parsed.query else url
    # A channel is "/@handle" (1 segment) or "/channel|c|user/<name>" (2 segments).
    # Anything after that is a tab (featured, about, playlists, ...): only the video
    # listing tabs are kept, every other tab is replaced by "/videos".
    root = segments[:1] if segments and segments[0].startswith("@") else segments[:2]
    tab = segments[len(root)] if len(segments) > len(root) else "videos"
    if tab not in ("videos", "streams", "shorts"):
        tab = "videos"
    return "https://www.youtube.com/" + "/".join(root + [tab])


def expand_source(
    source: str,
    http_client: Optional[Session] = None,
    limit: Optional[int] = None,
) -> List[str]:
    """
    Turns a video id/URL, a playlist URL or a channel URL into a list of video ids.

    Playlist and channel expansion reads the first page YouTube serves (roughly the
    first 30-100 videos); it is best effort and does not follow "load more"
    continuations. For bigger jobs, export the ids and pass them with ``--file``.

    :raises SourceError: if the page can't be loaded or contains no videos.
    """
    source = source.strip()
    if not is_listing_url(source):
        try:
            return [extract_video_id(source)]
        except InvalidVideoId:
            return [source]

    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0 (0 means no limit)")

    session = http_client or Session()
    session.headers.setdefault("Accept-Language", "en-US")
    url = _listing_page_url(source)
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
    except RequestException as exception:
        raise SourceError("Could not load {}: {}".format(url, exception)) from exception

    ids = unique(_RENDERER_RE.findall(response.text)) or unique(
        _ANY_VIDEO_ID_RE.findall(response.text)
    )
    if not ids:
        raise SourceError(
            "No videos found at {}. The page may require consent/login or be empty.".format(
                url
            )
        )
    return ids[:limit] if limit else ids
