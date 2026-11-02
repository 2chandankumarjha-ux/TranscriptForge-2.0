import asyncio
import json
import threading
import zipfile

import pytest
import responses

from transcriptforge import (
    BatchReport,
    BatchResult,
    IpBlocked,
    SourceError,
    TranscriptCache,
    VideoUnavailable,
    expand_source,
    fetch_many,
    load_transcript_json,
    make_zip,
    save_transcript_json,
    write_report_csv,
)
from transcriptforge import batch as batch_module
from transcriptforge.cache import transcript_from_dict, transcript_to_dict

from .helpers import HINDI, SAMPLE, make_transcript


# --------------------------------------------------------------------- cache
def test_serialization_roundtrip_keeps_hindi(tmp_path):
    original = make_transcript(HINDI, language="Hindi", language_code="hi")
    assert transcript_from_dict(transcript_to_dict(original)) == original

    path = save_transcript_json(original, tmp_path / "sub" / "t.json")
    assert "नमस्ते" in path.read_text(encoding="utf-8")  # not \u-escaped
    assert load_transcript_json(path) == original


def test_cache_set_get_delete_clear(tmp_path):
    cache = TranscriptCache(tmp_path / "c")
    transcript = make_transcript(SAMPLE)
    key = TranscriptCache.make_key("GJLlxj_dtq8", ["en"])
    assert cache.get(key) is None
    cache.set(key, transcript)
    assert cache.get(key) == transcript
    assert len(cache) == 1
    assert cache.delete(key) is True
    assert cache.delete(key) is False
    cache.set(key, transcript)
    assert cache.clear() == 1 and len(cache) == 0


def test_cache_key_depends_on_request_parameters():
    base = TranscriptCache.make_key("vid", ["de", "en"])
    assert base != TranscriptCache.make_key("vid", ["en", "de"])
    assert base != TranscriptCache.make_key(
        "vid", ["de", "en"], preserve_formatting=True
    )
    assert base != TranscriptCache.make_key("vid", ["de", "en"], translate_to="hi")
    assert base != TranscriptCache.make_key("vid", ["de", "en"], variant="b")
    assert base == TranscriptCache.make_key("vid", ("de", "en"))


def test_cache_ttl_and_purge(tmp_path):
    now = [1000.0]
    cache = TranscriptCache(tmp_path, ttl_seconds=60, clock=lambda: now[0])
    cache.set("a", make_transcript(SAMPLE))
    now[0] = 1050.0
    assert cache.get("a") is not None
    now[0] = 1100.0
    assert cache.get("a") is None
    assert cache.purge_expired() == 1 and len(cache) == 0


def test_cache_without_ttl_never_expires(tmp_path):
    now = [0.0]
    cache = TranscriptCache(tmp_path, ttl_seconds=None, clock=lambda: now[0])
    cache.set("a", make_transcript(SAMPLE))
    now[0] = 10**9
    assert cache.get("a") is not None
    assert cache.purge_expired() == 0


def test_cache_ignores_corrupt_and_foreign_version_entries(tmp_path):
    cache = TranscriptCache(tmp_path)
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert cache.get("bad") is None
    (tmp_path / "old.json").write_text(json.dumps({"version": 0}), encoding="utf-8")
    assert cache.get("old") is None
    assert cache.purge_expired() == 2


