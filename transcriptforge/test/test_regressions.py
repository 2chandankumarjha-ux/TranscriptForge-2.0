"""Regression tests for bugs found in the bug hunt (see BUG_REPORT.md)."""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from transcriptforge import (
    TranscriptCache,
    _cli,
    chunk_by_chars,
    extract_keywords,
    search_transcript,
)
from transcriptforge._cli import TranscriptForgeCli
from transcriptforge._errors import NoTranscriptFound, TranscriptsDisabled
from transcriptforge._selection import select_transcript
from transcriptforge._text import tokenize
from transcriptforge._transcripts import _TranscriptParser
from transcriptforge.batch import BatchReport, BatchResult, fetch_many
from transcriptforge.cleaning import clean_text
from transcriptforge.export import make_zip, save_many
from transcriptforge.formatters import SRTFormatter, WebVTTFormatter
from transcriptforge.sources import _listing_page_url, expand_source
from transcriptforge.utils import is_video_id

from .helpers import make_transcript

VID = "abcdefghijk"


class TestVideoIdValidation(TestCase):
    def test_trailing_newline_is_not_a_video_id(self):
        # `$` used to match before a trailing "\n"
        self.assertTrue(is_video_id("dQw4w9WgXcQ"))
        self.assertFalse(is_video_id("dQw4w9WgXcQ\n"))


class TestSubtitleTimestamps(TestCase):
    def test_milliseconds_never_reach_1000(self):
        # used to give "00:00:01,1000"
        self.assertEqual(
            SRTFormatter()._seconds_to_timestamp(1.9999999), "00:00:02,000"
        )
        self.assertEqual(
            WebVTTFormatter()._seconds_to_timestamp(59.9996), "00:01:00.000"
        )
        self.assertEqual(
            WebVTTFormatter()._seconds_to_timestamp(3599.9999), "01:00:00.000"
        )

    def test_regular_values_unchanged(self):
        self.assertEqual(SRTFormatter()._seconds_to_timestamp(6.93), "00:00:06,930")
        self.assertEqual(SRTFormatter()._seconds_to_timestamp(0), "00:00:00,000")
        self.assertEqual(SRTFormatter()._seconds_to_timestamp(-1), "00:00:00,000")
        self.assertEqual(SRTFormatter()._seconds_to_timestamp(3725.5), "01:02:05,500")


class TestChannelSubPages(TestCase):
    def test_tabs_are_replaced_by_videos(self):
        base = "https://www.youtube.com"
        for url, expected in [
            ("/@name", "/@name/videos"),
            ("/@name/featured", "/@name/videos"),
            ("/@name/playlists", "/@name/videos"),
            ("/@name/videos", "/@name/videos"),
            ("/@name/streams", "/@name/streams"),
            ("/@name/shorts/", "/@name/shorts"),
            ("/channel/UCabc/about", "/channel/UCabc/videos"),
            ("/c/Name", "/c/Name/videos"),
            ("/user/Name/featured", "/user/Name/videos"),
        ]:
            self.assertEqual(_listing_page_url(base + url), base + expected, url)

    def test_playlist_url_keeps_query(self):
        self.assertEqual(
            _listing_page_url("https://www.youtube.com/playlist?list=PLx"),
            "https://www.youtube.com/playlist?list=PLx",
        )
        self.assertEqual(
            _listing_page_url("https://www.youtube.com/playlist"),
            "https://www.youtube.com/playlist",
        )

    def test_negative_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            expand_source("https://www.youtube.com/playlist?list=PLx", limit=-1)


class TestCacheCorruption(TestCase):
    def test_valid_json_that_is_not_an_object_is_a_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = TranscriptCache(directory)
            for content in ("[]", '"text"', "5", "null"):
                Path(cache._path("k")).write_text(content, encoding="utf-8")
                self.assertIsNone(cache.get("k"), content)


class TestBatchRetries(TestCase):
    def test_negative_retries_still_tries_once(self):
        calls = []

        class Forge:
            _proxy_config = None

            def _fetch_best(self, video_id, *args, **kwargs):
                calls.append(video_id)
                return make_transcript([("hi", 0, 1)]), False

        report = fetch_many(Forge(), [VID], retries=-3)
        self.assertEqual(calls, [VID])
        self.assertTrue(report.results[0].ok)


class TestConflictingFlags(TestCase):
    def test_select_transcript_rejects_both_exclusions(self):
        with self.assertRaises(ValueError):
            select_transcript(
                None, ["en"], exclude_generated=True, exclude_manually_created=True
            )
        self.assertTrue(issubclass(NoTranscriptFound, Exception))


