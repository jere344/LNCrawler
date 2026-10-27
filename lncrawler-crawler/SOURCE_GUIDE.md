# Adding a source — fast path

Goal: one pass per source, no re-discovery. §7 is for the coordinator; agents can skip it.

## 0. Decide first

- **No MTL** (machine-translated, Vietnamese "convert"/"cv", AI/LLM-polished). Stub: `is_disabled = True`, `has_mtl = True`, `disable_reason = "Machine-translated (MTL) content — extremely low quality, intentionally excluded"`. Tells: "MTL"/"convert"/"AI translated" in footer or synopsis, no translator credits, every chapter bulk-imported. Mixed catalog with a per-novel MTL flag → implement, filter MTL novels out of search/browse, set `has_mtl` on read (readnovel_eu, truyenyy).
- **Mirror aggregator** (catalog copied from other sites: per-novel `domain`/`source` field, identical text): if the mirrored hosts exist in `sources/` → stub "mirror of X (already covered by x.py)". No such field: look for the mirrored site's markers in chapter bodies (footer, "© X", heading artifacts). LLM-rewritten synopses alone ≠ MTL.
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
- Covers: `data-src` / `data-original` / `_src` before `src`.
- Scope chapter-list selectors to the main container (sidebars reuse them). Chapter bodies may sit between nav markers (piaotia: `div.toplink`…`div.bottomlink`). API `link` may point to an announcement page.
- `absolute_url()` drops a trailing `/`; re-add before `urljoin` with relative pager links (kanunu8).
- Pagination: `?page=N`, `/trang-N/`, `page~N`; endpoints that repeat the last page → stop when a page adds no new URLs.
- GBK/Big5: `encoding="gbk"` on `get_soup`; GBK forms: `post_soup(url, data="k=" + quote(q.encode("gbk")), headers={"Content-Type": "application/x-www-form-urlencoded"})`. DEDE/jieqi search allows ~1 query/60 s, else a "信息提示" page → return `[]`, no retry loop. curl error 16 on HTTP/2 → `http_version='v1'`.
- `get_json` sites often need `Referer` / `Origin` / `X-Requested-With`.

## 4. Metadata checklist

Novel: `novel_title`, `novel_author` (join multiple), `novel_cover` (absolute, not a placeholder), `novel_synopsis` (no site boilerplate), `novel_tags` (genres + tags), `alternative_titles`, `self.status = NovelStatus.ongoing|completed|hiatus|unknown` (`from lncrawl.models import NovelStatus`; not on the base class, read via getattr — parse it, don't hard-code), `language`, `is_rtl` for ar/fa/he/ur, `has_mtl` / `is_adult` / `login_required` when true, translators via `self.translators`. Volumes: every `chapter.volume` exists, no empty volumes; single-chapter story = one Volume + one Chapter at `novel_url`.

Chapters: ids sequential from 1 in reading order (reverse newest-first lists); dedupe URLs; skip VIP/locked (lock icon or a class like 17k `span.ellipsis.vip`) and log the count. Body: no ads, scripts, nav, watermarks (Royal Road hides anti-piracy lines with classes from a `<style>` block).

Listings:
- `search_novel(query)` → `SearchResult(title, url, info)` as the site's search returns them, without filtering on query terms (alternative titles would be lost; multi-source ranking sorts them). At most `MAX_RESULTS_PER_SOURCE` (50, `lncrawl/core/search.py`) are kept, so fetch only the first page(s). Status/chapters/latest in `info`. No search at all → `[]` + docstring.
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

## 7. Coordinator notes

- Triage agents give one line per candidate (engine, data route, blocked via scraper?, MTL?, catalog size, verdict); then one agent per accepted source probes and implements in one context.
- Give each agent the brief (venv, hosts list, scratch-file prefix, no-MTL and politeness rules) up front; mid-run policy changes cost a round trip each.
- End with one reviewer over the whole diff, then one fix pass.
