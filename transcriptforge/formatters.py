import csv
import html
import io
import json

import pprint
from typing import List, Iterable

from ._transcripts import FetchedTranscript, FetchedTranscriptSnippet
from .segments import to_paragraphs
from .utils import format_timestamp


class Formatter:
    """Formatter should be used as an abstract base class.

    Formatter classes should inherit from this class and implement
    their own .format() method which should return a string. A
    transcript is represented by a List of Dictionary items.
    """

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        raise NotImplementedError(
            "A subclass of Formatter must implement "
            "their own .format_transcript() method."
        )

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs):
        raise NotImplementedError(
            "A subclass of Formatter must implement "
            "their own .format_transcripts() method."
        )


class PrettyPrintFormatter(Formatter):
    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        """Pretty prints a transcript.

        :param transcript:
        :return: A pretty printed string representation of the transcript.
        """
        return pprint.pformat(transcript.to_raw_data(), **kwargs)

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        """Converts a list of transcripts into a JSON string.

        :param transcripts:
        :return: A JSON string representation of the transcript.
        """
        return pprint.pformat(
            [transcript.to_raw_data() for transcript in transcripts], **kwargs
        )


class JSONFormatter(Formatter):
    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        """Converts a transcript into a JSON string.

        :param transcript:
        :return: A JSON string representation of the transcript.
        """
        return json.dumps(transcript.to_raw_data(), **kwargs)

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        """Converts a list of transcripts into a JSON string.

        :param transcripts:
        :return: A JSON string representation of the transcript.
        """
        return json.dumps(
            [transcript.to_raw_data() for transcript in transcripts], **kwargs
        )


class TextFormatter(Formatter):
    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        """Converts a transcript into plain text with no timestamps.

        :param transcript:
        :return: all transcript text lines separated by newline breaks.
        """
        return "\n".join(line.text for line in transcript)

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        """Converts a list of transcripts into plain text with no timestamps.

        :param transcripts:
        :return: all transcript text lines separated by newline breaks.
        """
        return "\n\n\n".join(
            [self.format_transcript(transcript, **kwargs) for transcript in transcripts]
        )


class _TextBasedFormatter(TextFormatter):
    def _format_timestamp(self, hours: int, mins: int, secs: int, ms: int) -> str:
        raise NotImplementedError(
            "A subclass of _TextBasedFormatter must implement "
            "their own .format_timestamp() method."
        )

    def _format_transcript_header(self, lines: Iterable[str]) -> str:
        raise NotImplementedError(
            "A subclass of _TextBasedFormatter must implement "
            "their own _format_transcript_header method."
        )

    def _format_transcript_helper(
        self, i: int, time_text: str, snippet: FetchedTranscriptSnippet
    ) -> str:
        raise NotImplementedError(
            "A subclass of _TextBasedFormatter must implement "
            "their own _format_transcript_helper method."
        )

    def _seconds_to_timestamp(self, time: float) -> str:
        """Helper that converts `time` into a transcript cue timestamp.

        :reference: https://www.w3.org/TR/webvtt1/#webvtt-timestamp

        :param time: a float representing time in seconds.
        :type time: float
        :return: a string formatted as a cue timestamp, 'HH:MM:SS.MS'
        :example:
        >>> self._seconds_to_timestamp(6.93)
        '00:00:06.930'
        """
        # work on whole milliseconds so that carries are handled (1.9999 -> 00:00:02.000,
        # never 00:00:01.1000)
        total_ms = int(round(max(float(time), 0.0) * 1000))
        hours, remainder = divmod(total_ms, 3_600_000)
        mins, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return self._format_timestamp(hours, mins, secs, ms)

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        """A basic implementation of WEBVTT/SRT formatting.

        :param transcript:
        :reference:
        https://www.w3.org/TR/webvtt1/#introduction-caption
        https://www.3playmedia.com/blog/create-srt-file/
        """
        lines = []
        for i, line in enumerate(transcript):
            end = line.start + line.duration
            time_text = "{} --> {}".format(
                self._seconds_to_timestamp(line.start),
                self._seconds_to_timestamp(
                    transcript[i + 1].start
                    if i < len(transcript) - 1 and transcript[i + 1].start < end
                    else end
                ),
            )
            lines.append(self._format_transcript_helper(i, time_text, line))

        return self._format_transcript_header(lines)


class SRTFormatter(_TextBasedFormatter):
    def _format_timestamp(self, hours: int, mins: int, secs: int, ms: int) -> str:
        return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, mins, secs, ms)

    def _format_transcript_header(self, lines: Iterable[str]) -> str:
        return "\n\n".join(lines) + "\n"

    def _format_transcript_helper(
        self, i: int, time_text: str, snippet: FetchedTranscriptSnippet
    ) -> str:
        return "{}\n{}\n{}".format(i + 1, time_text, snippet.text)


class WebVTTFormatter(_TextBasedFormatter):
    def _format_timestamp(self, hours: int, mins: int, secs: int, ms: int) -> str:
        return "{:02d}:{:02d}:{:02d}.{:03d}".format(hours, mins, secs, ms)

    def _format_transcript_header(self, lines: Iterable[str]) -> str:
        return "WEBVTT\n\n" + "\n\n".join(lines) + "\n"

    def _format_transcript_helper(
        self, i: int, time_text: str, snippet: FetchedTranscriptSnippet
    ) -> str:
        return "{}\n{}".format(time_text, snippet.text)


class TimestampedTextFormatter(TextFormatter):
    """One line per snippet, prefixed with its start time: ``[01:15] some text``."""

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        always_hours = kwargs.get("always_hours", False)
        return "\n".join(
            "[{}] {}".format(format_timestamp(s.start, always_hours), s.text)
            for s in transcript
        )