class TestSaveManyCollisions(TestCase):
    def test_formats_sharing_an_extension_do_not_overwrite_each_other(self):
        transcript = make_transcript([("hello world. second sentence here", 0, 2)])
        with tempfile.TemporaryDirectory() as directory:
            paths = save_many(
                [transcript], directory, ["text", "timestamped", "srt", "text"]
            )
            self.assertEqual(len(paths), 3)  # duplicate "text" request is ignored
            self.assertEqual(len(set(paths)), 3)
            names = sorted(os.listdir(directory))
            self.assertEqual(
                names,
                [
                    "GJLlxj_dtq8.en.srt",
                    "GJLlxj_dtq8.en.text.txt",
                    "GJLlxj_dtq8.en.timestamped.txt",
                ],
            )
            self.assertIn(
                "[00:00]",
                (Path(directory) / "GJLlxj_dtq8.en.timestamped.txt").read_text(),
            )

    def test_single_format_keeps_the_plain_name(self):
        transcript = make_transcript([("hello", 0, 1)])
        with tempfile.TemporaryDirectory() as directory:
            save_many([transcript], directory, ["text", "json"])
            self.assertEqual(
                sorted(os.listdir(directory)),
                ["GJLlxj_dtq8.en.json", "GJLlxj_dtq8.en.txt"],
            )


