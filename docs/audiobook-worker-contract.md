# Audiobook worker contract

This is the interface between lncrawler (prod) and the audiobook worker, the machine that runs Castwright on a lent GPU.

- **lncrawler side:** owns everything in [audiobooks-plan.md](audiobooks-plan.md).
- **Worker side:** owns the worker and how it drives Castwright, encodes and checks the audio.

Neither side relies on anything outside this file. Version: `v1`, sent by the worker as `X-Worker-Contract: 1`.

## Auth

- **Token:** every call sends `Authorization: Token <token>`. The token belongs to a Django user in the `audiobook_workers` group, and the admin creates and revokes it.
- **Who calls whom:** all calls go from the worker to prod over HTTPS. Prod never calls the worker.
- **Base URL:** `<LNCRAWLER_URL>/api/audiobook-worker/`.
- **Worker id:** `claim` and `ping` carry `worker_id` in the body. Every other call sends it as the `X-Worker-Id` header (400 if missing). A worker id belongs to the account that first used it: the same id from another token gets `403` on `claim`/`ping` and `409` on part calls. Get a token with `manage.py create_audiobook_worker <username>` on prod.
- **Bodies:** JSON objects only. Booleans (`retryable`, `available`) must be real JSON booleans, and `progress` a number; anything else is `400`.

## Endpoints

| Method | Path | Request | Response |
|---|---|---|---|
| `POST` | `claim` | `{worker_id, version, languages: [..]}` | `200` with a **Claim** (below), or `204` when there's nothing to do. Poll again after `Retry-After` seconds. |
| `GET` | `parts/<part_id>/epub` | none | The part as EPUB 3. |
| `POST` | `parts/<part_id>/heartbeat` | `{progress: 0..1, stage, message}` | `200 {"status": "ok"}`. It only records progress, stage and message for the admin. `409` means the part was cancelled or reassigned: stop and discard it. |
| `PUT` | `parts/<part_id>/chapters/<chapter_id>` | Body: the audio file. Headers: `Content-Type: audio/ogg`, `X-Content-SHA256`, and a real `Content-Length` (no chunked transfer: prod reads a chunked body as empty). Max 64 MB. | `201`. Re-sending the same hash is `200` (idempotent). `400` means the file failed validation, with the reason in the body. `413` means it's too big. |
| `POST` | `parts/<part_id>/complete` | `{qa, engine, engine_version}` | `200`. `400` if a chapter is missing, with the missing ids in the body. A `cast` key sent by an older worker is ignored. |
| `POST` | `parts/<part_id>/fail` | `{error, retryable: bool}` | `200` |
| `POST` | `ping` | `{worker_id, version, languages, available: bool, message}` | `200`. Send it every 5 min while the worker runs, even when idle, so the admin can see the worker is online. |

A claimed part has no time limit: nothing takes it back on a timer. The worker keeps it until it completes or fails it, or until an admin unpins its audiobook.

A worker that calls `claim` while it holds a part gets that same part back, with the same generation and the uploads it already sent. Work is cut at claim time: when nothing is queued for the worker, `claim` cuts the next part of its pinned book, or of a new book, from the chapters in the languages the worker sent. The cut happens only while the audio disk budget allows it; otherwise the answer is `204`.

## Claim

```json
{
  "part_id": "uuid",
  "audiobook_id": "uuid",
  "series": {"title": "Novel title", "authors": ["…"], "language": "en", "slug": "novel-slug", "synopsis": "…", "tags": ["…"]},
  "part": {"index": 3, "total_known": 8, "chapter_start": 51, "chapter_end": 75, "word_count": 74210},
  "chapters": [{"chapter_id": 1234, "number": 51, "title": "51. …", "word_count": 2950}],
  "epub_url": "https://…/api/audiobook-worker/parts/<id>/epub"
}
```

In a claim, `chapters[].chapter_id` is the Chapter primary key (it is the `<chapter_id>` used in the upload URL), and `number` is the chapter's own number.

A part is a run of whole chapters of about 75,000 words. Prod chooses the run and fixes it for good, so it can be anything from a single very long chapter up to many short ones.

`claim` only offers parts whose audiobook language is in the worker's `languages`. `languages` is a list of language codes (`en`, `fr`, ...), lower-cased by prod, at most 20 entries; a bad value is `400`. A missing `languages` means `["en"]`, so an old worker keeps getting English books only. Prod starts new books only in the languages the claiming worker sends. The worker alone decides which engines and voices it uses; prod records what it reports (`engine`, `engine_version`, the QA result) and ignores the `cast` and `engine_profiles` keys sent by older workers.

The EPUB carries `calibre:series` = series title, `calibre:series_index` = part index, `dc:creator` = authors, `dc:language`, one XHTML file per chapter, in the order of `chapters`. The heading of each chapter file equals the claim `title` (both come from `Chapter.display_title`'s labeler in the source's language), and the worker rejects the part when they differ.

Prod pins each audiobook to the worker that claimed its first part, so all parts of a novel go through the same worker workspace and its series memory. A pin is never released by time. A worker that dies keeps its audiobook pinned: an admin unpins it (the "Unpin worker" action), its claimed parts go back to the queue, and any worker may claim them. Several workers may run at once, each with its own `worker_id`.

## Audio format

Prod checks every upload with `ffprobe` and rejects anything outside these limits. That's what keeps prod's disk use predictable, so the worker does all the encoding and compression.

| | Required |
|---|---|
| Container / codec | Ogg / Opus |
| Channels | 1 (mono) |
| Bitrate | VBR, target 24 kbps. Rejected above 40 kbps on average. |
| Sample rate | 48 kHz (Opus native) |
| Loudness | Integrated −18 LUFS ±1, true peak ≤ −1.5 dBTP (two-pass `loudnorm`) |
| Silence | Leading and trailing silence trimmed to ≤ 0.5 s. Internal pauses ≤ 3 s. |
| One file | One chapter, from its title to its last line. The chapter title is read at the start. |
| Duration | Must be > 10 s and within ±1 % of the container's declared duration. |

Reference command, per chapter, after concatenating Castwright's output for that chapter:

```bash
ffmpeg -i chapter.wav -af "silenceremove=start_periods=1:start_threshold=-50dB:stop_periods=-1:stop_duration=3:stop_threshold=-50dB,loudnorm=I=-18:TP=-1.5:LRA=11" -ac 1 -ar 48000 -c:a libopus -b:a 24k -vbr on -application audio chapter.ogg
```

That reference command does one `loudnorm` pass. Run two passes in production.

Don't add tags or cover art: prod writes all metadata after upload.

That's about 10.8 MB per hour of audio. A 25-chapter part (~8 h) is ~90 MB.

## `complete` payload

- **`qa`:** `{passed: bool, checks: {name: {value, threshold, passed}}, notes}`, filled in by the worker's own checks. Prod stores it for the admin to read. It does not hide the part: a part is listenable once it is done, whether or not `passed` is true.
- **`engine`, `engine_version`:** required. For example `engine: "castwright+kokoro"`, `engine_version: "castwright@3a52b28 kokoro-v1.0"`. Prod stores them on the part and builds the narrator credits from them. This is how prod keeps track of which engine made each part as new engines are added.
- **`cast`:** not used any more. Prod ignores it, so an older worker that still sends it keeps working. Do not send it.
