# Attribution

TranscriptForge is a derivative work of
**[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)**
by Jonas Depoix, which is released under the MIT License.

- Based on upstream version **1.2.4** (commit `b5c3339`, 2026-10-30).
- The network layer that talks to YouTube (`_transcripts.py`, `_errors.py`,
  `proxies.py`) is upstream's code, only renamed. Without it none of this would work.
- Everything else (batch engine, cache, search, analytics, cleaning, segmentation,
  new formatters, export, extended CLI, tests for all of these) was added in
  TranscriptForge 2.0.

The original MIT license and copyright notice are kept in [LICENSE](LICENSE), as the
license requires. If TranscriptForge is useful to you, please also star and support
the upstream project.
