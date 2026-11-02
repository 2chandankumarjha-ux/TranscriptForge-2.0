from typing import Callable, Iterable, Optional, Sequence, Tuple

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from .cache import TranscriptCache
from .proxies import ProxyConfig

from ._selection import select_transcript
from ._transcripts import TranscriptListFetcher, FetchedTranscript, TranscriptList
from .utils import normalize_video_id


class TranscriptForge:
    # defaults as class attributes, so that every instance (and every subclass) has them
    _proxy_config: Optional[ProxyConfig] = None
    _cache: Optional[TranscriptCache] = None

    def __init__(
        self,
        proxy_config: Optional[ProxyConfig] = None,
        http_client: Optional[Session] = None,
        cache: Optional[TranscriptCache] = None,
    ):
        """
        Note on thread-safety: As this class will initialize a `requests.Session`
        object, it is not thread-safe. Make sure to initialize an instance of
        `TranscriptForge` per thread, if used in a multi-threading scenario! (Or just
        use `fetch_many`, which does this for you.)

        :param proxy_config: an optional ProxyConfig object, defining proxies used for
            all network requests. This can be used to work around your IP being blocked
            by YouTube, as described in the "Working around IP bans" section of the
            README.
        :param http_client: You can optionally pass in a requests.Session object, if you
            manually want to share cookies between different instances of
            `TranscriptForge`, overwrite defaults, specify SSL certificates, etc.
        :param cache: an optional `TranscriptCache`. When set, `fetch`, `fetch_best`
            and `fetch_many` serve repeated requests from disk instead of YouTube.
        """
        http_client = Session() if http_client is None else http_client
        http_client.headers.update({"Accept-Language": "en-US"})
        # Cookie auth has been temporarily disabled, as it is not working properly with
        # YouTube's most recent changes.
        # if cookie_path is not None:
        #     http_client.cookies = _load_cookie_jar(cookie_path)
        if proxy_config is not None:
            http_client.proxies = proxy_config.to_requests_dict()
            if proxy_config.prevent_keeping_connections_alive:
                http_client.headers.update({"Connection": "close"})
            if proxy_config.retries_when_blocked > 0:
                retry_config = Retry(
                    total=proxy_config.retries_when_blocked,
                    status_forcelist=[429],
                )
                http_client.mount("http://", HTTPAdapter(max_retries=retry_config))
                http_client.mount("https://", HTTPAdapter(max_retries=retry_config))
        self._proxy_config = proxy_config
        self._cache = cache
        self._fetcher = TranscriptListFetcher(http_client, proxy_config=proxy_config)

    def _clone(self, proxy_config: Optional[ProxyConfig] = None) -> "TranscriptForge":
        """A fresh instance (own HTTP session) sharing this one's cache."""
        return type(self)(proxy_config=proxy_config, cache=self._cache)

    def fetch(
        self,
        video_id: str,
        languages: Iterable[str] = ("en",),
        preserve_formatting: bool = False,
    ) -> FetchedTranscript:
        """
        Retrieves the transcript for a single video. This is just a shortcut for
        calling:
        `TranscriptForge().list(video_id).find_transcript(languages).fetch(preserve_formatting=preserve_formatting)`

        :param video_id: the video id **or a YouTube URL** (watch, youtu.be, shorts,
            embed, live ...).
        :param languages: A list of language codes in a descending priority. For
            example, if this is set to ["de", "en"] it will first try to fetch the
            german transcript (de) and then fetch the english transcript (en) if
            it fails to do so. This defaults to ["en"].
        :param preserve_formatting: whether to keep select HTML text formatting
        """
        return self._fetch_best(
            video_id,
            languages,
            preserve_formatting=preserve_formatting,
            best_effort=False,
        )[0]

    def fetch_best(
        self,
        video_id: str,
        languages: Iterable[str] = ("en",),
        preserve_formatting: bool = False,
        exclude_generated: bool = False,
        exclude_manually_created: bool = False,
        translate_to: Optional[str] = None,
        best_effort: bool = True,
    ) -> FetchedTranscript:
        """
        Like `fetch`, but smarter. If none of the requested languages exists it does
        not give up: it translates an available transcript into your first language
        (when YouTube offers that translation) or, failing that, returns whatever
        transcript exists (manually created ones first).

        :param translate_to: always translate the selected transcript into this
            language code.
        :param best_effort: set to False to get the strict behaviour of `fetch`
            (raise `NoTranscriptFound`).
        """
        return self._fetch_best(
            video_id,
            languages,
            preserve_formatting=preserve_formatting,
            exclude_generated=exclude_generated,
            exclude_manually_created=exclude_manually_created,
            translate_to=translate_to,
            best_effort=best_effort,
        )[0]

    def _fetch_best(
        self,
        video_id: str,
        languages: Iterable[str],
        preserve_formatting: bool = False,
        exclude_generated: bool = False,
        exclude_manually_created: bool = False,
        translate_to: Optional[str] = None,
        best_effort: bool = False,
    ) -> Tuple[FetchedTranscript, bool]:
        """Returns (transcript, served_from_cache)."""
        video_id = normalize_video_id(video_id)
        languages = list(languages)
        key = None
        if self._cache is not None:
            key = TranscriptCache.make_key(
                video_id,
                languages,
                preserve_formatting,
                translate_to,
                variant="{}{}{}".format(
                    "g" if exclude_generated else "",
                    "m" if exclude_manually_created else "",
                    "b" if best_effort else "",
                ),
            )
            cached = self._cache.get(key)
            if cached is not None:
                return cached, True

        transcript_list = self.list(video_id)
        selected = select_transcript(
            transcript_list,
            languages,
            exclude_generated=exclude_generated,
            exclude_manually_created=exclude_manually_created,
            translate_to=translate_to,
            best_effort=best_effort,
        )
        fetched = selected.fetch(preserve_formatting=preserve_formatting)
        if key is not None and self._cache is not None:
            self._cache.set(key, fetched)
        return fetched, False

    def fetch_many(
        self,
        video_ids: Iterable[str],
        languages: Iterable[str] = ("en",),
        preserve_formatting: bool = False,
        exclude_generated: bool = False,
        exclude_manually_created: bool = False,
        translate_to: Optional[str] = None,
        best_effort: bool = True,
        workers: int = 4,
        retries: int = 2,
        backoff: float = 2.0,
        min_delay: float = 0.0,
        proxy_pool: Optional[Sequence[ProxyConfig]] = None,
        on_progress: Optional[Callable[[int, int, "object"], None]] = None,
    ):
        """
        Fetches many transcripts in parallel and returns a `BatchReport`.

        - one failing video never stops the others; every video gets a `BatchResult`
          holding either the transcript or the error
        - temporary blocks (`RequestBlocked`, `IpBlocked`, `YouTubeRequestFailed`)
          are retried with exponential backoff; with a `proxy_pool` each retry
          switches to the next proxy
        - results are returned in the order of `video_ids`
        - each worker thread has its own HTTP session (this class isn't thread-safe)

        :param workers: number of parallel threads. Keep this low (2-5) unless you use
            rotating proxies, or YouTube will block you.
        :param retries: extra attempts per video for retryable errors.
        :param backoff: base seconds for the exponential backoff between retries.
        :param min_delay: minimum seconds between two requests of the same worker.
        :param on_progress: called as ``on_progress(done, total, result)`` after each
            video (from the calling thread).
        """
        from .batch import fetch_many

        return fetch_many(
            self,
            video_ids,
            languages,
            preserve_formatting=preserve_formatting,
            exclude_generated=exclude_generated,
            exclude_manually_created=exclude_manually_created,
            translate_to=translate_to,
            best_effort=best_effort,
            workers=workers,
            retries=retries,
            backoff=backoff,
            min_delay=min_delay,
            proxy_pool=proxy_pool,
            on_progress=on_progress,
        )

    async def afetch_many(self, video_ids: Iterable[str], *args, **kwargs):
        """asyncio version of `fetch_many` (runs in a thread, doesn't block the loop)."""
        from .batch import afetch_many

        return await afetch_many(self, video_ids, *args, **kwargs)

    def list(
        self,
        video_id: str,
    ) -> TranscriptList:
        """
        Retrieves the list of transcripts which are available for a given video. It
        returns a `TranscriptList` object which is iterable and provides methods to
        filter the list of transcripts for specific languages. While iterating over
        the `TranscriptList` the individual transcripts are represented by
        `Transcript` objects, which provide metadata and can either be fetched by
        calling `transcript.fetch()` or translated by calling `transcript.translate(
        'en')`. Example:

        ```
        forge = TranscriptForge()

        # retrieve the available transcripts
        transcript_list = forge.list('video_id')

        # iterate over all available transcripts
        for transcript in transcript_list:
            # the Transcript object provides metadata properties
            print(
                transcript.video_id,
                transcript.language,
                transcript.language_code,
                # whether it has been manually created or generated by YouTube
                transcript.is_generated,
                # a list of languages the transcript can be translated to
                transcript.translation_languages,
            )

            # fetch the actual transcript data
            print(transcript.fetch())

            # translating the transcript will return another transcript object
            print(transcript.translate('en').fetch())

        # you can also directly filter for the language you are looking for, using the transcript list
        transcript = transcript_list.find_transcript(['de', 'en'])

        # or just filter for manually created transcripts
        transcript = transcript_list.find_manually_created_transcript(['de', 'en'])

        # or automatically generated ones
        transcript = transcript_list.find_generated_transcript(['de', 'en'])
        ```

        :param video_id: the video id **or a YouTube URL** of the video.
        """
        return self._fetcher.fetch(normalize_video_id(video_id))
