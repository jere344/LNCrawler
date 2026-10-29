# Server audiobooks: lncrawler implementation plan

Status: Phases 1–6 done. Phase 6 is not yet checked in a browser. The frontend audiobook page lives at `/audiobooks/<novel slug>/` (not `/novels/:n/:s/audiobook`), to match the SEO pages, sitemap and RSS links.

**Scope.** This plan covers the lncrawler side: prod database, jobs, API, files, admin and frontend. The GPU worker that runs Castwright is owned by another agent. The two sides only share [audiobook-worker-contract.md](audiobook-worker-contract.md), which covers the endpoints, the claim payload and the audio format.

**Goal.** Multi-voice audiobooks of the most popular novels, made every night, then advertised and listened to on the site:
- shown on the home page and on their own pages;
- streamed in a player that keeps going while you browse and remembers where you stopped;
- downloadable as properly tagged `.m4b` files with a cover;
- and manageable from the admin.

## Architecture

```
GPU worker (other agent)              prod
┌────────────────────────┐   HTTPS   ┌───────────────────────────────────────────┐
│ claim → Castwright →   │──────────►│ /api/audiobook-worker/*  (token, contract) │
│ encode Opus 24 kbps →  │           │   validate (ffprobe) → tag (mutagen) → disk │
│ QA → upload → complete │◄──────────│ scheduler: enqueue, reaper, staleness       │
└────────────────────────┘           │ supervisor job: build .m4b on demand        │
                                     │ public API · RSS · SEO                     │
                                     │ nginx: streams chapter .ogg (range)        │
                                     │ frontend: home, /audiobooks, player        │
                                     └───────────────────────────────────────────┘
```

## Key decisions

| Topic | Choice | Why |
|---|---|---|
| Compression | On the worker. The contract requires Ogg/Opus mono at 24 kbps VBR, loudness-normalised with silence trimmed. Prod rejects anything else with `ffprobe`. | Smallest transfer and prod disk use, about 10.8 MB per hour. Prod never re-encodes. |
| Stored format | One `.ogg` per chapter, stored once | Streams in every browser with range requests from nginx. It's also the source for the RSS feed and for `.m4b` downloads. |
| Download format | `.m4b` per part, in two flavours, both built on demand and cached together (size-capped LRU): **Opus**, remuxed from the chapter files with no re-encode (smallest, the default); **AAC**, transcoded once to AAC-LC 64 kbps mono, for Apple Books and older devices | Disk only holds one copy permanently. The AAC version is the same job with one more ffmpeg flag and the same tags. |
| Downloads | Open to everyone, no login, not throttled. | Reach. |
| Engine tracking | Each part stores the `engine` and `engine_version` that made it, and the cast stores one per character. | New engines can be added later without losing track of what made each part. Old parts can be regenerated with a new engine on purpose. |
| Metadata | Written by prod, never by the worker | Titles and authors can change on prod. Retagging is cheap, and the worker stays simple. |
| Unit of work | `AudiobookPart`: a run of **whole chapters** of one English `NovelFromSource`, cut by **word count**. Chapters are added in order while the total stays ≤ `AUDIOBOOK_PART_WORDS` (default 75,000 words ≈ 8 h at ~155 words per minute). A chapter is never split; one chapter longer than the target becomes a part on its own. Chapter ranges are frozen when the part is created. | Even workload per job and even download sizes, whatever the chapter lengths. Freezing keeps part numbers stable. It matches Castwright's "book" and its series memory: series = novel, index = part. |
| Last partial block | A part is only created once the remaining chapters reach the word target, or when the novel is completed and the tail hasn't changed for 14 days | Avoids regenerating a part every time a chapter is added. |
| Audiobooks per novel | At most one per novel **per language**, made from the novel's **preferred source**: the one the site shows first (`preferred_source_key`: votes, then chapters with content). Only English for now (`LANGUAGES` constant). | Same source readers see. Voices stay consistent within one language. |
| DMCA | Hidden, not deleted: public reads go through `public_novels` / `public_sources`. No new parts are queued for DMCA novels. | Unmarking DMCA brings everything back, and no prune task is needed. |
| Merges and splits | The audiobook follows its source to the new novel. If that novel already has one in the same language, the longer one is kept and the other is deleted (files and row). | No orphan audiobooks, and no admin step. |
| Word counts | New `Chapter.word_count` (nullable int): counted lazily from the stripped body when a part is cut, then stored | Today chapters have no word count, and reading every chapter's JSON file each night would be too slow. |
| Listening progress | A new `ListeningProgress` model, synced with `ReadingHistory` | One "continue" point whether you read or listened. |
| Storage path | `<source folder>/audio/part-NNN/NNNNN.ogg` and `<source folder>/audio/cover.jpg` | nginx already serves `/lightnovels/` (`nginx.conf.template:83`), and the files are removed with the source. |

