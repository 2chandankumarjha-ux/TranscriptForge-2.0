import json
import zipfile
from unittest import TestCase

import responses

from transcriptforge._cli import TranscriptForgeCli

from .test_api import load_asset

VID = "GJLlxj_dtq8"
OTHER = "abcdefghijk"


def run(*args):
    return TranscriptForgeCli(list(args)).run()


class TestAdvancedCli(TestCase):
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

    def tmp(self):
        import tempfile
        from pathlib import Path

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def test_url_input_and_text_format(self):
        out = run("https://youtu.be/%s?t=5" % VID, "--format", "text")
        self.assertEqual(out.splitlines()[0], "Hey, this is just a test")

    def test_requires_some_input(self):
        with self.assertRaises(SystemExit):
            run("--format", "text")

    def test_file_input_skips_comments_and_duplicates(self):
        listing = self.tmp() / "ids.txt"
        listing.write_text(
            "# my list\n\nhttps://youtu.be/%s\n%s\n" % (VID, VID), encoding="utf-8"
        )
        out = run("--file", str(listing), "--format", "json")
        self.assertEqual(len(json.loads(out)), 1)

    def test_missing_file_is_reported_not_raised(self):
        self.assertIn("No such file", run("--file", str(self.tmp() / "nope.txt")))

    def test_output_dir_formats_zip_and_report(self):
        out_dir = self.tmp() / "out"
        out = run(
            VID,
            OTHER,
            "--output-dir",
            str(out_dir),
            "--formats",
            "srt",
            "json",
            "--zip",
        )
        self.assertIn("Saved 4 file(s)", out)
        self.assertTrue((out_dir / ("%s.en.srt" % VID)).exists())
        self.assertIn(
            "Hey", (out_dir / ("%s.en.json" % VID)).read_text(encoding="utf-8")
        )
        self.assertTrue((out_dir / "_report.csv").exists())
        with zipfile.ZipFile(str(out_dir) + ".zip") as archive:
            self.assertTrue(any(name.endswith(".srt") for name in archive.namelist()))

    def test_output_dir_defaults_to_text_or_explicit_format(self):
        a = self.tmp() / "a"
        run(VID, "--output-dir", str(a))
        self.assertTrue((a / ("%s.en.txt" % VID)).exists())
        b = self.tmp() / "b"
        run(VID, "--output-dir", str(b), "--format", "json")
        self.assertTrue((b / ("%s.en.json" % VID)).exists())

    def test_search_text_and_context(self):
        out = run(VID, "--search", "TEST", "--context", "1")
        self.assertIn("== %s (en): 2 hit(s)" % VID, out)
        self.assertIn("https://youtu.be/%s?t=0" % VID, out)
        self.assertIn("    this is not the original transcript", out)

    def test_search_json_and_errors(self):
        hits = json.loads(run(VID, "--search", "shorter", "--format", "json"))
        self.assertEqual(hits[0]["url"], "https://youtu.be/%s?t=5" % VID)
        self.assertIn("Search failed", run(VID, "--search", "(", "--regex"))
        self.assertEqual(
            len(
                json.loads(
                    run(
                        VID,
                        "--search",
                        r"t\w+t",
                        "--regex",
                        "--case-sensitive",
                        "--format",
                        "json",
                    )
                )
            ),
            3,
        )
        # whole word: "test" matches, but not the "test" inside "testing"
        self.assertIn(
            "1 hit(s)", run(VID, "--search", "test", "--whole-word", "--case-sensitive")
        )

    def test_stats_summary_and_chunks(self):
        stats = run(VID, "--stats")
        self.assertIn("words:", stats)
        self.assertIn("keywords:", stats)
        as_json = json.loads(run(VID, "--stats", "--format", "json"))
        self.assertEqual(as_json[0]["video_id"], VID)
        self.assertIn("key passages", run(VID, "--summary", "1"))
        chunks = json.loads(run(VID, "--chunks", "40", "--chunk-overlap", "10"))
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["video_id"], VID)
        self.assertIn("url", chunks[0])

    def test_clean_flag(self):
        out = run(VID, "--clean", "--format", "text")
        self.assertNotIn("<", out)

    def test_cache_makes_second_run_offline(self):
        cache_dir = self.tmp() / "cache"
        run(VID, "--cache-dir", str(cache_dir), "--format", "text")
        calls = len(responses.calls)
        out = run(
            VID,
            "--cache-dir",
            str(cache_dir),
            "--cache-ttl-hours",
            "0",
            "--format",
            "text",
        )
        self.assertEqual(len(responses.calls), calls)
        self.assertIn("Hey, this is just a test", out)

    def test_best_effort_translates(self):
        strict = run(VID, "--languages", "fr")
        self.assertIn("No transcripts were found", strict)
        self.assertIn(
            "tlang=fr",
            (
                run(VID, "--languages", "fr", "--best-effort", "--format", "json"),
                responses.calls[-1].request.url,
            )[1],
        )

    def test_workers_and_progress_summary(self):
        import io
        from contextlib import redirect_stderr

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            out = run(VID, OTHER, "--workers", "2", "--progress", "--format", "text")
        self.assertIn("[2/2] ok", buffer.getvalue())
        self.assertIn("2/2 transcripts fetched", out)

    def test_progress_marks_failures_and_cache(self):
        import io
        from contextlib import redirect_stderr

        responses.replace(
            responses.POST,
            "https://www.youtube.com/youtubei/v1/player",
            body=load_asset("youtube_video_unavailable.innertube.json.static"),
        )
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            out = run(VID, "--progress")
        self.assertIn("ERR", buffer.getvalue())
        self.assertIn("no longer available", out)

    def test_playlist_expansion(self):
        responses.get(
            "https://www.youtube.com/playlist",
            body='{"playlistVideoRenderer":{"videoId":"%s"}}' % VID,
        )
        out = run(
            "--playlist",
            "https://www.youtube.com/playlist?list=PL1",
            "--format",
            "json",
            "--limit",
            "5",
        )
        self.assertEqual(len(json.loads(out)), 1)

    def test_playlist_failure_is_reported(self):
        responses.get("https://www.youtube.com/playlist", status=404)
        self.assertIn(
            "Could not load", run("https://www.youtube.com/playlist?list=PL1")
        )

    def test_proxy_file_is_used(self):
        proxies = self.tmp() / "proxies.txt"
        proxies.write_text("# pool\nhttp://user:pw@10.0.0.1:8080\n", encoding="utf-8")
        out = run(VID, "--proxy-file", str(proxies), "--format", "text")
        self.assertIn("Hey, this is just a test", out)

    def test_list_transcripts_with_urls_and_errors(self):
        out = run("https://youtu.be/%s" % VID, "--list-transcripts")
        self.assertIn("transcripts are available", out)

    def test_exclude_both_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as raised:
            run(VID, "--exclude-generated", "--exclude-manually-created")
        self.assertEqual(raised.exception.code, 2)

    def test_preserve_formatting_flag(self):
        out = run(VID, "--preserve-formatting", "--format", "text")
        self.assertIn("<i>not</i>", out)


class TestListTranscriptsErrors(TestCase):
    @responses.activate
    def test_list_transcripts_reports_failing_videos(self):
        responses.post(
            "https://www.youtube.com/youtubei/v1/player",
            body=load_asset("youtube_video_unavailable.innertube.json.static"),
            content_type="application/json",
        )
        responses.get(
            "https://www.youtube.com/watch", body=load_asset("youtube.html.static")
        )
        self.assertIn("no longer available", run(VID, "--list-transcripts"))