def test_cache_set_cleans_up_temp_file_on_error(tmp_path, monkeypatch):
    cache = TranscriptCache(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("transcriptforge.cache.os.replace", boom)
    with pytest.raises(OSError):
        cache.set("a", make_transcript(SAMPLE))
    assert list(tmp_path.glob("*.tmp")) == []


# --------------------------------------------------------------------- batch
class FakeForge:
    """Stands in for TranscriptForge: scripted results per video id."""

    _proxy_config = None

    def __init__(self, script, shared=None):
        self.script = script
        self.shared = (
            shared
            if shared is not None
            else {"calls": {}, "clones": [], "lock": threading.Lock()}
        )
        self.proxy = None

    def _clone(self, proxy_config=None):
        clone = FakeForge(self.script, self.shared)
        clone.proxy = proxy_config
        with self.shared["lock"]:
            self.shared["clones"].append(proxy_config)
        return clone

    def _fetch_best(self, video_id, languages, **kwargs):
        with self.shared["lock"]:
            self.shared["calls"].setdefault(video_id, []).append((self.proxy, kwargs))
            step = self.script[video_id]
            outcome = (
                step.pop(0)
                if isinstance(step, list) and len(step) > 1
                else (step[0] if isinstance(step, list) else step)
            )
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome, False


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(batch_module, "_sleep", recorded.append)
    return recorded


def test_fetch_many_keeps_order_and_isolates_failures(sleeps):
    t = make_transcript(SAMPLE)
    forge = FakeForge({"a": [t], "b": [VideoUnavailable("b")], "c": [t]})
    report = fetch_many(forge, ["a", "b", "c"], ["en"], workers=3)
    assert [r.video_id for r in report.results] == ["a", "b", "c"]
    assert [r.ok for r in report.results] == [True, False, True]
    assert report.results[1].attempts == 1  # not retryable
    assert report.error_counts() == {"VideoUnavailable": 1}
    assert len(report.transcripts) == 2 and len(report.failed) == 1
    assert (
        "2/3 transcripts fetched" in report.summary()
        and "VideoUnavailable x1" in report.summary()
    )
    assert sleeps == []


def test_fetch_many_retries_blocked_requests_with_backoff(sleeps):
    t = make_transcript(SAMPLE)
    forge = FakeForge({"a": [IpBlocked("a"), IpBlocked("a"), t]})
    report = fetch_many(forge, ["a"], retries=2, backoff=2.0)
    assert report.results[0].ok and report.results[0].attempts == 3
    assert len(sleeps) == 2 and sleeps[0] >= 2.0 and sleeps[1] >= 4.0


def test_fetch_many_retries_network_errors(sleeps):
    import requests

    t = make_transcript(SAMPLE)
    forge = FakeForge(
        {"a": [requests.ConnectionError("dns"), requests.Timeout("slow"), t]}
    )
    result = fetch_many(forge, ["a"], retries=2).results[0]
    assert result.ok and result.attempts == 3


def test_fetch_many_gives_up_after_retries(sleeps):
    forge = FakeForge({"a": [IpBlocked("a")]})
    report = fetch_many(forge, ["a"], retries=1)
    result = report.results[0]
    assert not result.ok and result.attempts == 2 and result.error_type == "IpBlocked"
    assert forge.shared["calls"]["a"].__len__() == 2


def test_fetch_many_with_retries_zero_does_not_retry(sleeps):
    forge = FakeForge({"a": [IpBlocked("a")]})
    assert fetch_many(forge, ["a"], retries=0).results[0].attempts == 1


def test_fetch_many_rotates_through_proxy_pool_on_block(sleeps):
    t = make_transcript(SAMPLE)
    forge = FakeForge({"a": [IpBlocked("a"), t]})
    report = fetch_many(forge, ["a"], proxy_pool=["p0", "p1", "p2"], retries=2)
    assert report.results[0].ok
    assert [proxy for proxy, _ in forge.shared["calls"]["a"]] == ["p0", "p1"]


def test_fetch_many_spreads_workers_over_proxy_pool(sleeps):
    t = make_transcript(SAMPLE)
    forge = FakeForge({v: [t] for v in "abcd"})
    fetch_many(forge, list("abcd"), proxy_pool=["p0", "p1"], workers=2)
    assert set(forge.shared["clones"]) <= {"p0", "p1"}


def test_fetch_many_single_worker_uses_original_instance(sleeps):
    t = make_transcript(SAMPLE)
    forge = FakeForge({"a": [t]})
    fetch_many(forge, ["a"], workers=1)
    assert forge.shared["clones"] == []


def test_fetch_many_min_delay_and_progress_and_kwargs(sleeps):
    t = make_transcript(SAMPLE)
    forge = FakeForge({"a": [t], "b": [t]})
    seen = []
    fetch_many(
        forge,
        ["a", "b"],
        ["hi", "en"],
        min_delay=5.0,
        translate_to="hi",
        best_effort=True,
        exclude_generated=True,
        preserve_formatting=True,
        on_progress=lambda done, total, result: seen.append(
            (done, total, result.video_id)
        ),
    )
    assert [s[:2] for s in seen] == [(1, 2), (2, 2)]
    assert sleeps and all(
        s > 0 for s in sleeps
    )  # 2nd request of the single worker waits
    kwargs = forge.shared["calls"]["a"][0][1]
    assert (
        kwargs["translate_to"] == "hi"
        and kwargs["best_effort"]
        and kwargs["exclude_generated"]
    )


def test_fetch_many_unexpected_error_is_captured(sleeps):
    forge = FakeForge({"a": [RuntimeError("boom")]})
    result = fetch_many(forge, ["a"]).results[0]
    assert not result.ok and result.error_type == "RuntimeError"


def test_batch_result_and_report_serialization(tmp_path):
    t = make_transcript(SAMPLE)
    report = BatchReport(
        [
            BatchResult("a", transcript=t, from_cache=True),
            BatchResult("b", error=VideoUnavailable("b"), attempts=2),
        ],
        elapsed=1.5,
    )
    data = report.to_dict()
    assert data["results"][0]["ok"] and data["results"][0]["from_cache"]
    assert data["results"][1]["error_type"] == "VideoUnavailable"
    assert "(1 from cache)" in report.summary()
    path = write_report_csv(report, tmp_path / "r" / "_report.csv")
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("video_id,ok,")
    assert "VideoUnavailable" in text and "\n\n" not in text


def test_afetch_many_runs_in_executor(sleeps):
    t = make_transcript(SAMPLE)
    forge = FakeForge({"a": [t]})
    report = asyncio.run(batch_module.afetch_many(forge, ["a"], ["en"]))
    assert report.results[0].ok


# ------------------------------------------------------------------- sources
PLAYLIST_HTML = (
    '<script>var ytInitialData = {"x":{"playlistVideoRenderer":{"videoId":"AAAAAAAAAAA","a":1}},'
    '"y":{"playlistVideoRenderer":{"videoId":"BBBBBBBBBBB"}},'
    '"z":{"playlistVideoRenderer":{"videoId":"AAAAAAAAAAA"}},"rec":{"videoId":"RRRRRRRRRRR"}}</script>'
)


def test_expand_source_single_videos_do_not_touch_network():
    assert expand_source("https://youtu.be/GJLlxj_dtq8") == ["GJLlxj_dtq8"]
    assert expand_source("GJLlxj_dtq8") == ["GJLlxj_dtq8"]
    assert expand_source("not-an-id") == ["not-an-id"]


@responses.activate
def test_expand_playlist_dedupes_and_ignores_recommendations():
    responses.get("https://www.youtube.com/playlist", body=PLAYLIST_HTML)
    ids = expand_source("https://www.youtube.com/playlist?list=PL123")
    assert ids == ["AAAAAAAAAAA", "BBBBBBBBBBB"]
    assert responses.calls[0].request.url.endswith("list=PL123")
    responses.get("https://www.youtube.com/playlist", body=PLAYLIST_HTML)
    assert expand_source("https://www.youtube.com/playlist?list=PL123", limit=1) == [
        "AAAAAAAAAAA"
    ]


@responses.activate
def test_expand_channel_appends_videos_and_falls_back_to_any_video_id():
    responses.get(
        "https://www.youtube.com/@somechannel/videos", body='{"videoId":"CCCCCCCCCCC"}'
    )
    assert expand_source("https://www.youtube.com/@somechannel") == ["CCCCCCCCCCC"]


@responses.activate
def test_expand_source_errors():
    responses.get("https://www.youtube.com/playlist", status=500)
    with pytest.raises(SourceError):
        expand_source("https://www.youtube.com/playlist?list=PL1")
    responses.replace(
        responses.GET, "https://www.youtube.com/playlist", body="<html></html>"
    )
    with pytest.raises(SourceError):
        expand_source("https://www.youtube.com/playlist?list=PL1")


# ----------------------------------------------------------------------- zip
def test_make_zip_for_directory_and_file(tmp_path):
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "a.txt").write_text("x", encoding="utf-8")
    archive = make_zip(folder)
    assert archive == tmp_path / "out.zip"
    with zipfile.ZipFile(archive) as z:
        assert z.namelist() == ["out/a.txt"]
    single = make_zip(folder / "a.txt", tmp_path / "single.zip")
    with zipfile.ZipFile(single) as z:
        assert z.namelist() == ["a.txt"]
    assert make_zip(folder / "a.txt").name == "a.zip"
