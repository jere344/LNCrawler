# Adding a source — fast path

Goal: one pass per source, no re-discovery. §6b is the quality-control pass for new and existing sources. §7 is for the coordinator; agents can skip it.

## 0. Decide first

- **No MTL** (machine-translated, Vietnamese "convert"/"cv", AI/LLM-polished). Stub: `is_disabled = True`, `has_mtl = True`, `disable_reason = "Machine-translated (MTL) content — extremely low quality, intentionally excluded"`. Tells: "MTL"/"convert"/"AI translated" in footer or synopsis, no translator credits, every chapter bulk-imported. Mixed catalog with a per-novel MTL flag → implement, filter MTL novels out of search/browse, set `has_mtl` on read (readnovel_eu, truyenyy).
- **Mirror aggregator** (catalog copied from other sites: per-novel `domain`/`source` field, identical text): if the mirrored hosts exist in `sources/` → stub "mirror of X (already covered by x.py)". No such field: look for the mirrored site's markers in chapter bodies (footer, "© X", heading artifacts). LLM-rewritten synopses alone ≠ MTL.
- **Mostly paywalled**: more than half of the chapters locked (VIP, coins, membership, free preview window) → disabled stub with the locked share in `disable_reason`. Mixed sites with a free section: offer only that section (naver_novel serves Challenge League, refuses Webnovel).
- **Live but unworkable** (hard bot wall, paywall, encryption) → disabled stub; `disable_reason` says what blocks it and how it was tested (curl_cffi / browser).
- **Dead / parked / spam / not a novel site** → no file, one report line `domain | none | skipped | reason`.
- Prefer original / raw / human-translated content. Don't commit; don't touch unrelated files.

## 1. Environment and layout

- A venv with the deps is given in your brief; run `python -I` with `sys.path` set to `lncrawler-crawler/`. (Creating one: `pip install curl_cffi==0.16.3 beautifulsoup4==4.15.0 lxml==6.1.3 lxml_html_clean==0.4.5 requests==2.34.2 tenacity==9.1.4 python-slugify==9.1.2 pillow==12.3.0 text-unidecode==1.3`.)
- Path: `sources/<lang>/<first-letter>/<stem>.py`. Digit-leading names live flat (`zh/23qb.py`); some langs are flat (check `ls sources/<lang>`); Japanese → `ja/`. Stem must be importable: `-`/`.` → `_` (`berrys_cafe.py`). Create the letter folder if missing.
- `base_url` must be a literal str or list of literals (AST-indexed). Include aliases/redirect hosts.
- Before writing, `grep -rn "<domain>" sources/` (the host may hide under another name); improve the existing file instead of adding one — the loader keeps the last class per host.

## 2. Triage (before any code)

`getent hosts site` first: failure or `::1`/`127.0.0.1`/`0.0.0.0` = dead. Then probe **through the crawler's scraper** — it already impersonates Chrome (curl_cffi), so plain-curl 403s are often false bot walls (Royal Road, mvlempyr, uukanshu pass this way):

```python
import sys; sys.path.insert(0, "<lncrawler-crawler dir>")
from lncrawl.core.crawler import Crawler
class P(Crawler):
    base_url = "https://site/"
    def read_novel_info(self): ...
    def download_chapter_body(self, c): ...
p = P(); p.initialize()   # __init__ doesn't call initialize(); needed in every smoke test
r = p.scraper.get("https://site/", timeout=20)   # raw: get_response() raises on 4xx and hides the body
print(r.status_code, r.text[:300])
```

Check page text and final URL, not just status: shutdown banners, for-sale and spam pages return 200.

