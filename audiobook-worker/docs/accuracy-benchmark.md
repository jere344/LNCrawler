# Speaker-attribution accuracy: how to benchmark it

Plan for measuring, and later improving, how well the worker's own analysis (`worker/analysis/`) gives each sentence
to the right speaker. It runs offline: no Castwright, no prod, only llama-server and the analysis code.

## What is measured

Each run analyses a bench EPUB with `analyse_part` and is scored against a hand-checked gold labelling.

- **acc%**: share of gold sentences whose speaker the run got right.
- **dlg_acc%**: the same, over gold sentences spoken by a character. This is the number that matters most:
  narration is nearly always right, and a wrong voice on a line of dialogue is what listeners notice.
- **narr_acc%**: the same, over gold narration. A drop here means narration is being voiced by characters.
- **unmatched**: gold sentences the scorer could not find in the run's text (see "Scoring" below). Not counted in
  the percentages, so watch it: a jump means the text changed (EPUB reader, segmenter), not the attribution.
- **wall_s**, prompt and completion tokens: speed and cost of the analysis, from `runs.jsonl` and the run's
  `<label>.usage.jsonl`.
- Cast quality (read, not scored yet): characters found, names, merged or split persons, unnamed side characters.

### Scoring (`bench/score.py compare`)

The worker's sentences and the gold's do not line up one to one (different segmentation, and the older gold files
carry Castwright's inline `[excited]`-style tags). So the scorer works on characters: per chapter, whitespace is
removed from both texts, each gold sentence is found in the run's text (searching forward from the last match,
within a bounded window), and it takes the run's speaker over those characters. A character speaker wins when it
covers at least 30% of the sentence (a quote with its speech tag counts as speech), else the majority speaker.
Run ids are mapped to gold ids by character overlap, so a run that calls the merchant `marchand` and the gold
`marchand-armes` still scores. Narrator maps to narrator.

## Data

| Set | EPUB | Gold | Content | Status |
|---|---|---|---|---|
| en | `bench/data/chaotic-part1.epub` | `bench/results/gold-chaotic-part1.json` | 2 chapters, 215 gold sentences, 18 dialogue, xianxia web novel (translated) | main target |
| fr | `bench/data/fr-digne-part1.epub` | `bench/results/gold-fr-digne-part1.json` | 2 chapters, 172 gold sentences, 36 dialogue, « … – … » dialogue style | main target |
| zh | `bench/data/zh-lizhi-part1.epub` | none | 3 chapters, 1806 pieces, “…” dialogue | smoke test only |

The EPUBs are the part EPUBs the local lncrawler stack built for the worker (download them from the part's
`epub_url` in a claim, or from the API while the part exists). Novel text is copyrighted: `bench/data/` and
`bench/results/` stay out of git (see `.gitignore`) and live on the dev machine only. Keep a copy of them; the
gold files are hand work.

The en and fr sets are small: one dialogue line is 5.6% (en) or 2.8% (fr) of dialogue accuracy. Treat differences
under ~3 points as noise (see Variance).

### Gold format

A bench export: `{"characters": [{"id", "name", "aliases", "gender", "lines"}], "sentences": [{"chapter_id",
"index", "text", "character_id"}]}`, plus optional per-sentence `note`, `mixed` (quote and its tag in one sentence)
and the file-level `changes` list from its review. en and fr were made by an Opus agent from a reference analysis,
reading the source text, with every change noted. Known gold caveats: fr sentence 1/54 is not in the source
chapter (kept for alignment), fr 2/37 is uncertain (Livius or another assassin).

### Adding a set

1. Get a part EPUB (2-3 chapters with a lot of dialogue, ideally several speakers and an unnamed side character).
2. Build the sentence list with the segmenter only, so the gold does not depend on any model:
   `worker.analysis.protocol.numbered_pieces(chapter.text, lang)` for each `worker.epub.read_chapters(...)` chapter, every
   sentence `narrator`.
3. Have a strong model (Opus) label speakers from the source text with these rules: narration (including reported
   speech and thoughts without quotes) is `narrator`; quoted text that is not speech (titles, terms, signs, cited
   proverbs) is `narrator` with a note; a quote and its tag in one sentence goes to the speaker (`mixed: true`);
   unnamed speakers get a stable descriptive id; uncertain cases get `"note": "uncertain: ..."`. Check the
   sentence count and texts are unchanged.
