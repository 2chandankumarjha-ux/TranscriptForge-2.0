import asyncio
from unittest import TestCase

import responses

from transcriptforge import (
    NoTranscriptFound,
    TranscriptCache,
    TranscriptForge,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
    TranscriptForgeError,
)
from transcriptforge._selection import select_transcript
from transcriptforge._transcripts import TranscriptList

from .test_api import load_asset

VID = "GJLlxj_dtq8"


class TestAdvancedApi(TestCase):
    def setUp(self):
        responses.start()
        self.addCleanup(responses.stop)
        self.addCleanup(responses.reset)
        responses.post(
            "https://www.youtube.com/youtubei/v1/player",
            body=load_asset("youtube.innertube.json.static"),
            content_type="application/json",
        )
        responses.get(
            "https://www.youtube.com/watch", body=load_asset("youtube.html.static")
        )
        responses.get(
            "https://www.youtube.com/api/timedtext",
            body=load_asset("transcript.xml.static"),
        )

    def test_backwards_compatible_aliases(self):
        self.assertIs(YouTubeTranscriptApi, TranscriptForge)
        self.assertIs(YouTubeTranscriptApiException, TranscriptForgeError)

    def test_fetch_accepts_urls(self):
        for value in (
            "https://youtu.be/" + VID,
            "https://www.youtube.com/watch?v=" + VID,
        ):
            self.assertEqual(TranscriptForge().fetch(value).video_id, VID)

    def test_fetch_best_translates_when_language_is_missing(self):
        transcript = TranscriptForge().fetch_best(VID, ["fr"])
        self.assertEqual(transcript.language_code, "fr")
        self.assertIn("tlang=fr", responses.calls[-1].request.url)

    def test_fetch_best_falls_back_to_any_transcript_preferring_manual(self):
        transcript = TranscriptForge().fetch_best(VID, ["xx"])
        self.assertFalse(transcript.is_generated)
        self.assertEqual(transcript.language_code, "zh")

    def test_fetch_best_respects_exclusions(self):
        transcript = TranscriptForge().fetch_best(
            VID, ["xx"], exclude_manually_created=True
        )
        self.assertTrue(transcript.is_generated)

    def test_fetch_best_strict_mode_raises(self):
        with self.assertRaises(NoTranscriptFound):
            TranscriptForge().fetch_best(VID, ["xx"], best_effort=False)

    def test_fetch_best_translate_to(self):
        transcript = TranscriptForge().fetch_best(VID, ["en"], translate_to="hi")
        self.assertEqual(transcript.language_code, "hi")
        same = TranscriptForge().fetch_best(
            VID, ["hi"], translate_to="hi"
        )  # no double translation
        self.assertNotIn("tlang", responses.calls[-1].request.url)
        self.assertEqual(same.language_code, "hi")

    def test_fetch_hindi_manual_transcript(self):
        self.assertEqual(TranscriptForge().fetch(VID, ["hi"]).language_code, "hi")

    def test_cache_avoids_second_download(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            forge = TranscriptForge(cache=TranscriptCache(directory))
            first = forge.fetch(VID, ["en"])
            calls_after_first = len(responses.calls)
            second = forge.fetch(VID, ["en"])
            self.assertEqual(first, second)
            self.assertEqual(len(responses.calls), calls_after_first)
            # a different request (other language) is a different cache entry
            forge.fetch(VID, ["de"])
            self.assertGreater(len(responses.calls), calls_after_first)

    def test_fetch_many_real_flow_with_worker_threads_and_cache(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            forge = TranscriptForge(cache=TranscriptCache(directory))
            ids = [VID, "https://youtu.be/" + VID]
            report = forge.fetch_many(ids, ["en"], workers=2)
            self.assertEqual(len(report.succeeded), 2)
            again = forge.fetch_many([VID], ["en"], workers=1)
            self.assertTrue(again.results[0].from_cache)

    def test_afetch_many(self):
        report = asyncio.run(TranscriptForge().afetch_many([VID], ["en"]))
        self.assertTrue(report.results[0].ok)


class TestSelectionEdgeCases(TestCase):
    def test_best_effort_with_nothing_left_raises_no_transcript_found(self):
        empty = TranscriptList("vid", {}, {}, [])
        with self.assertRaises(NoTranscriptFound):
            select_transcript(empty, ["en"], best_effort=True)
