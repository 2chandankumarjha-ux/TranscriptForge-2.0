# Changelog

## Unreleased

### Fixed
- **CLI exit code**: the process now exits with 1 when any video/source failed
  (it always exited 0 before). `--exclude-generated` together with
  `--exclude-manually-created` is now a usage error (exit 2) instead of printing
  nothing; the API raises `ValueError` for the same combination.
- **CLI crashes -> usage errors**: `--chunks/--chunk-overlap`, `--summary`, `--context`,
  `--retries`, `--limit`, `--workers`, `--delay` are validated; a missing `--proxy-file`
  no longer ends in a traceback; `--webshare-proxy-username/-password` must be given
  together (a missing password used to be sent as the text `None`).
- **Hindi output on legacy encodings**: printing to a redirected/cp1252/ASCII stream no
  longer raises `UnicodeEncodeError`.
- **Data loss in `save_many` / `--formats`**: formats that share an extension
  (`text`, `paragraphs`, `timestamped`, `pretty` -> `.txt`) silently overwrote each other.
  They now get the format name in the file name.
- **Parser** deleted text between a `<` and a later `>` (`"if x < 5 and y > 3"` became
  `"if x  3"`); only real tags are stripped now (also in `clean_text`).
- **SRT/WebVTT** could emit `00:00:01,1000` (invalid) for times just below a whole
  second; negative start times no longer produce `-1:59:59`.
- **Channel URLs** with a tab (`/@name/featured`, `/about`, `/playlists`) were turned
  into a 404 URL; `--playlist` given a `watch?v=..&list=..` link now expands the list.
- **Indic text**: ZWJ/ZWNJ no longer split conjuncts, and Bengali, Gurmukhi, Gujarati,
  Odia, Tamil, Telugu, Kannada, Malayalam and Sinhala words are no longer cut into
  pieces by the tokenizer / whole-word search; curly apostrophes match stopwords.
- `clean_text` no longer removes brackets glued to a word (`arr[i]`, `note[1]`).
- `is_video_id("<id>\n")` is False; a corrupt cache file holding valid non-object JSON
  is treated as a miss; negative `retries` no longer yield a failed result without an
  error; negative `limit` is rejected; `make_zip(".")` no longer creates `..zip`.

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
