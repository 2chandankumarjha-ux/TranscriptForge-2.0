# Changelog

## 2.0.0

TranscriptForge forks `youtube-transcript-api` 1.2.4 and keeps its API compatible.

### Renamed
- Package `youtube_transcript_api` -> `transcriptforge`; CLI `transcriptforge`.
- `YouTubeTranscriptApi` -> `TranscriptForge`,
  `YouTubeTranscriptApiException` -> `TranscriptForgeError`. The old names still work
  as aliases.

### Added
- **URL input everywhere**: `fetch()` / `list()` / CLI accept watch, youtu.be, shorts,
  embed, live and music URLs (this used to raise `InvalidVideoId`).
- `fetch_best()`: translates or falls back to another language instead of failing.
- `fetch_many()` / `afetch_many()`: parallel downloads, per-video results, retries with
  exponential backoff, proxy-pool rotation, progress callback.
- `TranscriptCache`: atomic on-disk cache with TTL.
- Playlist / channel expansion (`expand_source`), best effort (first page only).
- `clean_transcript`: removes `[Music]`, `>>`, duplicates, HTML; Unicode NFC; keeps ZWJ.
- `to_paragraphs`, `chunk_by_time`, `chunk_by_chars` (with overlap) for reading and RAG.
- `search_transcript`: plain/regex/whole-word search with timestamps and deep links.
- `analyze_transcript`, `extract_keywords`, `summarize`: offline analytics with English
  and Hindi stopwords and a Devanagari-safe tokenizer.
- New formats: `timestamped`, `paragraphs`, `markdown`, `csv`, `jsonl`, `html`.
- `save_transcript`, `save_many`, `make_zip`, `write_report_csv`.
- CLI: `--file`, `--playlist`, `--workers`, `--retries`, `--delay`, `--cache-dir`,
  `--output-dir`, `--formats`, `--zip`, `--clean`, `--best-effort`, `--search`,
  `--stats`, `--summary`, `--chunks`, `--proxy-file`, `--progress`,
  `--preserve-formatting`; JSON output keeps Hindi readable.

### Changed
- Packaging moved from Poetry to standard `pyproject.toml` (setuptools).
- `test_cli.py` no longer leaves `TranscriptForge` monkey-patched for other tests.
- The test that expected `InvalidVideoId` for YouTube URLs now asserts that they are
  converted (non-YouTube URLs still raise).
