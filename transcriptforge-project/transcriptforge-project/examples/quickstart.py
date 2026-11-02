"""TranscriptForge quick tour. Run: python examples/quickstart.py <video id or URL>"""

import sys

from transcriptforge import (
    TranscriptCache,
    TranscriptForge,
    analyze_transcript,
    clean_transcript,
    save_many,
    search_transcript,
    summarize,
    to_paragraphs,
)

source = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=GJLlxj_dtq8"

forge = TranscriptForge(cache=TranscriptCache("transcript_cache"))

# 1. Hindi first, then English; if neither exists, translate/fall back automatically
transcript = clean_transcript(forge.fetch_best(source, ["hi", "en"]))
print(f"{transcript.video_id}: {transcript.language} ({len(transcript)} snippets)")

# 2. Readable paragraphs with timestamps
for paragraph in to_paragraphs(transcript)[:3]:
    print(f"[{paragraph.timestamp}] {paragraph.text[:100]}")

# 3. Search -> deep links into the video
for hit in search_transcript(transcript, "the", whole_word=True, max_hits=3):
    print(hit.timestamp, hit.url)

# 4. Analytics + offline extractive summary
stats = analyze_transcript(transcript)
print(stats.word_count, "words,", stats.words_per_minute, "words/min")
print("keywords:", stats.top_keywords[:5])
for passage in summarize(transcript, passages=3):
    print(f"* [{passage.timestamp}] {passage.text}")

# 5. Many videos at once, in parallel, then save as files
report = forge.fetch_many([source], ["hi", "en"], workers=3)
print(report.summary())
save_many(report.transcripts, "output", formats=["text", "srt", "markdown", "json"])