class TestMakeZip(TestCase):
    def test_current_directory_gets_a_real_name(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "out"
            folder.mkdir()
            (folder / "a.txt").write_text("x")
            previous = os.getcwd()
            os.chdir(folder)
            try:
                archive = make_zip(".")
            finally:
                os.chdir(previous)
            self.assertEqual(archive.name, "out.zip")
            self.assertTrue(archive.exists())
            self.assertFalse((folder / "..zip").exists())


class TestUnicodeWordHandling(TestCase):
    def test_zwj_and_zwnj_keep_conjuncts_together(self):
        self.assertEqual(tokenize("क्\u200dष"), ["क्\u200dष"])
        self.assertEqual(tokenize("क्\u200cष"), ["क्\u200cष"])

    def test_other_indic_scripts_are_not_split(self):
        for word in ["কৃষ্ণ", "தமிழ்", "తెలుగు", "ಕನ್ನಡ", "മലയാളം", "ગુજરાતી", "ਪੰਜਾਬੀ"]:
            self.assertEqual(tokenize(word), [word], word)

    def test_curly_apostrophe_matches_stopwords(self):
        self.assertEqual(tokenize("don\u2019t"), ["don't"])
        self.assertEqual(
            extract_keywords("don\u2019t it\u2019s python python", 5), [("python", 2)]
        )

    def test_whole_word_search_in_another_script(self):
        transcript = make_transcript([("কৃষ্ণ এবং রাম", 0, 2), ("রামায়ণ", 2, 2)])
        hits = search_transcript(transcript, "রাম", whole_word=True)
        self.assertEqual([h.snippet_index for h in hits], [0])


class TestCleaningFalsePositives(TestCase):
    def test_brackets_attached_to_a_word_are_kept(self):
        self.assertEqual(clean_text("the arr[i] element"), "the arr[i] element")
        self.assertEqual(clean_text("see note[1] below"), "see note[1] below")

    def test_real_sound_tags_still_removed(self):
        self.assertEqual(clean_text("[Music] hello [संगीत] world"), "hello world")
        self.assertEqual(clean_text("hello[Music]"), "hello[Music]")

    def test_comparison_operators_are_not_tags(self):
        self.assertEqual(clean_text("if x < 5 and y > 3"), "if x < 5 and y > 3")
        self.assertEqual(clean_text("<i>bold</i> text"), "bold text")


class TestParserKeepsComparisons(TestCase):
    XML = '<transcript><text start="0" dur="2">if x &lt; 5 and y &gt; 3 then &lt;i&gt;go&lt;/i&gt;</text></transcript>'

    def test_text_between_angle_brackets_survives(self):
        # used to become "if x  3 then go"
        self.assertEqual(
            _TranscriptParser().parse(self.XML)[0].text, "if x < 5 and y > 3 then go"
        )

    def test_preserve_formatting_keeps_comparisons_and_formatting_tags(self):
        self.assertEqual(
            _TranscriptParser(preserve_formatting=True).parse(self.XML)[0].text,
            "if x < 5 and y > 3 then <i>go</i>",
        )


class _FakeForge:
    """Stands in for TranscriptForge.fetch_many so that no network is needed."""

    def __init__(self, results):
        self.results = results

    def __call__(self, *args, **kwargs):
        return BatchReport(self.results)


def _ok(video_id=VID):
    return BatchResult(video_id, make_transcript([("hallo welt", 0, 2)], video_id))


def _failed(video_id=VID):
    return BatchResult(video_id, None, TranscriptsDisabled(video_id))


class TestCliExitCodeAndValidation(TestCase):
    def _run(self, results, *args):
        cli = TranscriptForgeCli([VID, *args])
        with patch.object(_cli.TranscriptForge, "fetch_many", _FakeForge(results)):
            return cli, cli.run()

    def test_exit_code_is_zero_on_success(self):
        cli, output = self._run([_ok()], "--format", "text")
        self.assertEqual(cli.exit_code, 0)
        self.assertIn("hallo welt", output)

    def test_exit_code_is_one_when_a_video_failed(self):
        cli, output = self._run([_failed()])
        self.assertEqual(cli.exit_code, 1)
        self.assertIn("Subtitles are disabled", output)

    def test_exit_code_is_one_on_partial_failure(self):
        cli, _ = self._run([_ok(), _failed("bbbbbbbbbbb")])
        self.assertEqual(cli.exit_code, 1)

    def test_exit_code_for_list_transcripts_errors(self):
        cli = TranscriptForgeCli(["--list-transcripts", VID])
        with patch.object(
            _cli.TranscriptForge, "list", side_effect=TranscriptsDisabled(VID)
        ):
            cli.run()
        self.assertEqual(cli.exit_code, 1)

    def test_invalid_numbers_are_usage_errors_not_tracebacks(self):
        for args in [
            ["--chunks", "100", "--chunk-overlap", "200"],
            ["--chunks", "-5"],
            ["--summary", "-1"],
            ["--context", "-1"],
            ["--retries", "-1"],
            ["--limit", "-1"],
            ["--workers", "0"],
            ["--delay", "-1"],
        ]:
            with self.assertRaises(SystemExit) as raised:
                TranscriptForgeCli([VID, *args])._parse_args()
            self.assertEqual(raised.exception.code, 2, args)

    def test_valid_chunk_settings_are_accepted(self):
        parsed = TranscriptForgeCli(
            [VID, "--chunks", "200", "--chunk-overlap", "50"]
        )._parse_args()
        self.assertEqual((parsed.chunks, parsed.chunk_overlap), (200, 50))

    def test_missing_proxy_file_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as raised:
            TranscriptForgeCli(
                [VID, "--proxy-file", "/does/not/exist.txt"]
            )._parse_args()
        self.assertEqual(raised.exception.code, 2)

    def test_webshare_needs_both_credentials(self):
        for args in (
            ["--webshare-proxy-username", "u"],
            ["--webshare-proxy-password", "p"],
        ):
            with self.assertRaises(SystemExit):
                TranscriptForgeCli([VID, *args])._parse_args()
        parsed = TranscriptForgeCli(
            [VID, "--webshare-proxy-username", "u", "--webshare-proxy-password", "p"]
        )._parse_args()
        self.assertEqual(parsed.webshare_proxy_username, "u")

    def test_playlist_flag_with_watch_url_expands_the_list(self):
        cli = TranscriptForgeCli(
            ["--playlist", "https://www.youtube.com/watch?v=%s&list=PLabc123" % VID]
        )
        seen = []

        def fake_expand(url, limit=None):
            seen.append(url)
            return ["aaaaaaaaaaa", "bbbbbbbbbbb"]

        with patch.object(_cli, "expand_source", fake_expand):
            ids = cli._collect_video_ids(cli._parse_args(), [])
        self.assertEqual(seen, ["https://www.youtube.com/playlist?list=PLabc123"])
        self.assertEqual(ids, ["aaaaaaaaaaa", "bbbbbbbbbbb"])

    def test_playlist_flag_with_plain_video_id_is_unchanged(self):
        cli = TranscriptForgeCli(["--playlist", VID])
        self.assertEqual(cli._collect_video_ids(cli._parse_args(), []), [VID])


class TestChunkingStillValidates(TestCase):
    def test_library_api_still_raises(self):
        transcript = make_transcript([("a b c", 0, 1)])
        with self.assertRaises(ValueError):
            chunk_by_chars(transcript, 100, 200)
        self.assertEqual(
            json.loads(json.dumps(len(chunk_by_chars(transcript, 100)))), 1
        )
