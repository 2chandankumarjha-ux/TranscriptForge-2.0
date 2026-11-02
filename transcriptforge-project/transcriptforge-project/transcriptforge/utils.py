import re
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from ._errors import InvalidVideoId

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_PATH_PREFIXES = ("embed", "shorts", "live", "v", "vi")
_URL_IN_TEXT_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)


def is_video_id(value: str) -> bool:
    """True if `value` has the shape of a YouTube video id (11 chars: A-Z a-z 0-9 _ -)."""
    return bool(_VIDEO_ID_RE.match(value or ""))


def _is_youtube_host(host: Optional[str]) -> bool:
    host = (host or "").lower()
    return any(host == d or host.endswith("." + d) for d in _YOUTUBE_DOMAINS)


def _parse(value: str):
    candidate = value if "://" in value else "https://" + value
    return urlparse(candidate)


def extract_video_id(value: str) -> str:
    """
    Turns a video id or any common YouTube URL into a plain video id.

    Supports ``watch?v=``, ``youtu.be/``, ``/shorts/``, ``/embed/``, ``/live/``,
    ``/v/``, mobile and music subdomains and youtube-nocookie.com.

    :raises InvalidVideoId: if no video id can be found.
    """
    value = (value or "").strip()
    if is_video_id(value):
        return value

    parsed = _parse(value)
    if _is_youtube_host(parsed.hostname):
        segments = [s for s in parsed.path.split("/") if s]
        query = parse_qs(parsed.query)
        if query.get("v") and is_video_id(query["v"][0]):
            return query["v"][0]
        if (parsed.hostname or "").lower().endswith("youtu.be") and segments:
            if is_video_id(segments[0]):
                return segments[0]
        if (
            len(segments) >= 2
            and segments[0] in _PATH_PREFIXES
            and is_video_id(segments[1])
        ):
            return segments[1]
    raise InvalidVideoId(value)


def normalize_video_id(value: str) -> str:
    """Like `extract_video_id`, but returns the input unchanged if it isn't a URL."""
    try:
        return extract_video_id(value)
    except InvalidVideoId:
        return value


def extract_video_ids(text: str) -> List[str]:
    """Finds all YouTube video URLs inside free text. Order kept, duplicates removed."""
    found: List[str] = []
    for url in _URL_IN_TEXT_RE.findall(text or ""):
        try:
            video_id = extract_video_id(url.rstrip(".,;"))
        except InvalidVideoId:
            continue
        if video_id not in found:
            found.append(video_id)
    return found


def extract_playlist_id(value: str) -> Optional[str]:
    """Returns the ``list=`` id of a YouTube URL, if any."""
    parsed = _parse((value or "").strip())
    if not _is_youtube_host(parsed.hostname):
        return None
    ids = parse_qs(parsed.query).get("list")
    return ids[0] if ids else None


def format_timestamp(seconds: float, always_hours: bool = False) -> str:
    """``75.4`` -> ``01:15``; ``3725`` -> ``1:02:05``."""
    total = int(max(seconds, 0))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours or always_hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{:02d}:{:02d}".format(minutes, secs)


def timestamp_url(video_id: str, seconds: float) -> str:
    """A deep link that opens the video at the given second."""
    return "https://youtu.be/{}?t={}".format(video_id, int(max(seconds, 0)))


def unique(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
