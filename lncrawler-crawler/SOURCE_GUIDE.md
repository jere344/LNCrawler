# Adding a source — fast path

Written from the first big batch (~97 files, 14 functional sources). Goal: get a source done in one pass, no re-discovery.

## 0. Rules that decide before you start

- **No MTL.** Machine-translated / auto-"convert" / LLM-polished sites are not implemented. Create a stub: `is_disabled = True`, `has_mtl = True`, `disable_reason = "(Machine-translated (MTL) content — extremely low quality, intentionally excluded)"`. Quick tells: "convert", "MTL", "AI translated" in footer/synopsis, leftover prompts in synopses, no translator credits, bulk-imported novels with translator null and every chapter TRANSLATED (exclude).
- **Prefer original / raw / human-curated** content, and languages with few sources.
- **Live but not workable** (bot wall, paywall, client-side encryption, unscrapable) → disabled stub with an explanation.
- **Dead / parked / non-resolving domains are skipped with no stub** (tests in §2) and reported as one line: `domain | none | skipped | reason`.
- Don't commit. Don't touch unrelated uncommitted files.

## 1. Environment (do once, 2 min — everyone lost time here)

- `lncrawl` can't be imported without deps (`curl_cffi`, etc.). The crawler has no requirements file of its own; the subset it needs is pinned in `lncrawler-api/requirements.txt`. Create one **once per session** in the scratchpad and reuse it:
  ```bash
  python3 -m venv "$SCRATCHPAD/venv" && "$SCRATCHPAD/venv/bin/pip" install -q curl_cffi==0.16.3 beautifulsoup4==4.15.0 lxml==6.1.3 lxml_html_clean==0.4.5 requests==2.34.2 tenacity==9.1.4 python-slugify==9.1.2 pillow==12.3.0 python-box==7.4.1 text-unidecode==1.3
  ```
  Then smoke-test with the real class: `"$SCRATCHPAD/venv/bin/python" -I` with `sys.path` set explicitly to the `lncrawler-crawler/` directory (do not run from inside a downloaded/scratch dir).
- `sources/` is a sibling of `lncrawl/`, not inside it.
- Layout: `sources/<lang>/<first-letter>/<stem>.py`. **Exceptions:** names starting with a digit live flat in the language folder (`zh/23qb.py`, `en/9kafe.py`); some langs are flat (`es/skynovels.py`, `vi/truyencv.py`). Japanese: both `ja/` and `jp/` exist; use `ja/` for new ones. Check `ls sources/<lang>` first.
- `base_url` **must be a literal str or list of literals** (the lazy index is an AST scan).
- Before writing, `grep -rn "<domain>" sources/` and grep `base_url` / `search_url` in sibling files for aliases — the domain may already exist under another name (NovelBuddy was hidden in `novelfullme.py`). Improve the existing file instead of creating a second one; the loader keeps only the last class per host.
- Duplicate scan after writing: AST over `sources/**/*.py`, normalise trailing `/` and `www.`.

## 2. Triage in 3 curl calls (before any code)

```bash
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'
getent hosts site                           # DNS first; failure = dead
curl -sIL -A "$UA" https://site/            # status, final URL, server: cloudflare?
curl -sL  -A "$UA" https://site/ | head -c 3000   # "Just a moment", __NEXT_DATA__, wp-json, SPA shell?
curl -sL  -A "$UA" "https://site/wp-json/wp/v2/posts?per_page=1" | head -c 300
```

Decision table:

| Signal                                                                                                | Meaning        | Action                                              |
| ----------------------------------------------------------------------------------------------------- | -------------- | --------------------------------------------------- |
| 403 / "Just a moment" / `cf-mitigated` / Anubis / turnstile **in curl**                               | bot wall?      | **not final** — retest in a real browser (below)    |
| DNS fail, curl 000 on apex+www, 404 root, JS redirect to /lander or for-sale page, tiny/unrelated 200  | dead           | skip, no stub; one-line report (§0)                 |
| Login / coin / paywall for bodies (ebook stores: readmoo, bookwalker → test in browser first)          | paid           | disabled stub (or free chapters only if truly free) |
| Body AES/devalue-encrypted client side                                                                | too complex    | disabled stub                                       |
| `__NEXT_DATA__`, `/api/`, `wp-json`, RSS/Atom, Blogger `/feeds/posts/default?alt=json`, MediaWiki API | JSON available | **use it, don't scrape HTML**                       |
| Madara / NovelFull / MangaStream theme                                                                | known engine   | use the template in `lncrawl/templates/`            |
| Static HTML                                                                                           | scrape         | `Crawler` + bs4                                     |

