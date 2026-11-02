import asyncio
import functools
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout

from ._errors import IpBlocked, RequestBlocked, YouTubeRequestFailed
from ._transcripts import FetchedTranscript
from .proxies import ProxyConfig

#: Errors that are worth retrying (temporary blocks / network trouble). Everything
#: else (disabled transcripts, private video, ...) will not change on retry.
RETRYABLE_ERRORS = (
    IpBlocked,
    RequestBlocked,
    YouTubeRequestFailed,
    RequestsConnectionError,
    Timeout,
)

_sleep = time.sleep  # indirection so tests can run without waiting


@dataclass
class BatchResult:
    video_id: str
    transcript: Optional[FetchedTranscript] = None
    error: Optional[BaseException] = None
    attempts: int = 1
    elapsed: float = 0.0
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return self.transcript is not None

    @property
    def error_type(self) -> str:
        return type(self.error).__name__ if self.error is not None else ""

    def to_dict(self) -> Dict:
        return {
            "video_id": self.video_id,
            "ok": self.ok,
            "language_code": self.transcript.language_code if self.transcript else None,
            "is_generated": self.transcript.is_generated if self.transcript else None,
            "snippets": len(self.transcript) if self.transcript else 0,
            "error_type": self.error_type,
            "error": str(self.error).strip() if self.error is not None else "",
            "attempts": self.attempts,
            "from_cache": self.from_cache,
            "elapsed": round(self.elapsed, 3),
        }


@dataclass
class BatchReport:
    results: List[BatchResult]
    elapsed: float = 0.0

    @property
    def succeeded(self) -> List[BatchResult]:
        return [r for r in self.results if r.ok]

    @property
    def failed(self) -> List[BatchResult]:
        return [r for r in self.results if not r.ok]

    @property
    def transcripts(self) -> List[FetchedTranscript]:
        return [r.transcript for r in self.results if r.transcript is not None]

    def error_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for result in self.failed:
            counts[result.error_type] = counts.get(result.error_type, 0) + 1
        return counts

    def summary(self) -> str:
        line = "{ok}/{total} transcripts fetched in {sec:.1f}s ({cached} from cache)".format(
            ok=len(self.succeeded),
            total=len(self.results),
            sec=self.elapsed,
            cached=sum(1 for r in self.results if r.from_cache),
        )
        if self.failed:
            line += "; failed: " + ", ".join(
                "{} x{}".format(name, n)
                for name, n in sorted(self.error_counts().items())
            )
        return line

    def to_dict(self) -> Dict:
        return {
            "summary": self.summary(),
            "elapsed": round(self.elapsed, 3),
            "results": [r.to_dict() for r in self.results],
        }


def fetch_many(
    forge,
    video_ids: Iterable[str],
    languages: Iterable[str] = ("en",),
    preserve_formatting: bool = False,
    exclude_generated: bool = False,
    exclude_manually_created: bool = False,
    translate_to: Optional[str] = None,
    best_effort: bool = False,
    workers: int = 1,
    retries: int = 2,
    backoff: float = 2.0,
    min_delay: float = 0.0,
    proxy_pool: Optional[Sequence[ProxyConfig]] = None,
    on_progress: Optional[Callable[[int, int, BatchResult], None]] = None,
) -> BatchReport:
    """
    Fetches many transcripts (see `TranscriptForge.fetch_many` for the docs).
    Results keep the order of `video_ids`; one failing video never stops the rest.
    """
    video_ids = list(video_ids)
    languages = list(languages)
    workers = max(1, int(workers))
    retries = max(0, int(retries))
    pool = list(proxy_pool) if proxy_pool else []
    local = threading.local()
    counter_lock = threading.Lock()
    next_worker_slot = [0]

    def new_client(proxy_index: int):
        if workers == 1 and not pool:
            return forge  # honours a custom http_client the caller configured
        return forge._clone(
            pool[proxy_index % len(pool)] if pool else forge._proxy_config
        )

    def client_for_thread():
        if not hasattr(local, "client"):
            with counter_lock:
                local.proxy_index = next_worker_slot[0]
                next_worker_slot[0] += 1
            local.client = new_client(local.proxy_index)
            local.last_request = 0.0
        return local

    def work(video_id: str) -> BatchResult:
        started = time.monotonic()
        state = client_for_thread()
        last_error: Optional[BaseException] = None
        attempts = 0
        for attempt in range(1, retries + 2):
            attempts = attempt
            wait = min_delay - (time.monotonic() - state.last_request)
            if wait > 0:
                _sleep(wait)
            state.last_request = time.monotonic()
            try:
                transcript, from_cache = state.client._fetch_best(
                    video_id,
                    languages,
                    preserve_formatting=preserve_formatting,
                    exclude_generated=exclude_generated,
                    exclude_manually_created=exclude_manually_created,
                    translate_to=translate_to,
                    best_effort=best_effort,
                )
                return BatchResult(
                    video_id,
                    transcript,
                    None,
                    attempts,
                    time.monotonic() - started,
                    from_cache,
                )
            except RETRYABLE_ERRORS as exception:
                last_error = exception
                if attempt > retries:
                    break
                if pool:  # a blocked IP: switch to the next proxy of the pool
                    state.proxy_index += 1
                    state.client = new_client(state.proxy_index)
                _sleep(backoff * (2 ** (attempt - 1)) * (1 + random.random() * 0.25))
            except Exception as exception:  # noqa: BLE001 - reported per video
                last_error = exception
                break
        return BatchResult(
            video_id, None, last_error, attempts, time.monotonic() - started
        )

    started_all = time.monotonic()
    results: List[Optional[BatchResult]] = [None] * len(video_ids)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(work, vid): i for i, vid in enumerate(video_ids)}
        for future in as_completed(futures):
            result = future.result()
            results[futures[future]] = result
            done += 1
            if on_progress is not None:
                on_progress(done, len(video_ids), result)
    return BatchReport(
        [r for r in results if r is not None], time.monotonic() - started_all
    )


async def afetch_many(forge, *args, **kwargs) -> BatchReport:
    """asyncio wrapper: runs `fetch_many` in a worker thread without blocking the loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(fetch_many, forge, *args, **kwargs)
    )
