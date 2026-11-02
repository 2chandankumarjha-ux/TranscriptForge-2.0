import csv
import re
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

from ._transcripts import FetchedTranscript
from .batch import BatchReport
from .formatters import FormatterLoader

FORMAT_EXTENSIONS = {
    "json": "json",
    "jsonl": "jsonl",
    "pretty": "txt",
    "text": "txt",
    "paragraphs": "txt",
    "timestamped": "txt",
    "srt": "srt",
    "webvtt": "vtt",
    "markdown": "md",
    "csv": "csv",
    "html": "html",
}

_FORMAT_KWARGS = {
    "json": {"ensure_ascii": False, "indent": 2},
    "jsonl": {},
}


def _safe(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._") or "transcript"


def format_transcript(transcript: FetchedTranscript, fmt: str) -> str:
    """Formats a transcript; non-ASCII text (Hindi etc.) is kept readable in JSON."""
    return (
        FormatterLoader()
        .load(fmt)
        .format_transcript(transcript, **_FORMAT_KWARGS.get(fmt, {}))
    )


def save_transcript(
    transcript: FetchedTranscript,
    directory: Union[str, Path],
    fmt: str = "text",
    filename: Optional[str] = None,
) -> Path:
    """Saves one transcript as ``<directory>/<video_id>.<lang>.<ext>`` (UTF-8)."""
    extension = FORMAT_EXTENSIONS.get(fmt, "txt")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = filename or "{}.{}".format(
        _safe(transcript.video_id), _safe(transcript.language_code)
    )
    path = directory / "{}.{}".format(name, extension)
    path.write_text(format_transcript(transcript, fmt), encoding="utf-8", newline="\n")
    return path


def save_many(
    transcripts: Iterable[FetchedTranscript],
    directory: Union[str, Path],
    formats: Sequence[str] = ("text",),
) -> List[Path]:
    """Saves every transcript in every requested format."""
    return [
        save_transcript(transcript, directory, fmt)
        for transcript in transcripts
        for fmt in formats
    ]


def write_report_csv(report: BatchReport, path: Union[str, Path]) -> Path:
    """Writes a one-row-per-video status table (handy to find what failed)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "video_id",
        "ok",
        "language_code",
        "is_generated",
        "snippets",
        "error_type",
        "error",
        "attempts",
        "from_cache",
        "elapsed",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for result in report.results:
            row = result.to_dict()
            row["error"] = " ".join(row["error"].split())
            writer.writerow(row)
    return path


def make_zip(
    source: Union[str, Path], zip_path: Optional[Union[str, Path]] = None
) -> Path:
    """Zips a directory (or a single file) and returns the path of the archive."""
    source = Path(source)
    zip_path = (
        Path(zip_path)
        if zip_path
        else source.with_suffix(".zip")
        if source.is_file()
        else Path(str(source).rstrip("/\\") + ".zip")
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        if source.is_file():
            archive.write(source, source.name)
        else:
            for file in sorted(source.rglob("*")):
                if file.is_file() and file != zip_path:
                    archive.write(file, file.relative_to(source.parent))
    return zip_path
