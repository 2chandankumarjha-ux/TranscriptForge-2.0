# TranscriptForge

An advanced toolkit for getting **YouTube transcripts / subtitles** (manual, auto-generated and translated) with Python or from the command line. No API key, no headless browser.

TranscriptForge is a fork of the excellent [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api) by Jonas Depoix (MIT). Its YouTube layer is kept as is, and a large toolbox is built on top: batch downloads, caching, search, analytics, cleaning, RAG chunking, many export formats, and first-class Hindi/Devanagari handling. See [NOTICE.md](NOTICE.md).

## What is new compared to upstream

| | upstream | TranscriptForge |
|---|---|---|
| Input | video id only | id **or any YouTube URL** (watch, youtu.be, shorts, embed, live, music); playlists and channels |
| Missing language | `NoTranscriptFound` | `fetch_best()` translates or falls back to another language |
| Many videos | write your own loop | `fetch_many()` parallel, retries, proxy rotation, per-video results, async |
| Repeated runs | download again | on-disk `TranscriptCache` with TTL |
| Formats | json, pretty, text, srt, webvtt | + **markdown, html, csv, jsonl, timestamped, paragraphs** |
| Processing | none | clean, paragraphs, time/char chunks, search, stats, extractive summary |
| Hindi / Sanskrit | works | tokenizer and search that keep matras and conjuncts intact, readable (non-`\u`) JSON |
| CLI | one command | batch files, playlists, `--output-dir/--zip`, `--search`, `--stats`, `--chunks`, ... |
| Tests | 100 % coverage | 100 % coverage (200+ tests) |

## Install

```bash
pip install .                    # from this folder
pip install -e ".[test,dev]"     # for development
```

Python 3.8+. Dependencies: `requests`, `defusedxml`.

## Quick start

```python
from transcriptforge import TranscriptForge

forge = TranscriptForge()
transcript = forge.fetch("https://youtu.be/GJLlxj_dtq8", languages=["hi", "en"])

for snippet in transcript:
    print(snippet.start, snippet.text)
```

`fetch()` is identical to upstream's, except that it also understands URLs.

### Smarter language handling

```python
# Hindi preferred. If it does not exist: translate an available transcript into Hindi,
# and if that is impossible too, use whatever exists (manual transcripts first).
transcript = forge.fetch_best(video, ["hi", "en"])

forge.fetch_best(video, ["en"], translate_to="hi")        # always translate
forge.fetch_best(video, ["xx"], best_effort=False)         # strict: raises NoTranscriptFound
```

### Many videos

```python
report = forge.fetch_many(
    ["id1", "https://youtu.be/id2", "id3"],
    languages=["hi", "en"],
    workers=3,                 # parallel threads (each has its own HTTP session)
    retries=2, backoff=2.0,    # blocked / network errors are retried with backoff
    min_delay=0.5,             # seconds between requests of one worker
    on_progress=lambda done, total, r: print(done, total, r.video_id, r.ok),
)

print(report.summary())            # "2/3 transcripts fetched in 4.1s (0 from cache); failed: VideoUnavailable x1"
for result in report.failed:
    print(result.video_id, result.error_type)
transcripts = report.transcripts   # successful ones, in input order

# asyncio
report = await forge.afetch_many(ids, ["en"])
```

One failing video never stops the others; every video gets a `BatchResult` (transcript or error, attempts, time, `from_cache`).

### Caching

```python
from transcriptforge import TranscriptForge, TranscriptCache

forge = TranscriptForge(cache=TranscriptCache("cache_dir", ttl_seconds=7 * 24 * 3600))
forge.fetch(video)   # downloads
forge.fetch(video)   # instant, from disk
```

The language *order*, formatting flag and translation target are part of the cache key. Use `ttl_seconds=None` to keep entries forever.

### Playlists and channels

```python
from transcriptforge import expand_source

ids = expand_source("https://www.youtube.com/playlist?list=PL...", limit=50)
```

This reads the first page YouTube serves (roughly the first 30 to 100 videos) and does not follow "load more". For bigger jobs, put the ids in a file and use `--file`.

## Processing transcripts

```python
from transcriptforge import (
    clean_transcript, to_paragraphs, chunk_by_chars, chunk_by_time,
    search_transcript, analyze_transcript, summarize,
)

t = clean_transcript(transcript)    # removes [Music], [संगीत], >>, duplicates, HTML; NFC; keeps ZWJ/ZWNJ

for p in to_paragraphs(t):          # readable paragraphs instead of 2-second fragments
    print(f"[{p.timestamp}] {p.text}  {p.link(t.video_id)}")

chunks = chunk_by_chars(t, max_chars=1000, overlap_chars=100)   # for embeddings / LLM context
windows = chunk_by_time(t, window_seconds=60)

for hit in search_transcript(t, "कृष्ण", whole_word=True, context=1):
    print(hit.timestamp, hit.url)   # https://youtu.be/<id>?t=<seconds>

stats = analyze_transcript(t)       # words, unique words, words/min, longest pause, keywords, phrases
for passage in summarize(t, passages=5):    # offline extractive summary, no model or API key
    print(passage.timestamp, passage.text)
```

### A note on Hindi, Sanskrit and other Indic scripts

Python's regex `\w` does not match Devanagari vowel signs, so naive code splits words like `कृष्ण` into pieces. TranscriptForge uses its own word class everywhere (tokenizing, keywords, whole-word search), treats the danda (`।` `॥`) as sentence punctuation, ships Hindi stopwords, and writes JSON with `ensure_ascii=False`, so files stay readable.

