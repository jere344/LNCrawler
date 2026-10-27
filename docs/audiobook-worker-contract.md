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
| `POST` | `claim` | `{worker_id, version, engine_profiles: [..]}` | `200` with a **Claim** (below), or `204` when there's nothing to do. Poll again after `Retry-After` seconds. |
| `GET` | `parts/<part_id>/epub` | none | The part as EPUB 3. |
| `POST` | `parts/<part_id>/heartbeat` | `{progress: 0..1, stage, message}` | `200 {lease_until}`. `409` means the part was cancelled or reassigned: stop and discard it. |
| `PUT` | `parts/<part_id>/chapters/<chapter_id>` | Body: the audio file. Headers: `Content-Type: audio/ogg`, `X-Content-SHA256`, and a real `Content-Length` (no chunked transfer: prod reads a chunked body as empty). Max 64 MB. | `201`. Re-sending the same hash is `200` (idempotent). `400` means the file failed validation, with the reason in the body. `413` means it's too big. |
| `POST` | `parts/<part_id>/complete` | `{cast, qa, engine, engine_version}` | `200`. `400` if a chapter is missing, with the missing ids in the body. |
| `POST` | `parts/<part_id>/fail` | `{error, retryable: bool}` | `200` |
| `POST` | `ping` | `{worker_id, version, engine_profiles, available: bool, message}` | `200`. Send it every 5 min while the worker runs, even when idle, so the admin can see the worker is online. |

A part's **lease** is 15 minutes, and each heartbeat extends it. An expired lease sends the part back to the queue.

## Claim

```json
{
  "part_id": "uuid",
  "audiobook_id": "uuid",
  "series": {"title": "Novel title", "authors": ["…"], "language": "en", "slug": "novel-slug"},
  "part": {"index": 3, "total_known": 8, "chapter_start": 51, "chapter_end": 75, "word_count": 74210},
  "chapters": [{"chapter_id": 1234, "number": 51, "title": "Chapter 51: …", "word_count": 2950}],
  "epub_url": "https://…/api/audiobook-worker/parts/<id>/epub",
  "engine_profile": "qwen-mixed",
  "previous_cast": {"Narrator": {"engine": "qwen", "voice": "…"}, "Mara": {"…": "…"}},
  "lease_until": "2026-11-02T03:15:00Z"
}
```

In a claim, `chapters[].chapter_id` is the Chapter primary key (it is the `<chapter_id>` used in the upload URL), and `number` is the chapter's own number.

A part is a run of whole chapters of about 75,000 words. Prod chooses the run and fixes it for good, so it can be anything from a single very long chapter up to many short ones.

`claim` only offers parts whose `engine_profile` is in the `engine_profiles` the worker sent. Profiles are free-text names agreed between the two sides (`kokoro` and `qwen-mixed` today). Adding an engine means the worker announces a new profile and the admin assigns it to audiobooks; prod needs no code change.

The EPUB carries `calibre:series` = series title, `calibre:series_index` = part index, `dc:creator` = authors, `dc:language`, one XHTML file per chapter, in the order of `chapters`.

Prod pins each audiobook to the worker that claimed its first part, so all parts of a novel go through the same Castwright workspace and its series memory. `previous_cast` is a copy of the cast prod has on record, so the worker can check its series memory against it or rebuild it.

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

- **`cast`:** `{character: {engine, voice, model?, gender?, role: "narrator"|"main"|"minor"}}`. It covers every speaking character in this part. Prod shows it on the audiobook page and passes it back as `previous_cast` on the next claim.
- **`qa`:** `{passed: bool, checks: {name: {value, threshold, passed}}, notes}`, filled in by the worker's own checks. When `passed` is false, prod keeps the part unpublished until the admin listens to it.
- **`engine`, `engine_version`:** required. For example `engine: "castwright+kokoro"`, `engine_version: "castwright@3a52b28 kokoro-v1.0"`. Prod stores them on the part and builds the narrator credits from them. This is how prod keeps track of which engine made each part as new engines are added.
- **Per-character engine:** each `cast` entry carries the engine of that voice, because a mixed profile uses several.