| Signal (via scraper) | Action |
| --- | --- |
| `__NEXT_DATA__` / `_next/data`, `/api/`, `wp-json`, RSS, Blogger feeds, MediaWiki API | use the JSON, don't scrape HTML |
| Madara / NovelFull / MangaStream / NovelMTL look | `python -I tools/match_template.py <home> <novel> <chapter>`; `use <Template>` → subclass it. "partial match" is often a false positive (one selector hit) |
| Static HTML | `Crawler` + bs4 |
| 403 / "Just a moment" / turnstile / Anubis | check in a real browser (built-in pane). Data via XHR → call that API (often unwalled). Still stuck → stub "also blocked in a real browser". Never solve interactive challenges |
| Login / coins / VIP for bodies; free preview window (first N chapters only: tadu, faloo, 17k) | stub — partial novels are worse than none |
| Body encrypted, signed API + protobuf (neopage), chapter URL built by obfuscated per-page JS (8book), font glyph remapping (kawebook), server-side truncation (bilinovel "內容加載失敗") | stub, don't keep probing |
| Custom captcha form (e.g. `vb_challenge`), not Turnstile/Anubis | stub "custom captcha gate"; never solve |
| Click-through interstitial before the site (wuxia.blog) | stub if the gate is a JS button with no plain-GET target; otherwise follow the link |
| JS "Redirecting..." page posting to a third-party router or parking host (boxnovel) | parked → no file, one report line |
| Host resolves but connections time out | dead unless another route answers |
| Local TLS failure (curl error 60, CA gap) | probe with `p.scraper.get(url, verify=False)`; the shipped file keeps default TLS |
| Page-embedded API token that returns 401 without it | don't reuse it in the source; if that is the only way in, stub and say so in `disable_reason` |
| Free preview then paywall (lorenovels, ~ch. 65) | binary-search the chapter number, one body request per probe, to find the boundary; stub |

Routes that kept paying off:
- WordPress REST: categories = novels, posts = chapters. The API can live on another domain (mvlempyr → chap.heliosarchive.online): check the front-end JS.
- Blogger: `/feeds/posts/default/-/<label>?alt=json`; if feeds are disabled, HTML label pages `/search/label/<x>` (xbookcn).
- Novel page shows ~30 chapters / "load more": the full list is an `/ajax/...` endpoint named in inline JS (`grep -oE '[A-Za-z]+Url\s*=\s*"[^"]+"'`; NovelPing `/ajax/chapter-archive?novelId=`).
- Next.js/RSC chapter lists behind `onClick`: grep JS chunks for fetch URLs. POST-only API (405 on GET): field names are in the JS bundle.
- Always count chapters from the list/API, not the novel page.

## 3. Known traps

- Search param / listing URL from specs are often wrong (`tukhoa` → `search`; `/top/` → `/topfull/allvisit/N.html`). Site search may post to a third-party host or Google CSE → no usable search (§4b).
- Covers: `data-src` / `data-original` / `_src` before `src`; `self.image_url(img)` handles these.
- Scope chapter-list selectors to the main container (sidebars reuse them). Chapter bodies may sit between nav markers (piaotia: `div.toplink`…`div.bottomlink`). API `link` may point to an announcement page.
- `absolute_url()` drops a trailing `/`; re-add before `urljoin` with relative pager links (kanunu8).
- Pagination: `?page=N`, `/trang-N/`, `page~N`; endpoints that repeat the last page → stop when a page adds no new URLs.
- GBK/Big5: `encoding="gbk"` on `get_soup`; GBK forms: `post_soup(url, data="k=" + quote(q.encode("gbk")), headers={"Content-Type": "application/x-www-form-urlencoded"})`. DEDE/jieqi search allows ~1 query/60 s, else a "信息提示" page → return `[]`, no retry loop. curl error 16 on HTTP/2 → `http_version='v1'`.
- `get_json` sites often need `Referer` / `Origin` / `X-Requested-With`.

## 4. Metadata checklist