4. Skim the uncertain notes yourself, then add a row to the table above and a baseline below.

## Running

From `audiobook-worker/`, with the Castwright stack up (the script frees its sidecar's VRAM) and the
`lncrawler-llama:sm61` image and `llm-models` volume present:

```bash
docker build -q -t lncrawler-audiobook-worker:dev .
sh bench/run_native.sh <label> bench/data/chaotic-part1.epub
python -m bench.score compare --gold bench/results/gold-chaotic-part1.json --errors bench/results/<label>.json
```

`run_native.sh` starts llama-server with the production model arguments (Qwen3.5-9B-MTP Q4_K_M, 32k context, one
slot, MTP drafting, thinking off), except `--sleep-idle-seconds`: the bench keeps the model loaded between calls. It
restarts llama-server if it stalls. `LLM_GGUF=<file>` tries another model from the volume.
`bench_native.py run` writes the export `bench/results/<label>.json` (characters, numbered sentences), its usage in
`<label>.usage.jsonl` and a line with the wall time in `runs.jsonl`. `compare` prints one row per file: the gold scores
itself as a sanity row, then each run. `--errors` lists every gold sentence the run got wrong (gold speaker, run
speaker, text), `--exclude-text SUBSTR` drops sentences from scoring (repeatable), and `--json OUT` also writes the
rows. Stop the `llama`
container afterwards (`docker rm -f llama`) before rendering anything. Watch the GPU temperature on long series:
wait for it to cool under 65 °C when it passes 80 °C.

## Baselines (2026-10-29)

Qwen3.5-9B-MTP Q4_K_M on the GTX 1080, worker analysis as of the worker-side analysis change.

| Set | Run | acc% | dlg_acc% | narr_acc% | unmatched | wall_s |
|---|---|---|---|---|---|---|
| en | native2-en | 98.5 | 83.3 (15/18) | 100 | 12 | 67 |
| fr | native3-fr | 96.8 | 86.1 (31/36) | 100 | 15 | 76 |
| zh | native3-zh | — | — | — | — | 373 |

An earlier run scored 88.9% (32/36) on the French dialogue before an unrelated change. (Castwright's own analyzer,
which scored 57% on the same part, is no longer an option.) The unmatched counts come from Castwright's inline tags
in the en/fr gold texts.

## Known error classes (where to look first)

- **Addressee taken for the speaker** (en 1/102-104: "Rest well, Tianzi." given to Tianzi).
- **Untagged turns in a long exchange** (fr: Livius and Cicéron alternating, 2/37, 2/69).
- **Speaker named by a role** ("le premier", "le second", "l'Impériale"): fr 2/15, 2/20.
- **Unnamed side characters** (innkeeper, merchant): found when the cast call sees the whole chapter, missed when
  the chapter is cut into attribution-sized chunks. Cast detection now sees up to 24000 characters at once
  (`CAST_CHUNK_CHARS`); keep a check on this when changing chunking.
- **zh: quoted terms in narration** (“功德”, “敕令”, “轰”) are given to a character. Chinese uses the same marks for
  speech and for terms.

## Variance

Temperature is 0, but llama.cpp output still varies between runs (MTP drafting, batch shapes): the same French
setup scored 88.9 and 86.1 on dialogue. When comparing two versions, run each set three times and compare the
means; report the spread. A change is worth keeping when it moves dialogue accuracy by more than the spread on
both en and fr without lowering narration.

## Ideas to try later

1. Larger gold sets: 5-10 chapters per language, more speakers, a first-person novel.
2. A Chinese gold set once Chinese parts are on the roadmap, then rules for quoted terms (a quote of one or two
   words with no speech verb is narration).
3. Prompt work on the error classes above, one at a time, measured with the protocol above.
4. Give the attribution call the previous chapter's last exchange as context (today only the previous chunk of the
   same chapter).
5. A second pass on low-confidence runs only (escalation), with a larger model if one fits.
6. Score cast quality: duplicates and splits per series over a few consecutive parts.