class ParagraphTextFormatter(TextFormatter):
    """Readable prose: snippets merged into paragraphs, separated by blank lines.

    Accepts the keyword arguments of `segments.to_paragraphs` (max_gap, min_chars,
    max_chars).
    """

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        return "\n\n".join(p.text for p in to_paragraphs(transcript, **kwargs))


class MarkdownFormatter(TextFormatter):
    """Markdown document with one paragraph per block and clickable timestamps."""

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        lines = [
            "# Transcript: {}".format(transcript.video_id),
            "",
            "- Language: {} (`{}`){}".format(
                transcript.language,
                transcript.language_code,
                ", auto-generated" if transcript.is_generated else "",
            ),
            "- Video: https://www.youtube.com/watch?v={}".format(transcript.video_id),
            "",
        ]
        for paragraph in to_paragraphs(transcript, **kwargs):
            lines.append(
                "**[{}]({})** {}".format(
                    paragraph.timestamp,
                    paragraph.link(transcript.video_id),
                    paragraph.text,
                )
            )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        return "\n\n---\n\n".join(
            self.format_transcript(transcript, **kwargs) for transcript in transcripts
        )


class CSVFormatter(TextFormatter):
    """CSV with the columns video_id, language_code, start, duration, end, text."""

    COLUMNS = ["video_id", "language_code", "start", "duration", "end", "text"]

    def _write(self, transcripts: List[FetchedTranscript]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(self.COLUMNS)
        for transcript in transcripts:
            for s in transcript:
                writer.writerow(
                    [
                        transcript.video_id,
                        transcript.language_code,
                        s.start,
                        s.duration,
                        round(s.start + s.duration, 3),
                        s.text,
                    ]
                )
        return buffer.getvalue()

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        return self._write([transcript])

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        return self._write(transcripts)


class JSONLinesFormatter(TextFormatter):
    """JSON Lines: one JSON object per snippet. Ideal for datasets and pipelines."""

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        kwargs.setdefault("ensure_ascii", False)
        return "\n".join(
            json.dumps(
                {
                    "video_id": transcript.video_id,
                    "language_code": transcript.language_code,
                    **snippet,
                },
                **kwargs,
            )
            for snippet in transcript.to_raw_data()
        )

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        return "\n".join(self.format_transcript(t, **kwargs) for t in transcripts)


class HTMLFormatter(TextFormatter):
    """A self-contained, mobile-friendly HTML page with clickable timestamps."""

    _STYLE = (
        ":root{color-scheme:light dark}"
        "body{font:17px/1.7 system-ui,'Noto Sans Devanagari',sans-serif;"
        "max-width:46rem;margin:2rem auto;padding:0 1rem}"
        "h1{font-size:1.4rem}h2{font-size:1.15rem;margin-top:2.5rem}"
        "p{margin:.8rem 0}a.t{font-variant-numeric:tabular-nums;font-weight:600;"
        "text-decoration:none;margin-right:.5rem}small{opacity:.7}"
    )

    def _section(self, transcript: FetchedTranscript, **kwargs) -> str:
        parts = [
            '<section lang="{}">'.format(html.escape(transcript.language_code)),
            "<h2>{} <small>({}{})</small></h2>".format(
                html.escape(transcript.video_id),
                html.escape(transcript.language),
                ", auto-generated" if transcript.is_generated else "",
            ),
        ]
        for paragraph in to_paragraphs(transcript, **kwargs):
            parts.append(
                '<p><a class="t" href="{}">{}</a>{}</p>'.format(
                    html.escape(paragraph.link(transcript.video_id)),
                    paragraph.timestamp,
                    html.escape(paragraph.text),
                )
            )
        parts.append("</section>")
        return "\n".join(parts)

    def _document(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        title = (
            "Transcript {}".format(transcripts[0].video_id)
            if len(transcripts) == 1
            else "{} transcripts".format(len(transcripts))
        )
        return (
            '<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>{title}</title>\n<style>{style}</style>\n</head>\n<body>\n"
            "<h1>{title}</h1>\n{body}\n</body>\n</html>\n"
        ).format(
            lang=html.escape(transcripts[0].language_code) if transcripts else "en",
            title=html.escape(title),
            style=self._STYLE,
            body="\n".join(self._section(t, **kwargs) for t in transcripts),
        )

    def format_transcript(self, transcript: FetchedTranscript, **kwargs) -> str:
        return self._document([transcript], **kwargs)

    def format_transcripts(self, transcripts: List[FetchedTranscript], **kwargs) -> str:
        return self._document(transcripts, **kwargs)


class FormatterLoader:
    TYPES = {
        "json": JSONFormatter,
        "pretty": PrettyPrintFormatter,
        "text": TextFormatter,
        "webvtt": WebVTTFormatter,
        "srt": SRTFormatter,
        "timestamped": TimestampedTextFormatter,
        "paragraphs": ParagraphTextFormatter,
        "markdown": MarkdownFormatter,
        "csv": CSVFormatter,
        "jsonl": JSONLinesFormatter,
        "html": HTMLFormatter,
    }

    class UnknownFormatterType(Exception):
        def __init__(self, formatter_type: str):
            super().__init__(
                "The format '{formatter_type}' is not supported. "
                "Choose one of the following formats: {supported_formatter_types}".format(
                    formatter_type=formatter_type,
                    supported_formatter_types=", ".join(FormatterLoader.TYPES.keys()),
                )
            )

    def load(self, formatter_type: str = "pretty") -> Formatter:
        """
        Loads the Formatter for the given formatter type.

        :param formatter_type:
        :return: Formatter object
        """
        if formatter_type not in FormatterLoader.TYPES.keys():
            raise FormatterLoader.UnknownFormatterType(formatter_type)
        return FormatterLoader.TYPES[formatter_type]()