Novel: `novel_title`, `novel_author` (join multiple), `novel_cover` (absolute, not a placeholder), `novel_synopsis` (no site boilerplate), `novel_tags` (genres + tags), `alternative_titles`, `self.status = NovelStatus.ongoing|completed|hiatus|unknown` (`from lncrawl.models import NovelStatus`; not on the base class, read via getattr — parse it, don't hard-code), `language`, `is_rtl` for ar/fa/he/ur, `has_mtl` / `is_adult` / `login_required` when true, translators via `self.translators`. Volumes: every `chapter.volume` exists, no empty volumes; single-chapter story = one Volume + one Chapter at `novel_url`.

Volume covers: when the site shows one image per volume, set `Volume(id=..., title=..., cover_url=...)` (absolute URL, from a page or API response `read_novel_info` already fetches; `self.image_url(img)` for HTML). The downloader inserts it right after the title of the volume's first chapter, on novels with at least two volumes. Leave it out when the site has none: never reuse `novel_cover` or a placeholder, and no extra request per volume unless the volume has its own page already being fetched. EPUB templates: `self.book_cover_url(book)`.

Chapters: ids sequential from 1 in reading order (reverse newest-first lists); dedupe URLs; skip VIP/locked (lock icon or a class like 17k `span.ellipsis.vip`) and log the count. Body: no ads, scripts, nav, watermarks (Royal Road hides anti-piracy lines with classes from a `<style>` block).

Version: bump `version` (class attribute, default 1, so `version = 2`, then 3, ...) only when a fix changes the chapter bodies already downloaded, e.g. truncated text or ads left in the body. Use it sparingly: the next update of every novel on the source refetches all its chapters, which is slow and hits the site hard. Metadata is refreshed on every update, and new chapters and changed chapter URLs are picked up without a bump, so don't bump for fixes to novel metadata, titles, volumes, the table of contents, search or browse. Leave it out of new sources.

Make the bump non-breaking when the stored bodies can be fixed without the site (§6c): then nothing is refetched.

Listings:
- `search_novel(query)` → `SearchResult(title, url, info, cover)` as the site's search returns them, without filtering on query terms (alternative titles would be lost; multi-source ranking sorts them). At most `MAX_RESULTS_PER_SOURCE` (50, `lncrawl/core/search.py`) are kept, so fetch only the first page(s). Status/chapters/latest in `info`. `cover` comes only from what the search response already contains (`self.image_url(img)` for HTML, `self.absolute_url(...)` for JSON), never an extra request per result; omit it rather than returning a site placeholder. No search at all → `[]` + docstring.
- `browse_novels(offset, limit)` → popular/ranking; returns ≤ `limit`; fetch only the pages needed. Genre listings have no hook: iterate them inside `browse_novels` (naver_novel).

## 4b. Politeness (don't get flagged on first indexing)

Harvest walks `browse_novels` on every new source and many jobs hit one host; a ban loses the source for every user.

- `self.init_executor(ratelimit=1)` in `initialize()` for any sizeable site (wraps every HTTP call). 429 + `Retry-After` is already handled; never retry-loop on 403/challenge — fail fast.
- Every loop has a page cap and stops when a page adds nothing new. Prefer max `per_page`.
- **No usable site search but an enumerable catalog** → `lncrawl/core/catalog_cache.py` `cached_catalog(key, builder, ttl=timedelta(days=7), build=...)` (example: `sources/en/m/mvlempyr.py`):
  - Shared on disk (`LNCRAWL_CACHE_DIR`), one build at a time (flock).
  - **Only `warm_catalog(self) -> int` builds** (`build=True`); the `warm_catalogs` scheduler task calls it every 12 h. `search_novel`/`browse_novels` read only and raise `LNException` at once if the catalog is missing — multi-source search has a 40 s budget (`lncrawl/core/search.py`) and drops a raising source.
  - Builder: sequential, `time.sleep(random.uniform(1.0, 2.5))` between pages, raise on 403/challenge, raise if page 1 (or a genre's page 1) is empty or the total is implausibly small — never return a partial catalog. Store small JSON records (title, url, author, status).
- Live tests: a few pages only (monkeypatch the page cap); never build a full catalog during development.

## 5. Skeleton

```python
# -*- coding: utf-8 -*-
"""Site — what it hosts, language, route used (API/HTML), quirks."""
import logging
from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)


class XCrawler(Crawler):
    base_url = ["https://example.com/"]
    language = "xx"

    def initialize(self):
        self.init_executor(ratelimit=1)

    def search_novel(self, query): ...
    def browse_novels(self, offset=0, limit=50): ...
    def read_novel_info(self): ...
    def download_chapter_body(self, chapter) -> str: ...


class YCrawler(Crawler):  # disabled stub; no parentheses inside the reason string
    base_url = ["https://example.org/"]
    language = "xx"
    is_disabled = True
    disable_reason = "Cloudflare challenge also in a real browser; no public API"
```

Helpers: `get_soup(url, headers=, encoding=)`, `get_json`, `post_soup`, `absolute_url`, `resolve_bounded([(fn, *args), ...])` (ordered parallel fetches), `self.cleaner.extract_contents(tag)` (for an API HTML fragment use `self.make_soup(html).body`).

## 6. Verification

1. `ast.parse`; duplicate-host scan over `sources/**/*.py` (normalise `www.` and trailing `/`).
2. Real class, **fresh instance per novel** (chapters accumulate otherwise), `initialize()` first: `search_novel`, `browse_novels(0, 20)` and `(20, 10)`, `read_novel_info` on a completed and an ongoing novel, `download_chapter_body` on first and last chapter (print counts + first 150 chars).
3. Report what was verified live vs only parsed.

## 6b. Quality control

Run on every new source and when re-auditing existing ones. The dump does the fetching; you judge it against the live page.

```bash
python -I tools/qc_source.py sources/<lang>/<x>/<stem>.py --out <scratch>/qc [--novel URL --novel URL]
```

Without `--novel` it takes two novels from `browse_novels`; pass them yourself when browse is missing, and make sure one of them has volumes when the site has volumes. It writes `<out>/<Class>/report.md` (metadata, chapter list, volumes, 5 random chapters of novel 0 and 2 of novel 1, automatic flags), `data.json` and `cover_<n>.jpg`. Flags are leads, not verdicts, and a clean report proves nothing about fields the source never extracts: always open the novel page next to the report.

Metadata (novel page next to the report):
- **Cover**: open `cover_<n>.jpg`. It is the book's cover, not a site logo, "no image" picture, default avatar or 1×1 pixel. No cover beats a placeholder: return `None` when the site serves its default image (match its file name). Same image for both novels = placeholder.
- **Title**: no site suffix ("– Read Online"), no status or chapter count.
- **Authors**: people only. Not a date, word/chapter count, status, translator, "Unknown"/"N/A", or the label itself ("Author:"). Several authors joined with `, `; original-script name alongside the romanized one is fine.
- **Tags/genres**: genres and tags only. Not the status, a date, word/view/chapter counts, the author, the language, rating, "Novel"/"Web Novel" type labels, or the site's whole genre menu (same list on both novels = sidebar scraped).
- **Other fields shown on the page are extracted, each into its own attribute**: `status` (parsed, not hard-coded), `alternative_titles`, `novel_edition` (Web Novel / Light Novel / Raw / Official translation), `translators`, `editors`, `original_publisher`, `english_publisher`, `is_adult` for an R18 catalog. A value pasted into the synopsis or tags instead is a bug.
- **Synopsis**: the blurb only. No "Read more/Show less", labels and values of other fields (Author:, Genre:, Status:, Alternative names:), chapter links, site boilerplate shared by every novel (same prefix/suffix on both novels), ratings, or the whole page text. Paragraph breaks kept. Empty is acceptable only when the site has none.

Chapter list:
- Count matches the site, ids 1..N in reading order (not newest first), no duplicate URLs, locked/VIP chapters skipped.
- **Titles**: the chapter's title only. No appended date, "x days ago", view/word count, "NEW"/"HOT"/lock badges, novel name prefix, or whitespace runs. Empty title → leave it empty (the pipeline writes `#<id>`), don't invent one.
- **Volumes**, when the site groups chapters (headings, tabs, "Volume N" sections, separate volume pages):
  - extracted as `Volume`s, not flattened into one list; a flat list whose titles say "Vol. 3 Chapter 2" while the site has volume headings is a bug;
  - titles are the site's volume names, not "Volume 1" when the site has a real one, and without chapter counts or dates;
  - boundaries: the first and last chapter of each volume in the report match the site, no chapter in two volumes, no empty volume, volumes in reading order;
  - covers: the volume's own image when the site shows one per volume; never the novel cover or a placeholder repeated on every volume (§4).

Chapter bodies (the 5 + 2 random samples):
- Paragraphs are `<p>` blocks (or kept `<br>` breaks), not one merged wall of text, not one `<p>` per sentence fragment broken mid-line, no runs of empty `<p>`.
- None of: scripts, styles, iframes, forms, ad slots, share/vote buttons, nav ("Previous/Next chapter", "Table of contents", 上一章/下一章), comment sections, author-note widgets.
- **No watermarks**: "read at/on <site>", site name or URL lines, "find the original at", "if you are reading this on another site", 本章未完/请记住/最新章节, Patreon/Ko-fi/Discord begging blocks added by the aggregator (a translator's own short note at the end is content), anti-piracy lines hidden with CSS classes or `display:none` (Royal Road). Lines repeated across chapters of different novels (cross-novel flag) are almost always a watermark.
- Text decodes cleanly (no mojibake, no `�`), no obfuscation substitutions (glyphs swapped for placeholders like `N` or private-use characters), images have absolute URLs, the chapter is complete (compare the last line with the site; "loading"/"continue reading" endings mean pagination or an AJAX part is missed).

Fix in the source file, rerun the dump, and bump `version` only when the body fix changes chapters already downloaded (§4).

## 6c. Non-breaking versions (body migrations)

A bump refetches every stored chapter of the source. When the new body only drops or rewrites content that the stored body still contains, fix the stored chapters instead:

```python
from lncrawl.core import body_migrations

    version = 2
    body_migrations = {2: "_migrate_v2"}

    def _migrate_v2(self, body, chapter):
        return body_migrations.drop_matching(body, _WATERMARK_RE)
```

- On update, a chapter stored at version `v` goes through every step from `v + 1` to `version`. If each step has a method, the body is fixed on disk and not refetched. A version missing from `body_migrations` is breaking: its chapters are refetched. A method returns `None` to refetch one chapter (a marker it needs is missing).
- The method gets the body as the old `download_chapter_body` returned it (the downloader keeps the `<h1>` and volume cover aside, and drops a repeated title line afterwards) and the stored chapter dict. The cleaner has already stripped classes and most attributes: match text and tag names, never CSS classes. Helpers in `lncrawl/core/body_migrations.py`: `drop_matching`, `drop_blocks`, `sub_text`. Reuse the regexes the download path uses.
- **Non-breaking**: watermark or nav lines, begging blocks, site credits, stray characters, a leading title line, unwrapping a wrapper. **Breaking**: a new container or selector, missing or truncated text (pagination, second request), lost line breaks, removals that can only be found by class or hidden style, decoding fixes.
- Verify on live chapters: `python -I tools/check_migration.py <source.py> [--novel URL] [--chapters 6] [--old-ref HEAD]`. It downloads the same chapters with the old code (the source and core at `--old-ref`) and the current code, migrates the old body and compares. Every chapter must be `same` or `refetch`; "(old body already identical)" means the sample didn't hit the removed content, so try another `--seed` or novel.

## 7. Coordinator notes

- Triage agents give one line per candidate (engine, data route, blocked via scraper?, MTL?, catalog size, verdict); then one agent per accepted source probes and implements in one context.
- Give each agent the brief (venv, hosts list, scratch-file prefix, no-MTL and politeness rules) up front; mid-run policy changes cost a round trip each.
- End with one reviewer over the whole diff, then one fix pass.
- Keep each Haiku agent under 100k tokens of context (above that it costs ~5×): at most 2–3 sources per QC or implementation agent, ~6 files per reviewer working from the diff only. A QC pass over 8 sources per agent ran at 200–350k.
