# Analysis

The worker analyses each part's EPUB itself, on the local LLM (llama-server, Qwen3.5 9B), and writes the cast and the sentences into the Castwright book. Castwright designs voices, renders and checks audio. It does no analysis.

## Flow for one part

1. Download the EPUB and import it into Castwright (chapters and titles).
2. Analysis. The TTS engines (`qwen`, `kokoro`) are unloaded to free the card. The chapters are analysed in order: a cast call, then attribution in chunks. The cast and manuscript slices are written to the book, and the series memory is saved.
3. The worker waits `LLM_IDLE_S` + 5 s, so llama-server has unloaded its weights before design.
4. Casting. `castConfirmed` is set before design, because Castwright writes designed voices only into confirmed casts. Qwen voices are designed for the main characters, and a failed design falls back to Kokoro.
5. The designed Qwen voices are saved into the series memory for the next parts.
6. Render, encode, upload, complete.

A restart resumes at the next unfinished chapter: each finished chapter is checkpointed in `analysis.json` in the part folder. A part whose analysis is written is not analysed again.

## Modules

- `worker/analysis/protocol.py`: the numbered quote runs the model reads (`numbered_pieces`, `quote_runs`, `render_runs`), the JSON reply parser, the language conventions of the prompts, and `AnalysisError`.
- `worker/analysis/cast.py`: cast detection for one chapter, resolved against the series memory, with evidence quotes.
- `worker/analysis/attribution.py`: speaker attribution per chunk of whole paragraphs (at most 9000 characters). A labelled quote run gives its speaker at confidence 0.9, a quote the model left unlabelled is the narrator at 0.5, and narration is the narrator at 0.95. A chunk that labels under 30% of its runs (with at least 5 runs) is retried as two halves.
- `worker/analysis/run.py`: `analyse_part`, which runs one part's chapters, checkpoints them, numbers the sentences across the part, and builds the cast rows.
- `worker/series.py`: the series memory.
- `worker/llm.py`: the llama-server client. It retries on errors and bad replies, writes one usage line per call to `DATA_DIR/llm-usage.jsonl`, and asks for a server restart when a call stalls.

## Series memory

One file per audiobook: `DATA_DIR/series/<audiobook_id>.json`. It holds each character's name, aliases, gender, age range, role, description, voice style, first and last chapter seen, lines, and designed voice; plus `chaptersSeen` and `analysedParts`.

- The prompts see the narrator and the characters seen within the last 100 chapters, most recent first, at most 80. Older characters stay in the file. A name or alias that matches one of them brings it back under its old id and voice.
- New ids are kebab-case slugs of the name, made unique with `-2`, `-3`.
- A part already in `analysedParts` is analysed on a copy of the memory, so its chapters and lines are counted once.
- An empty memory for a part above 1 is seeded from the previous part's Castwright book, found in the library by title.

## What Castwright needs written

- Slice `cast`: `{characters: [...]}`, replaced whole. Each row has `id`, `name`, `role`, `color`, and optionally `gender`, `ageRange`, `aliases`, `description`, `voiceStyle` and `evidence`. `voiceStyle` is always written, or Castwright asks its own LLM for one.
- Slice `manuscript`: `{sentences: [{id, chapterId, characterId, text, confidence}]}`, all chapters of the part in one write. Sentence ids are unique across the book.
- Slice `state`: `castConfirmed: true` before design, and `audioFormat: mp3` after it.

## Voice reuse

A character with a designed Qwen voice in the series memory keeps it in later parts. Its row carries `voiceId`, `voiceUuid`, `ttsEngine: "qwen"` and `overrideTtsVoices.qwen`, so design skips it and rendering uses the same voice. Castwright cannot change an existing `voiceUuid`, so the worker never resends a different voice for one. A kokoro part never sends Qwen voice keys.

## Not done

- Emotion tags: every line is neutral.
- Two parts at once, or analysing part N+1 while part N renders.
- Accuracy is measured on the bench only: [accuracy-benchmark.md](accuracy-benchmark.md).