Triage checks the homepage text and final URL, not only the status code: shutdown banners, spam and for-sale pages can return 200. Check home/genre APIs for shutdown banners too.

### Bot walls: curl failing is not a verdict

A 403 / challenge from curl only means curl was blocked. Many sites let a real browser through (JS challenge solved, TLS/HTTP2 fingerprint, cookies). First try curl_cffi with `impersonate="chrome"` (yomu.com.br went 403 → 200). Aliyun WAF (17k, qidian) is not beaten by impersonation → stub. Before writing a disabled stub for a bot wall:

1. Open the site's home page, a search page and a chapter page in a real browser (built-in browser pane / Chrome / headless Chromium via Playwright or Selenium) and see if content loads on its own (no interactive captcha).
2. If it loads, find out *what* made it pass, because that decides the implementation:
   - Pass only after the JS challenge resolves, cookie `cf_clearance` set → use the browser templates in `lncrawl/templates/browser/` (`BasicBrowserTemplate`, `SearchableBrowserTemplate`, `ChapterOnlyBrowserTemplate`, … via `core/browser.py`, `can_use_browser`), or the project's existing curl_cffi/impersonation path (check how `lncrawl/core/scraper.py` is set up and copy a source already doing this, e.g. the existing Cloudflare-fronted ones such as `novelfull`/`novelmtl` templates).
   - Pass with plain requests once the right headers/impersonation are used → stay on `Crawler` + `get_soup`; test curl with `--http2`, a full browser header set, or `curl_cffi` with `impersonate="chrome"` before reaching for a browser.
   - The page loads, but the data comes from an XHR/API call → watch the Network tab, call that API directly (often not behind the wall at all).
3. Only if the browser also hits an interactive captcha / turnstile / Anubis proof-of-work that never resolves headless → disabled stub, reason says *"also blocked in a real browser"*.
4. Passive Cloudflare JS challenge: use the browser template only if the challenge clears passively within ~10s in the real browser template; otherwise stub. Never solve interactive challenges or bypass CAPTCHAs. Record in the stub's `disable_reason` how it was tested (curl only / curl_cffi / browser) so it can be revisited.

Browser-based sources are slower and heavier; prefer a JSON/API route when one exists and use the browser for the challenge/cookie only if possible.

Free wins that kept coming up: WordPress REST categories = novels and posts = chapters; Next.js `pageProps`; RSS for chapter lists (Golden Novel); Blogger label feeds.

Before investing in a site:
- Check chapter counts via the chapter list / API / sitemap, not only the novel page.
- Next.js/RSC payloads may embed chapter bodies, or hide chapter lists behind `onClick` without `href`: grep JS chunks for fetch/API calls before giving up.
- POST-only JSON API returns 405 on GET: probe POST with a JSON body and find field names in the JS bundle.

## 3. Things that were wrong in specs (verify, don't trust)