## Formats

| name | extension | notes |
|---|---|---|
| `text` | txt | one line per snippet |
| `paragraphs` | txt | merged into paragraphs |
| `timestamped` | txt | `[01:15] text` |
| `markdown` | md | headings and clickable timestamp links |
| `html` | html | standalone, mobile friendly page (escaped) |
| `srt`, `webvtt` | srt, vtt | subtitle files |
| `json`, `jsonl` | json, jsonl | JSON Lines = one snippet per line, good for datasets |
| `csv` | csv | video_id, language_code, start, duration, end, text |
| `pretty` | txt | Python pretty print |

```python
from transcriptforge import save_many, make_zip

save_many(report.transcripts, "out", formats=["text", "srt", "markdown", "json"])  # out/<id>.<lang>.<ext>
make_zip("out")                                                                    # out.zip
```

## Command line

```bash
transcriptforge GJLlxj_dtq8 --languages hi en --format text
transcriptforge "https://youtu.be/GJLlxj_dtq8" --list-transcripts

# batch: file with ids/URLs, 3 workers, cache, best effort, cleaned, saved as files + zip
transcriptforge --file video_ids.txt --workers 3 --cache-dir .cache --best-effort --clean \
    --languages hi en --output-dir out --formats text srt markdown --zip --progress

# whole playlist (first page), only the first 20 videos
transcriptforge --playlist "https://www.youtube.com/playlist?list=PL..." --limit 20 --output-dir out

# find things, get stats, summaries and RAG chunks
transcriptforge VIDEO --search "python" --context 1        # timestamps + deep links
transcriptforge VIDEO --search "कृष्ण|राम" --regex --whole-word
transcriptforge VIDEO --stats
transcriptforge VIDEO --summary 5
transcriptforge VIDEO --chunks 1000 --chunk-overlap 100    # JSON for LLM / RAG pipelines
```

`transcriptforge --help` lists every option. With `--output-dir`, a `_report.csv` status table is written for batch runs.

## Errors, blocks and proxies

All errors derive from `TranscriptForgeError` (`CouldNotRetrieveTranscript` for per-video problems): `TranscriptsDisabled`, `NoTranscriptFound`, `VideoUnavailable`, `VideoUnplayable`, `AgeRestricted`, `InvalidVideoId`, `NotTranslatable`, `TranslationLanguageNotAvailable`, `PoTokenRequired`, `RequestBlocked`, `IpBlocked`, `YouTubeRequestFailed`, ...

**YouTube blocks most cloud IPs** (AWS, GCP, Azure, and often Google Colab) and sometimes home IPs after many requests. You then get `RequestBlocked` / `IpBlocked`. Options:

```python
from transcriptforge import TranscriptForge, GenericProxyConfig, WebshareProxyConfig

TranscriptForge(proxy_config=WebshareProxyConfig("user", "password"))       # rotating residential proxies
TranscriptForge(proxy_config=GenericProxyConfig(https_url="https://user:pw@host:port"))

# a pool: workers are spread over it, and a blocked request moves on to the next proxy
pool = [GenericProxyConfig(https_url=u, http_url=u) for u in ["http://p1:8080", "http://p2:8080"]]
forge.fetch_many(ids, proxy_pool=pool, workers=2)
```

CLI: `--webshare-proxy-username/--webshare-proxy-password`, `--http-proxy`, `--https-proxy`, `--proxy-file proxies.txt` (one URL per line).

Without proxies, keep `workers` low (2 to 5) and use `min_delay` and the cache.

## Migrating from `youtube-transcript-api`

```python
# before
from youtube_transcript_api import YouTubeTranscriptApi
# after
from transcriptforge import TranscriptForge
```

The old names `YouTubeTranscriptApi` and `YouTubeTranscriptApiException` still exist as aliases, so `from transcriptforge import YouTubeTranscriptApi` keeps old code working. The CLI is now `transcriptforge`.

One intentional behaviour change: YouTube URLs are now accepted instead of raising `InvalidVideoId`.

## Limitations (please read)

- Like upstream, this uses YouTube's **undocumented** endpoints. YouTube changes them from time to time, and then fetching breaks until the upstream project ships a fix. If that happens, compare `transcriptforge/_transcripts.py` with upstream's current version.
- Playlist/channel expansion is best effort (first page only).
- `summarize()` is frequency based and extractive. It picks key passages; it does not write new sentences like an LLM.
- Respect YouTube's terms of service and creators' rights when you store or republish transcripts.

## Development

```bash
pip install -e ".[test,dev]"
pytest transcriptforge
coverage run -m pytest transcriptforge && coverage report -m --fail-under=100
ruff format transcriptforge && ruff check transcriptforge
```

The tests replay recorded YouTube responses (upstream's fixtures), so they run offline.

## Project layout

```
transcriptforge/
  _api.py          TranscriptForge: fetch, fetch_best, fetch_many, list
  _transcripts.py  YouTube access and parsing (from upstream)
  batch.py         parallel engine, retries, proxy rotation, reports
  cache.py         on-disk cache, JSON load/save
  sources.py       playlist / channel expansion
  cleaning.py  segments.py  search.py  analysis.py
  formatters.py  export.py  _cli.py  proxies.py  _errors.py  utils.py
examples/          quickstart.py, Colab notebook, sample id list
```

## License

MIT. Original work (c) 2018 Jonas Depoix; modifications (c) 2026 TranscriptForge contributors. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