**Disk budget.**
- **Permanent storage:** only the Opus chapter files. One part is ~8 h ≈ 90 MB, so 100 novels × 4 parts ≈ 36 GB.
- **Download cache:** both `.m4b` flavours (Opus ~90 MB per part, AAC ~230 MB per part) are temporary. They share one cache with a hard cap (`AUDIOBOOK_M4B_CACHE_GB`, default 5 GB). Least recently downloaded files are evicted first, and the daily housekeeping prunes it too.
- **Extra disk for AAC support:** none beyond that fixed cap. Eviction only costs a rebuild on the next download: seconds for Opus, a few minutes for AAC. `AUDIOBOOK_DISK_BUDGET_GB` stops new enqueues when it's reached, and the admin dashboard shows usage.

## Phase 1: models, settings, admin

`lncrawler_api/models/audiobook_models.py`:

- **`Audiobook`**
  - `novel` (FK, unique together with `language`), `language`, `source` (FK `NovelFromSource`)
  - `status`: `active` | `paused` | `retired`
  - `published`, `featured` (bool, home hero pick), `worker_id` (affinity)
  - `cover_path`, `total_duration_s`, `total_size_bytes`, `parts_done` (denormalised for listing queries)
  - `cast` (merged JSON of every part's cast), `credits` (engine and version strings)
  - `first_published_at`, `last_part_at` (feeds "new" badges and sorting)
- **`AudiobookPart`** (also the job)
  - `audiobook`, `index`, `chapter_start`, `chapter_end`, `word_count`, `estimated_duration_s` (words ÷ 155 wpm, shown before the part exists)
  - `engine`, `engine_version` (reported by the worker at `complete`)
  - `status`: `queued` | `claimed` | `done` | `failed` | `stale`
  - job fields: `priority`, `worker_id`, `claimed_at`, `lease_until`, `progress`, `stage`, `attempts`, `error_message`
  - `content_hash`, `cast`, `qa`, `qa_passed`, `approved` (admin override when QA fails)
  - `duration_s`, `size_bytes`, `completed_at`
  - unique `(audiobook, index)`
- **`AudiobookChapter`**
  - `part`, `chapter` (OneToOne `Chapter`), `file_path`, `duration_s`, `size_bytes`, `sha256`, `offset_s` (start within the part, used for `.m4b` chapter markers)
- **`AudiobookWorker`**
  - `worker_id`, `user`, `last_seen_at`, `version`, `available`, `message`
  - filled by `ping` and `claim`
- **`ListeningProgress`**
  - `user`, `audiobook`, `chapter` (FK), `position_s`, `speed`, `finished`, `updated_at`
  - unique `(user, audiobook)`
- **`AudiobookDailyStat`**
  - `audiobook`, `date`, `plays`, `downloads`, `listen_seconds`
  - feeds "most listened" and the admin

**Settings** (`settings.py` + `.env.example`):
Only what an operator tunes per deployment:
- `AUDIOBOOK_ENABLED`
- `AUDIOBOOK_PART_WORDS` (75000)
- `AUDIOBOOK_QUEUE_WORDS` (600000)
- `AUDIOBOOK_DISK_BUDGET_GB`, `AUDIOBOOK_M4B_CACHE_GB`

Tuning values are module constants in `services/audiobook_service.py` instead: `WORDS_PER_MINUTE` 155, `MAX_ATTEMPTS` 3, `LEASE_SECONDS` 900, `MAX_BITRATE_KBPS` 40, `TAIL_STABLE_DAYS` 14.

**Word counts:**
- `Chapter.word_count` (nullable). Prod has ~10M chapters, so nothing ever scans them all. Counts come from three places:
  - **at download:** the crawler counts each chapter's body while it's in memory (`_save_chapter` / `_restore_chapter`) and writes `word_count` into the chapter entry. `meta.json` keeps it, and `from_meta_json` stores it on import. Crawler and API share one counting function;
  - **lazily on use:** not set → count it from the body being read anyway and store it; set → read it. Used by the audiobook part cutting and by the "words read" counter in `users_views.py`, which loads the body already;
  - no backfill command: existing chapters get counted over time as they're used.
- A re-import clears it only when the chapter really changed (new URL, new number, or content that just arrived).
- Prod has no word counts today. An earlier `Chapter.word_count` (migration 0037) was removed in 0042.

**Image dependencies:**
- `mutagen` in `requirements.txt` (pure Python tagging); Pillow is already there.
- `ffmpeg`/`ffprobe` in the API Dockerfile apt list, in whichever image runs the supervisor jobs and the upload view.

**Django admin** (`admin/audiobook_admin.py`, in `app_groups.py`):

- **Audiobook list**
  - columns: cover thumbnail, novel, parts done/queued/failed, hours, size, published, featured, worker
  - actions: Publish / Unpublish, Feature, Pause / Resume, Enqueue next part, Delete audio files, Rebuild cover, Retag files
- **Part list**
  - shows status, progress and stage live
  - actions: Retry, Regenerate (high priority), Approve despite QA
  - QA checks shown as a table, with an inline `<audio>` player per chapter for spot listening
- **Novel admin:** a **Generate audiobook** action. This is the manual "run by admin" path.
- **Dashboard page** (custom template, like the scheduler one):
  - workers with last seen ("offline for 3 days" in red), queue length and est. nights to empty it
  - hours produced in the last 7 nights, failures, disk used vs budget
  - plays and downloads over the last 30 days

## Phase 2: scheduler tasks (`scheduler.py`)

The scheduler only runs tasks at fixed intervals; it has no time-of-day setting. So the enqueue task doesn't run once a night. It runs hourly and **tops the queue up** to `AUDIOBOOK_QUEUE_WORDS` words of queued work, about one night for the worker. The worker always finds work when it starts, and the queue never grows beyond what it can produce.

Logic lives in `services/audiobook_scheduler.py`. Every task does nothing while `AUDIOBOOK_ENABLED` is off.

- **`enqueue_audiobooks`** (hourly):
  - stops when queued + claimed words reach `AUDIOBOOK_QUEUE_WORDS`, or when audio disk use reaches `AUDIOBOOK_DISK_BUDGET_GB`;
  - **round robin**, one part per step, serving whoever has waited longest:
    - **started books:** active, with no part queued or in progress, and with a full next part available. They wait since `last_enqueued_at`. A book that has caught up with the latest releases drops out until enough new chapters arrive;
    - **the new-book slot:** it waits since the newest audiobook's `created_at`. Serving it starts the next most popular novel (`rank_week_views`, then `rank_total_views`) that has no audiobook in that language yet. It skips DMCA novels and novels with no English source. A novel qualifies once one full part can be cut, no empty Audiobook row is left behind, and the scan stops after 50 novels in a row that yield nothing;
    - ties go to the more popular novel, and the new-book slot loses ties;
    - effect: with N books in progress, a new book starts once every N+1 parts. The collection grows fast at first and slower as more books are in progress, a huge novel gets one part per cycle like any other, and the new-book slot comes round more often again as books catch up;
    - scheduler parts have priority 0 and are claimed in the order they were created, so the round order holds. Admin actions (Generate, Regenerate) use priority 100 and jump the queue;
  - parts are cut as in Phase 1 (whole chapters up to `AUDIOBOOK_PART_WORDS`).
- **`reap_audiobook_leases`** (every 5 min): sends parts with an expired lease back to the queue. After `MAX_ATTEMPTS` they become `failed`.
- **`audiobook_housekeeping`** (daily):
  - safety net for moved sources: any audiobook whose source now belongs to another novel follows it (`follow_source`). The move and split services already call it directly;
  - stale parts: only for sources re-imported since the part was last checked (`checked_at`, else `completed_at`). It recomputes `content_hash` and marks the part `stale` on a change. It never does a full scan, which would unpack archived sources, and a part with an unreadable chapter file is left alone and retried. Stale parts stay playable until regenerated.
- **Moved to the phases that create these files:**
  - removing leftover `.part` uploads goes to Phase 3;
  - pruning the `.m4b` cache and rebuilding the cover when the source cover changes go to Phase 4;
  - stats are counted directly by the Phase 5 endpoints, so no rollup task is needed.

## Phase 3: worker API (prod side of the contract)

`views/audiobook_worker_views.py` uses DRF `TokenAuthentication` and an `IsAudiobookWorker` permission (user in the `audiobook_workers` group). It implements every endpoint in the contract:

- **`claim`:** `select_for_update(skip_locked=True)`, ordered by priority. Affinity: the worker's own audiobooks first, then audiobooks with no worker. The first claim pins the audiobook. The response includes `previous_cast`.
- **`heartbeat`, upload, `complete`, `fail`:** every write is a conditional `UPDATE … WHERE id=… AND worker_id=… AND status='claimed'`, never a save of a part loaded earlier. Otherwise a late heartbeat could bring back a part the lease reaper has just requeued. Zero rows updated → `409`.
- **Part EPUB:** reuses `epub_service._build` with a chapter range and the `calibre:series` / `series_index` metadata. Built on request and not stored.
- **Upload pipeline:**
  1. Stream the body to `*.part` and check the SHA-256.
  2. Validate the format with `ffprobe` against the contract table (`400` with the reason on failure).
  3. Tag the file with mutagen (Vorbis comments: title, album, artist, tracknumber, language, comment = credits).
  4. Move it into place atomically.
- **`complete`:**
  - checks every chapter is present and computes the `offset_s` values
  - stores `cast`, `qa`, `engine` and `engine_version`, and merges the cast into `Audiobook.cast`
  - on a regenerated part, swaps the files atomically and drops that part's `.m4b` cache
  - updates the denormalised totals
  - publishes automatically if the audiobook is published and QA passed (or the admin approved)
- **nginx:** `location /api/audiobook-worker/` with `client_max_body_size 64m` and a longer `proxy_read_timeout`. Today there's no limit set, so the 1 MB default applies; the raise stays on this location only.
- **`manage.py audiobook_fake_worker`:** a dev-only command.
  - It claims parts and generates contract-valid Opus files with ffmpeg: a tone, plus `anullsrc` padding sized from the text length.
  - It uploads them and completes the part.
  - Lets the whole server side and frontend be built and tested with no GPU and no Castwright.

## Phase 4: metadata and cover

- **Cover** (`services/audiobook_cover.py`, Pillow), built from the source cover:
  - a 1400×1400 square (audiobook apps expect square art): the blurred, darkened cover fills the background, the portrait cover is centred on it, and a small "Audiobook" ribbon with a headphone glyph sits on top;
  - saved as `audio/cover.jpg` (~150 KB), plus a 600 px WebP for the site;
  - the `.m4b` gets a per-part variant with a "Part 3" badge, made at build time and never stored;
  - it's the image used everywhere: home cards, Media Session artwork, OG image, RSS.
- **`.m4b` build:** a new `Job` type `audiobook_m4b`, run by the crawler supervisor like `epub`, with the same `202` → poll → download flow as `prepare_source_epub`.
  1. ffmpeg concat of the part's chapter `.ogg` files with chapter markers from an ffmetadata file (chapter titles and offsets), `-movflags +faststart`, then one of:
     - `format=opus`: `-c copy`, which takes seconds;
     - `format=aac`: `-c:a aac -b:a 64k -ac 1`, ffmpeg's built-in encoder. It runs far faster than real time on one core, so a few minutes per part, once, then cached. The job runs at low CPU priority (`nice`) so the site isn't affected.
  2. mutagen MP4 tags:

| Tag | Value |
|---|---|
| `©nam` | `"<Title> — Part 3 (Ch. 51–75)"` |
| `©alb` | Title |
| `©ART`, `aART` | Authors |
| `©wrt` | Narrator credit: "Generated voices (LNCrawler)" |
| `©gen` | Audiobook |
| `©day` | Year |
| `desc`, `ldes` | Synopsis |
| `trkn` | (3, total) |
| `stik` | 2 (audiobook) |
| `©grp`, `©mvn`, `©mvi`, `shwm` | Series name and index, which Apple Books and most players group by |
| `covr` | Cover |
| `©too` | lncrawler |
| `----:com.apple.iTunes:LANGUAGE` | Language |

  3. The download name is `"<Title> - Part 03 (Ch. 51-75).m4b"`, sanitised, as `Content-Disposition`. Both formats get the same name.
- **Chapter `.ogg` files** carry their own tags from upload, so a file saved straight from the player is labelled too.
- **Retagging:** on a title or author change (signal on `Novel`/`NovelFromSource` save), queue a retag of the `.ogg` files and drop the `.m4b` cache.

## Phase 5: public API, feeds and SEO

- **`GET audiobooks/`** (API host, same style as `novels/`) lists published audiobooks.
  - Sort by `popular` (rank + plays), `new` (`first_published_at`), `updated` (`last_part_at`) or `longest`.
  - Filter by tag/genre (reuse the novel tag filters), with a search query.
  - Paginated. Each card has cover, title, authors, hours, parts, the language flag (top right of the cover) and the user's progress when logged in.
- **`GET audiobooks/<novel slug>/?lang=en`** returns the detail:
  - synopsis, credits;
  - the cast list (character → voice/engine, with narrator and main characters first), returned as `description` per entry too (null when absent), and `has_volumes`;
  - parts with their state and `.m4b` download state;
  - chapters with `audio_url`, `duration_s` and number/title;
  - the user's progress.
- **`GET audiobooks/<slug>/parts/<index>/download/?format=opus|aac`** returns `202` while building, then the file through nginx `X-Accel-Redirect` (internal `/_m4b/`; the cache folder is not reachable directly). Counts a download when the request starts the file.
  - Open to everyone, not throttled. An uncached AAC build costs CPU, so builds are cached and run as jobs.
- **`GET|PUT|POST audiobooks/<slug>/progress/`** reads and saves listening progress.
  - Throttled. POST is for `fetch(..., {keepalive: true})` on page hide, which can send the Token header (`sendBeacon` can't).
  - When a chapter is ≥ 90 % listened, it also moves `ReadingHistory.last_read_chapter` forward (never back), so "continue reading" follows listening.
- **`POST audiobooks/<slug>/play/`** records one play per chapter per visitor (user or IP) per 12 h, plus listened seconds, feeding `AudiobookDailyStat`. nginx serves the audio, so Django can't count plays otherwise.
- **`novels/home/`** gets the `featured` audiobook, the top 12 audiobooks and the user's "continue listening" list.
- The chapter serializer gets `audio_url` and `audio_duration_s` when published.
- **Podcast RSS feed:** `GET audiobooks/<slug>/feed.xml` on the API host.
  - One feed per audiobook, one `<item>` per chapter with an `<enclosure>` pointing at the `.ogg`.
  - iTunes/Podcasting 2.0 tags: `itunes:image`, `itunes:author`, `itunes:order`, `podcast:person` for credits.
  - Users can subscribe in AntennaPod, Pocket Casts and similar apps, which keep their own progress and download in the background. Good promotion at almost no cost.
- **SEO** (`views/seo_views.py`, `views/sitemap.py`):
  - an `AudiobookSitemap` entry for `/audiobooks` and each audiobook page;
  - OG tags with the square cover and `og:audio` (part 1, chapter 1);
  - schema.org `Audiobook` JSON-LD (`name`, `author`, `readBy`, `duration`, `image`, `inLanguage`, `bookFormat`);
  - one line in `public/llms.txt`.

## Phase 6: frontend

All new strings go through the `i18n-locales` skill, in all 21 locales.

- **Global audio player** (`components/audio/`, mounted in the app layout so playback survives navigation):
  - **Mini bar** (bottom, above the footer on mobile): cover, title, chapter, play/pause, ±15 s / +30 s, progress.
  - **Full player** (expands into a bottom sheet on mobile):
    - chapter list with progress ticks;
    - speed 0.75–2.5× with pitch kept;
    - sleep timer: end of chapter, 15, 30 or 60 min;
    - "read this chapter" link to the reader.
  - **Behaviour:**
    - Media Session API (artwork, chapter title, next/previous chapter, seek);
    - the next chapter is preloaded 30 s before the end, then auto-advance;
    - keyboard shortcuts (space, ←/→, `[`/`]` for speed);
    - progress saved every 15 s, on pause, on chapter end and on `pagehide`;
    - anonymous progress stays in `localStorage` and moves to the account on login.
- **Home page** (`components/home/HomePage.tsx`):
  - an **Audiobooks** section near the top, after the intro: the `featured` audiobook as a wide card with a "Listen now" button, then a horizontal row of square covers with hours, the language flag and a play button that starts straight in the mini player;
  - a **Continue listening** row for logged-in users;
  - a one-time intro banner announcing audiobooks (dismissible, reusing `introBanner.ts` styling), linking to `/audiobooks`;
  - matching placeholders in `HomeSkeleton.tsx`.
- **`/audiobooks` page:** grid of square covers with sort, tag filters and search. The header links to the RSS help.
- **Audiobook page** `/novels/:novelSlug/:sourceSlug/audiobook`:
  - cover (language flag top right), title and authors, total hours, credits;
  - "Listen" / "Resume chapter 57 at 12:40";
  - the characters (name and description, narrator first), only when a description exists;
  - parts with a **Download .m4b** split button (with a "Preparing…" state), chapter range, size, duration (estimated until the part exists) and the engine that narrated it:
    - "Opus (.m4b)" (smaller, the default) plus "AAC (.m4b)" (Apple Books, older players), each with its size;
    - the AAC option is preselected on iOS/macOS Safari.
  - the chapter list with play buttons and progress;
  - a "Subscribe in a podcast app" button (copy the RSS link, plus `antennapod://` and `pktc://` deep links);
  - "coming next: part 5 is queued".
- **Novel page (`SourceDetail.tsx`):** an audiobook banner linking to the audiobook page, and a headphone badge in the chapter list and on novel cards everywhere.
- **Reader:**
  - a "Narrated" mode in `TtsSettings.tsx`, shown when the chapter has `audio_url`; it plays through the global player, so listening continues if the user leaves the reader;
  - client TTS stays the fallback;
  - no text highlighting in v1.
- **Library and history:**
  - "New audio" badge on bookmarked novels with a new part since the last visit;
  - listening shows up in `/history` with a headphone icon.
- **Navigation:** an "Audiobooks" entry in `Header.tsx`.
- **Polish checklist:**
  - skeletons for every new view, empty states ("No audiobooks yet");
  - an error state when a file fails to load (falls back to client TTS in the reader);
  - mobile layouts at 360 px;
  - dark/light themes;
  - focus and ARIA labels on player controls, `prefers-reduced-motion`.

## Phase 7: tests

In `lncrawler_api/tests/`, on `MergeTestCase`:

- **`test_audiobook_enqueue.py`:**
  - ranking order, exclusions, caps, the disk budget;
  - part cutting by words: whole chapters only, a single over-long chapter becomes its own part, ranges stay frozen after chapters are added, the completed-novel tail rule;
- **Word counts:** counting from HTML, lazy fill when cutting, reset on a real chapter change.
- **`test_audiobook_worker_api.py`:**
  - auth (anonymous, user, worker), claim order and affinity, concurrent claims (`TransactionTestCase`);
  - heartbeat `409`;
  - upload: hash mismatch; format rejections (stereo, MP3, bitrate over 40 kbps, too short), with fixtures made by ffmpeg; idempotent re-upload;
  - `complete` with a missing chapter, cast merge, QA gate, engine recorded, regenerated-part swap, `ping`;
- **`test_audiobook_scheduler.py`:** enqueue passes and budgets, lease reaper, staleness, moved sources, LRU cache pruning.
- **`test_audiobook_media.py`:**
  - `.m4b` job output in both formats: `ffprobe` shows the codec (opus / aac) and the chapters, mutagen shows the tags and cover;
  - DMCA books still download and play (only the listings hide them);
  - `.ogg` tags after upload;
  - square cover size;
  - retag on title change.
- **`test_audiobook_public_api.py`:**
  - unpublished audiobooks are hidden; list sorting and filters;
  - progress PUT/beacon and the sync to `ReadingHistory` (forward only);
  - play counting deduplicated per session;
  - RSS validity;
  - sitemap entries and JSON-LD.
- **Frontend:** type check, lint and i18n check. Manual pass with the fake worker's data in the browser on mobile and desktop widths.

## Order

1. **Phase 1, then Phase 3 with `audiobook_fake_worker`.** From here the server side works end to end with no GPU. The worker agent can start on the real worker against the contract at the same point.
2. **Phases 2 and 4.**
3. **Phases 5 and 6.** The frontend can start once Phase 5's API shapes are fixed, using fake-worker data.
4. **Phase 7** throughout, then full verification.
5. **Rollout:**
   1. Deploy with `AUDIOBOOK_ENABLED=false`.
   2. Connect the real worker with a small `AUDIOBOOK_QUEUE_WORDS`, unpublished.
   3. Listen in the admin for a week.
   4. Publish, turn on the home section and the banner.
   5. Raise `AUDIOBOOK_QUEUE_WORDS` to what the worker actually produces per night.

## Decisions taken

1. AAC download alongside Opus: yes. It's the same `.m4b` job with a different codec flag.
2. Downloads are open to everyone, not throttled.
3. Parts are cut by word count (75,000 words by default), whole chapters only.
4. The engine is stored per part and per character, as the worker reports it.
5. Languages a worker takes are announced with its ping (`languages`, default English), and a language counts for 7 days after its last announcement. Several workers: the union of their languages.
6. A pin on an audiobook is released after 7 days without contact from its worker.
7. Popularity of a new book is per novel and language: the total views of its sources in that language.
8. Adult: guests and viewers who allow adult content (`show_r18` yes or blur) see adult audiobooks, flagged `is_adult`. Only logged-in viewers who chose no do not. SEO pages and the sitemap never list them; the per-book feed allows them.
9. Catalog feed `audiobooks/feed.xml?adult=exclude|include|only` (default exclude): plain RSS 2.0, one item per listenable part, newest first, 50 items. Its URL is `catalog_feed_url` in the list response.
10. Reading and listening history are one list (`?kind=all|read|listen`), newest first, 20 per page. A listening entry can be deleted by its owner.
11. Narrator credit is "Generated voices (LNCrawler)" everywhere; downloads carry a " [generated]" suffix.
12. The language is shown as a flag everywhere a book is: card and home cover (top right), the audiobook page cover, and "Also available in" links to the other languages of the novel (clickable flags, no chips). The list has a language filter, shown when more than one language is visible. Language names come from `languageCodeToName`, flags from `languageFlagUrl`, as in the novel cards.
13. No 30 s sample: the preview button, its player mode and the notice are removed.
14. The cast section is titled "Characters" and is shown only when at least one character has a description (from the worker's optional `description`, see the contract). Each entry is the character name (bold) with its description. No caption.
15. The audiobooks block sits on the home page right after "Best of all time". The intro banner is removed, and so is the "Novels you added" section.
16. Source pages: the audiobook banner sits below the source's action rows, with a top margin.
17. The "Disclaimer" paragraphs of wuxiaworld.site synopses are dropped by the crawler, and a data migration strips them from the synopses already stored.
18. No pills: no "New part" badge and no "Generated" chip on cards or on the page. The generated disclaimer stays as a line on the page.
19. Formats are shown by codec, both are `.m4b`: "Opus (.m4b)" and "AAC (.m4b)", with the size and a short use note. The download button names the selected one. Apple Podcasts does not play Opus files, so its help points to the AAC download.
20. Volumes: when a source's chapters span more than one volume, each part lists its volumes in its meta line ("Volume 2: Title", "Volumes 2–3") and the expanded chapter list has a sub-heading at each volume change. Novels without volumes see no change.
21. No engine profiles: the worker decides the engines; prod only records what each part and character was made with.