- Search parameter names (`tukhoa` ignored, real one was `search`).
- Listing URL patterns (`/top/` 404, real one `/topfull/allvisit/N.html`).
- Cover attribute: `data-src` / `data-original` / `_src` before `src` (placeholders).
- Chapter body container (piaotia text was between `div.toplink` and `div.bottomlink`, not an ad marker). Sidebar links share chapter-list selectors: scope the chapter loop to the main container (e.g. `div.profile-main`).
- Traps: custom `@font-face` glyph remapping (e.g. cs_prajad fonts on kawebook) makes text unreadable → stub. Client-side obfuscated body decode (scrambled `$.get` URLs, `eval`'d char offsets) → stub with reason "chapter bodies decoded client-side by obfuscated JS".
- Chapter links from an API `link` may be an announcement page; check the real chapter URL (`/chapitre/<slug>/`).
- Pagination: `?page=N` vs `/trang-N/` vs `page~N`; some endpoints repeat the last page instead of 404 → break when a page adds no new URLs. Sites that ignore `?page=N` and repeat the same list need an offset>0 short-circuit returning `[]`.
- Encoding: GBK/Big5 sites need `encoding=` on `get_soup` and GBK-quoted query strings. curl error 16 under HTTP/2 → `http_version='v1'` plus a short retry.
- `get_json` sites often need `Referer` / `Origin` / `X-Requested-With`.

## 4. Metadata checklist — fetch everything the site exposes

Novel level (set on `self`):

- [ ] `novel_title`
- [ ] `novel_author` (join multiple; also artists/illustrators if listed)
- [ ] `novel_cover` (absolute URL, real image not placeholder)
- [ ] `novel_synopsis` (strip site boilerplate, emails, LLM leftovers)
- [ ] `novel_tags` (genres + tags + keywords + category + type/perspective/style; `genres` and `tags` are merged by `novel_info.__format_tags`)
- [ ] `alternative_titles`
- [ ] `status` (`NovelStatus` ongoing / completed / hiatus; don't hard-code "ongoing" if the site tells)
- [ ] `language` (class attr; folder-derived if empty), `is_rtl` for ar/fa/he/ur
- [ ] translator / publisher / original-language / year / rating / view counts if exposed (translators via `self.translators` is read with `getattr`)
- [ ] `has_mtl`, `is_adult`, `has_manga`, `login_required` where true
- [ ] `volumes` (`Volume`) and `chapter.volume` consistent; no empty volumes. Single-chapter stories = one-entry Volume + one Chapter whose url is `novel_url`.

Chapter level:

- [ ] `id` sequential from 1 in reading order (reverse newest-first lists), `title`, `url`, `volume`
- [ ] skip / mark locked, VIP, paid chapters (detect the lock icon; log count); dedupe duplicate URLs
- [ ] extra fields you need later on the Chapter (`api_id`, `title_id`) are fine

Listing level:

- [ ] `search_novel(query)` → `SearchResult(title, url, info)`; put status / chapters / latest in `info`. If the site has no search, return `[]` and say so in the docstring.
- [ ] `browse_novels(offset, limit)` → popular/ranking/latest; bounded pagination; returns ≤ `limit`.
- [ ] Genres / categories / authors / languages / status listings: the base `Crawler` has no hook for them, so iterate genre pages inside `browse_novels` (that is how naver_novel does it) and keep genre/tag per novel.
- [ ] Chapter body: stripped of ads, scripts, nav, share widgets, translator notes/watermarks; images only if they're content.

## 5. Skeleton

```python
# -*- coding: utf-8 -*-
"""Site name — what it hosts, language, features, quirks (encoding, API, limits)."""
import logging
from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult, Volume  # whatever you use

logger = logging.getLogger(__name__)


class XCrawler(Crawler):
    base_url = ["https://example.com/"]   # literals only, include aliases
    language = "xx"

    def search_novel(self, query): ...
    def browse_novels(self, offset, limit): ...
    def read_novel_info(self): ...
    def download_chapter_body(self, chapter) -> str: ...
```

Disabled stub:

```python
class XCrawler(Crawler):
    base_url = ["https://example.com/"]
    language = "xx"
    is_disabled = True
    disable_reason = "(Cloudflare managed challenge on every request; no public API)"
```

Useful helpers: `get_soup(url, headers=, encoding=)`, `get_json(url, headers=)`, `absolute_url(url, page_url)`, `resolve_bounded([(fn, *args), ...])` for ordered parallel page fetches, `self.cleaner.extract_contents(tag)`.

## 6. Verification (cheap, in this order)

1. `ast.parse` the file; duplicate-`base_url` scan.
2. With the shared venv, run the **real class**: `search_novel("a common word")`, `browse_novels(0, 20)` and `(20, 10)`, `read_novel_info()` on one result, `download_chapter_body()` on first and last chapter. Print counts and the first 200 chars of a body.
3. Force the API path to fail once if you wrote a fallback.
4. Check one completed novel with volumes and one ongoing novel with many chapters.
5. Record in the report: what was verified live vs only parsed.

## 7. How to split work between agents (what wasted tokens)

- The researcher → spec → implementer hand-off made the implementer **re-verify every selector** anyway. Better: a researcher only **triages** (3 curl calls above, one line per candidate: engine, API?, blocked?, languages, MTL?). Then **one agent per accepted source** probes and implements in the same context.
- Give every agent: this guide, the existing-source list for its language (`ls sources/<lang>`), the venv path, and the no-MTL rule up front — mid-run policy changes cost a round-trip per agent.
- Give agents the conclusion, not the search: "spec says X, but check Y" lists of known-wrong areas are in section 3.
- Don't ask for dead-domain lists beyond the one-line `domain | none | skipped | reason` entries from triage.
- Finish with one reviewer over the whole diff (imports, duplicate hosts, language/folder match, stubs have `disable_reason`, sequential chapter ids, bounded loops), then one implementer pass for fixes.
