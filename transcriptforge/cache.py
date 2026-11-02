import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Union

from ._transcripts import FetchedTranscript, FetchedTranscriptSnippet

_FORMAT_VERSION = 1


def transcript_to_dict(transcript: FetchedTranscript) -> Dict:
    return {
        "video_id": transcript.video_id,
        "language": transcript.language,
        "language_code": transcript.language_code,
        "is_generated": transcript.is_generated,
        "snippets": transcript.to_raw_data(),
    }


def transcript_from_dict(data: Dict) -> FetchedTranscript:
    return FetchedTranscript(
        snippets=[
            FetchedTranscriptSnippet(
                text=s["text"], start=float(s["start"]), duration=float(s["duration"])
            )
            for s in data["snippets"]
        ],
        video_id=data["video_id"],
        language=data["language"],
        language_code=data["language_code"],
        is_generated=bool(data["is_generated"]),
    )


def save_transcript_json(transcript: FetchedTranscript, path: Union[str, Path]) -> Path:
    """Writes a transcript as UTF-8 JSON (Hindi/Sanskrit stays readable)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(transcript_to_dict(transcript), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_transcript_json(path: Union[str, Path]) -> FetchedTranscript:
    """Loads a transcript written by `save_transcript_json` or the cache."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return transcript_from_dict(data.get("transcript", data))


class TranscriptCache:
    """
    A small on-disk cache so the same transcript is never downloaded twice. It is
    safe to share between threads and processes (writes are atomic).

    :param directory: where the JSON files are stored (created if missing).
    :param ttl_seconds: how long an entry stays valid. `None` keeps entries forever.
    """

    def __init__(
        self,
        directory: Union[str, Path],
        ttl_seconds: Optional[float] = 7 * 24 * 3600,
        clock: Callable[[], float] = time.time,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._clock = clock

    @staticmethod
    def make_key(
        video_id: str,
        languages: Iterable[str] = ("en",),
        preserve_formatting: bool = False,
        translate_to: Optional[str] = None,
        variant: str = "",
    ) -> str:
        """The requested language *order* matters, so it is part of the key."""
        raw = "|".join(
            [
                ",".join(languages),
                "fmt" if preserve_formatting else "plain",
                translate_to or "",
                variant,
            ]
        )
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return "{}-{}".format(video_id, digest)

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.directory / (safe + ".json")

    def get(self, key: str) -> Optional[FetchedTranscript]:
        path = self._path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") != _FORMAT_VERSION:
                return None
            if self.ttl_seconds is not None and (
                self._clock() - float(payload["cached_at"]) > self.ttl_seconds
            ):
                return None
            return transcript_from_dict(payload["transcript"])
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            # corrupt entry: behave like a miss and let the next set() overwrite it
            return None

    def set(self, key: str, transcript: FetchedTranscript) -> None:
        payload = {
            "version": _FORMAT_VERSION,
            "cached_at": self._clock(),
            "transcript": transcript_to_dict(transcript),
        }
        fd, tmp_name = tempfile.mkstemp(dir=str(self.directory), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(tmp_name, self._path(key))
        except BaseException:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise

    def delete(self, key: str) -> bool:
        try:
            self._path(key).unlink()
            return True
        except FileNotFoundError:
            return False

    def purge_expired(self) -> int:
        """Removes expired / unreadable entries and returns how many were removed."""
        removed = 0
        for path in self.directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                expired = self.ttl_seconds is not None and (
                    self._clock() - float(payload["cached_at"]) > self.ttl_seconds
                )
            except (ValueError, KeyError, TypeError, OSError):
                expired = True
            if expired:
                path.unlink()
                removed += 1
        return removed

    def clear(self) -> int:
        count = 0
        for path in self.directory.glob("*.json"):
            path.unlink()
            count += 1
        return count

    def __len__(self) -> int:
        return sum(1 for _ in self.directory.glob("*.json"))
