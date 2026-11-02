import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Dict, List, Optional

from .analysis import analyze_transcript, summarize
from .cache import TranscriptCache
from .cleaning import clean_transcript
from .export import FORMAT_EXTENSIONS, make_zip, save_many, write_report_csv
from .formatters import FormatterLoader
from .proxies import GenericProxyConfig, ProxyConfig, WebshareProxyConfig
from .search import search_transcript
from .segments import chunk_by_chars
from .sources import expand_source, is_listing_url
from .utils import format_timestamp, normalize_video_id, timestamp_url, unique

from ._api import TranscriptForge, FetchedTranscript, TranscriptList


class TranscriptForgeCli:
    def __init__(self, args: List[str]):
        self._args = args

    # ------------------------------------------------------------------ run
    def run(self) -> str:
        parsed_args = self._parse_args()

        if parsed_args.exclude_manually_created and parsed_args.exclude_generated:
            return ""

        proxy_config: Optional[ProxyConfig] = None
        if parsed_args.http_proxy != "" or parsed_args.https_proxy != "":
            proxy_config = GenericProxyConfig(
                http_url=parsed_args.http_proxy,
                https_url=parsed_args.https_proxy,
            )

        if (
            parsed_args.webshare_proxy_username is not None
            or parsed_args.webshare_proxy_password is not None
        ):
            proxy_config = WebshareProxyConfig(
                proxy_username=parsed_args.webshare_proxy_username,
                proxy_password=parsed_args.webshare_proxy_password,
            )

        proxy_pool = self._load_proxy_pool(parsed_args.proxy_file)

        forge_kwargs: Dict = {"proxy_config": proxy_config}
        if parsed_args.cache_dir:
            forge_kwargs["cache"] = TranscriptCache(
                parsed_args.cache_dir,
                ttl_seconds=(
                    None
                    if parsed_args.cache_ttl_hours <= 0
                    else parsed_args.cache_ttl_hours * 3600
                ),
            )
        forge = TranscriptForge(**forge_kwargs)

        exceptions: List[BaseException] = []
        video_ids = self._collect_video_ids(parsed_args, exceptions)

        # ---- --list-transcripts: show what exists, don't fetch anything
        if parsed_args.list_transcripts:
            listings: List[TranscriptList] = []
            for video_id in video_ids:
                try:
                    listings.append(forge.list(video_id))
                except Exception as exception:
                    exceptions.append(exception)
            sections = [str(exception) for exception in exceptions]
            sections.extend(str(transcript_list) for transcript_list in listings)
            return "\n\n".join(sections)

        # ---- fetch (sequential by default, parallel with --workers N)
        report = None
        transcripts: List[FetchedTranscript] = []
        if video_ids:
            report = forge.fetch_many(
                video_ids,
                parsed_args.languages,
                preserve_formatting=parsed_args.preserve_formatting,
                exclude_generated=parsed_args.exclude_generated,
                exclude_manually_created=parsed_args.exclude_manually_created,
                translate_to=parsed_args.translate or None,
                best_effort=parsed_args.best_effort,
                workers=parsed_args.workers,
                retries=parsed_args.retries,
                min_delay=parsed_args.delay,
                proxy_pool=proxy_pool or None,
                on_progress=self._progress if parsed_args.progress else None,
            )
            exceptions.extend(result.error for result in report.failed)
            transcripts = report.transcripts

        if parsed_args.clean:
            transcripts = [clean_transcript(t) for t in transcripts]

        print_sections = [str(exception) for exception in exceptions]
        wants_json = parsed_args.format == "json"

        if transcripts and parsed_args.output_dir:
            print_sections.append(
                self._export(
                    parsed_args,
                    transcripts,
                    report,
                    wants_explicit_format=self._has_flag("--format"),
                )
            )
        if transcripts and parsed_args.search:
            print_sections.append(
                self._search_section(parsed_args, transcripts, wants_json)
            )
        if transcripts and parsed_args.stats:
            print_sections.append(self._stats_section(transcripts, wants_json))
        if transcripts and parsed_args.summary:
            print_sections.append(self._summary_section(parsed_args, transcripts))
        if transcripts and parsed_args.chunks:
            print_sections.append(self._chunks_section(parsed_args, transcripts))

        analysis_requested = bool(
            parsed_args.search
            or parsed_args.stats
            or parsed_args.summary
            or parsed_args.chunks
        )
        if transcripts and not analysis_requested and not parsed_args.output_dir:
            kwargs = {"ensure_ascii": False} if wants_json else {}
            print_sections.append(
                FormatterLoader()
                .load(parsed_args.format)
                .format_transcripts(transcripts, **kwargs)
            )
        if report is not None and len(report.results) > 1 and parsed_args.progress:
            print_sections.append(report.summary())

        return "\n\n".join(section for section in print_sections if section != "")

    # -------------------------------------------------------------- helpers
    def _has_flag(self, flag: str) -> bool:
        return any(a == flag or a.startswith(flag + "=") for a in self._args)

    @staticmethod
    def _progress(done: int, total: int, result) -> None:
        mark = "ok " if result.ok else "ERR"
        extra = " (cache)" if result.from_cache else ""
        if not result.ok:
            extra = " - " + result.error_type
        print(
            "[{}/{}] {} {}{}".format(done, total, mark, result.video_id, extra),
            file=sys.stderr,
        )

    @staticmethod
    def _load_proxy_pool(path: Optional[str]) -> List[ProxyConfig]:
        if not path:
            return []
        pool: List[ProxyConfig] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pool.append(GenericProxyConfig(http_url=line, https_url=line))
        return pool

    def _collect_video_ids(
        self, parsed_args, exceptions: List[BaseException]
    ) -> List[str]:
        raw_items: List[str] = list(parsed_args.video_ids)
        if parsed_args.file:
            try:
                for line in (
                    Path(parsed_args.file).read_text(encoding="utf-8").splitlines()
                ):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        raw_items.append(line)
            except OSError as exception:
                exceptions.append(exception)
        raw_items.extend(parsed_args.playlist or [])

        video_ids: List[str] = []
        for item in raw_items:
            if is_listing_url(item):
                try:
                    video_ids.extend(expand_source(item, limit=parsed_args.limit))
                except Exception as exception:
                    exceptions.append(exception)
            else:
                video_ids.append(normalize_video_id(item))
        return unique(video_ids)

    def _export(
        self, parsed_args, transcripts, report, wants_explicit_format: bool
    ) -> str:
        if parsed_args.formats:
            formats = parsed_args.formats
        elif wants_explicit_format:
            formats = [parsed_args.format]
        else:
            formats = ["text"]
        directory = Path(parsed_args.output_dir)
        saved = save_many(transcripts, directory, formats)
        lines = ["Saved {} file(s) to {}".format(len(saved), directory)]
        if report is not None and len(report.results) > 1:
            lines.append(
                "Status table: {}".format(
                    write_report_csv(report, directory / "_report.csv")
                )
            )
        if parsed_args.zip:
            lines.append("ZIP archive: {}".format(make_zip(directory)))
        return "\n".join(lines)

    def _search_section(self, parsed_args, transcripts, as_json: bool) -> str:
        try:
            per_video = [
                (
                    t,
                    search_transcript(
                        t,
                        parsed_args.search,
                        regex=parsed_args.regex,
                        case_sensitive=parsed_args.case_sensitive,
                        whole_word=parsed_args.whole_word,
                        context=parsed_args.context,
                    ),
                )
                for t in transcripts
            ]
        except Exception as exception:  # e.g. invalid regular expression
            return "Search failed: {}".format(exception)

        if as_json:
            return json.dumps(
                [hit.to_dict() for _, hits in per_video for hit in hits],
                ensure_ascii=False,
                indent=2,
            )
        lines: List[str] = []
        for transcript, hits in per_video:
            lines.append(
                "== {} ({}): {} hit(s)".format(
                    transcript.video_id, transcript.language_code, len(hits)
                )
            )
            for hit in hits:
                lines.extend("    " + text for text in hit.before)
                lines.append("[{}] {}  ->  {}".format(hit.timestamp, hit.text, hit.url))
                lines.extend("    " + text for text in hit.after)
        return "\n".join(lines)

    @staticmethod
    def _stats_section(transcripts, as_json: bool) -> str:
        stats = [analyze_transcript(t) for t in transcripts]
        if as_json:
            return json.dumps(
                [s.to_dict() for s in stats], ensure_ascii=False, indent=2
            )
        blocks = []
        for s in stats:
            blocks.append(
                "\n".join(
                    [
                        "== {} ({}{})".format(
                            s.video_id,
                            s.language_code,
                            ", auto" if s.is_generated else "",
                        ),
                        "words: {}  unique: {}  diversity: {}".format(
                            s.word_count, s.unique_word_count, s.lexical_diversity
                        ),
                        "duration: {}  pace: {} words/min  longest pause: {}s".format(
                            format_timestamp(s.duration_seconds),
                            s.words_per_minute,
                            s.longest_pause_seconds,
                        ),
                        "keywords: "
                        + ", ".join("{} ({})".format(w, c) for w, c in s.top_keywords),
                        "phrases: "
                        + ", ".join("{} ({})".format(w, c) for w, c in s.top_phrases),
                    ]
                )
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _summary_section(parsed_args, transcripts) -> str:
        blocks = []
        for t in transcripts:
            lines = ["== {} ({}) key passages".format(t.video_id, t.language_code)]
            for seg in summarize(t, passages=parsed_args.summary):
                lines.append(
                    "[{}] {}  ->  {}".format(
                        seg.timestamp, seg.text, timestamp_url(t.video_id, seg.start)
                    )
                )
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    @staticmethod
    def _chunks_section(parsed_args, transcripts) -> str:
        rows = []
        for t in transcripts:
            for chunk in chunk_by_chars(
                t, parsed_args.chunks, parsed_args.chunk_overlap
            ):
                row = chunk.to_dict()
                row.update(
                    {
                        "video_id": t.video_id,
                        "language_code": t.language_code,
                        "url": chunk.link(t.video_id),
                    }
                )
                rows.append(row)
        return json.dumps(rows, ensure_ascii=False, indent=2)

    def _get_version(self):
        try:
            return version("transcriptforge")
        except PackageNotFoundError:
            return "unknown"

    # ------------------------------------------------------------- argparse
    def _parse_args(self):
        parser = argparse.ArgumentParser(
            prog="transcriptforge",
            description=(
                "TranscriptForge: get YouTube transcripts/subtitles (also auto-generated and "
                "translated ones) without a headless browser. Handles URLs, playlists, batches, "
                "caching, search, analytics and many export formats."
            ),
        )
        parser.add_argument(
            "--version",
            action="version",
            version=f"%(prog)s, version {self._get_version()}",
        )
        parser.add_argument(
            "--list-transcripts",
            action="store_const",
            const=True,
            default=False,
            help="This will list the languages in which the given videos are available in.",
        )
        parser.add_argument(
            "video_ids",
            nargs="*",
            type=str,
            help="Video ids or YouTube URLs (watch, youtu.be, shorts, embed, live). "
            "Playlist and channel URLs are expanded automatically.",
        )
        parser.add_argument(
            "--languages",
            nargs="*",
            default=[
                "en",
            ],
            type=str,
            help=(
                'A list of language codes in a descending priority. For example, if this is set to "de en" it will '
                "first try to fetch the german transcript (de) and then fetch the english transcript (en) if it fails "
                "to do so. Use --list-transcripts to see which codes a video offers."
            ),
        )
        parser.add_argument(
            "--exclude-generated",
            action="store_const",
            const=True,
            default=False,
            help="If this flag is set transcripts which have been generated by YouTube will not be retrieved.",
        )
        parser.add_argument(
            "--exclude-manually-created",
            action="store_const",
            const=True,
            default=False,
            help="If this flag is set transcripts which have been manually created will not be retrieved.",
        )
        parser.add_argument(
            "--format",
            type=str,
            default="pretty",
            choices=tuple(FormatterLoader.TYPES.keys()),
            help="Output format printed to the terminal (and used for --output-dir if --formats is not given).",
        )
        parser.add_argument(
            "--translate",
            default="",
            help=(
                "The language code for the language you want this transcript to be translated to. Use the "
                "--list-transcripts feature to find out which languages are translatable and which translation "
                "languages are available."
            ),
        )
        parser.add_argument(
            "--best-effort",
            action="store_true",
            help="If none of --languages exists, translate an available transcript into the first "
            "language (if YouTube allows it) or fall back to any available transcript.",
        )
        parser.add_argument(
            "--preserve-formatting",
            action="store_true",
            help="Keep basic HTML formatting tags (<i>, <b>) in the text.",
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Remove [Music]-style tags, >> markers, duplicates, normalise whitespace/Unicode.",
        )

        sources = parser.add_argument_group("input sources")
        sources.add_argument(
            "--file",
            metavar="PATH",
            help="Text file with one video id/URL per line (# for comments).",
        )
        sources.add_argument(
            "--playlist",
            nargs="+",
            metavar="URL",
            help="Playlist or channel URL(s) to expand into videos.",
        )
        sources.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of videos taken from each playlist/channel.",
        )

        batch = parser.add_argument_group("speed and reliability")
        batch.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Parallel downloads (default 1). 2-5 is sensible without rotating proxies.",
        )
        batch.add_argument(
            "--retries",
            type=int,
            default=2,
            help="Extra attempts for temporarily blocked requests (default 2).",
        )
        batch.add_argument(
            "--delay",
            type=float,
            default=0.0,
            help="Minimum seconds between requests of one worker.",
        )
        batch.add_argument(
            "--cache-dir",
            metavar="DIR",
            help="Cache transcripts on disk, so repeated runs are instant.",
        )
        batch.add_argument(
            "--cache-ttl-hours",
            type=float,
            default=168.0,
            help="Cache lifetime in hours (default 168 = 7 days, 0 = forever).",
        )
        batch.add_argument(
            "--progress",
            action="store_true",
            help="Show progress on stderr and a summary at the end.",
        )

        output = parser.add_argument_group("saving")
        output.add_argument(
            "--output-dir",
            metavar="DIR",
            help="Save one file per video (and format) here instead of printing.",
        )
        output.add_argument(
            "--formats",
            nargs="+",
            choices=tuple(FORMAT_EXTENSIONS),
            help="Formats to save with --output-dir, e.g. text srt json.",
        )
        output.add_argument(
            "--zip",
            action="store_true",
            help="Also pack the --output-dir into a .zip archive.",
        )

        analysis = parser.add_argument_group("analysis")
        analysis.add_argument(
            "--search",
            metavar="TEXT",
            help="Find TEXT in the transcripts; prints timestamps and deep links.",
        )
        analysis.add_argument(
            "--regex",
            action="store_true",
            help="Treat --search as a regular expression.",
        )
        analysis.add_argument(
            "--case-sensitive", action="store_true", help="Case sensitive --search."
        )
        analysis.add_argument(
            "--whole-word",
            action="store_true",
            help="Only match whole words in --search (Devanagari aware).",
        )
        analysis.add_argument(
            "--context",
            type=int,
            default=0,
            help="Snippets of context around each search hit.",
        )
        analysis.add_argument(
            "--stats",
            action="store_true",
            help="Word count, speaking pace, keywords and phrases.",
        )
        analysis.add_argument(
            "--summary",
            type=int,
            metavar="N",
            default=0,
            help="Print the N most important passages (extractive, offline).",
        )
        analysis.add_argument(
            "--chunks",
            type=int,
            metavar="CHARS",
            default=0,
            help="Print JSON chunks of about CHARS characters with timestamps (for LLM/RAG use).",
        )
        analysis.add_argument(
            "--chunk-overlap",
            type=int,
            default=0,
            help="Overlap in characters between chunks.",
        )

        proxies = parser.add_argument_group("proxies")
        proxies.add_argument(
            "--webshare-proxy-username",
            default=None,
            type=str,
            help='Specify your Webshare "Proxy Username" found at https://dashboard.webshare.io/proxy/settings',
        )
        proxies.add_argument(
            "--webshare-proxy-password",
            default=None,
            type=str,
            help='Specify your Webshare "Proxy Password" found at https://dashboard.webshare.io/proxy/settings',
        )
        proxies.add_argument(
            "--http-proxy",
            default="",
            metavar="URL",
            help="Use the specified HTTP proxy.",
        )
        proxies.add_argument(
            "--https-proxy",
            default="",
            metavar="URL",
            help="Use the specified HTTPS proxy.",
        )
        proxies.add_argument(
            "--proxy-file",
            metavar="PATH",
            help="Text file with one proxy URL per line; blocked requests rotate to the next proxy.",
        )
        # Cookie auth has been temporarily disabled, as it is not working properly with
        # YouTube's most recent changes.

        args = parser.parse_args(self._args)
        if not args.video_ids and not args.file and not args.playlist:
            parser.error("give at least one video id/URL, or use --file / --playlist")
        return self._sanitize_video_ids(args)

    def _sanitize_video_ids(self, args):
        args.video_ids = [video_id.replace("\\", "") for video_id in args.video_ids]
        return args
