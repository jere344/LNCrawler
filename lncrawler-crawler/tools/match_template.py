# -*- coding: utf-8 -*-
"""Check a site against the engine templates in lncrawl/templates/.

Usage:
    python -I tools/match_template.py <url> [<novel_url>] [<chapter_url>]
    python -I tools/match_template.py --existing

Live mode fetches the given pages with lncrawl's Scraper (curl_cffi, Chrome
impersonation) and checks each template's markers. Without a novel URL a
template can be reported as a partial match only. --existing scans
sources/**/*.py as text (no network) and lists hand-written sources that carry
a template's markers. See SOURCE_GUIDE.md section 2b.
"""
import argparse
import ast
import math
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Fingerprints. Each marker is (kind, value):
#   ("css", selector)  matched with soup.select_one() on the live page
#   ("text", string)   substring of the raw HTML
# Every value is a selector / URL pattern the template code relies on, so the
# fingerprint follows the template when the template changes.
TEMPLATES = [
    {
        "name": "Madara",
        "template": "lncrawl.templates.madara.MadaraTemplate",
        "home": [
            ("text", "wp-manga"),  # search uses post_type=wp-manga
            ("text", "admin-ajax.php"),  # chapter fallback endpoint
        ],
        "novel": [
            ("css", ".post-title h1"),
            ("css", ".summary_image"),
            ("css", ".author-content"),
            ("css", ".genres-content"),
            ("css", ".description-summary"),
            ("css", "#manga-chapters-holder"),
            ("css", ".wp-manga-chapter"),
        ],
        "chapter": [
            ("css", ".reading-content"),
        ],
    },
    {
        "name": "NovelFull",
        "template": "lncrawl.templates.novelfull.NovelFullTemplate",
        "home": [
            ("text", 'name="keyword"'),  # search?keyword=
        ],
        "novel": [
            ("css", "h3.title"),
            ("css", ".book img"),
            ("css", ".info"),
            ("css", ".desc-text"),
            ("css", "[data-novel-id]"),
        ],
        "chapter": [
            ("css", "#chr-content, #chapter-content"),
        ],
    },
    {
        "name": "MangaStream",
        "template": "lncrawl.templates.mangastream.MangaStreamTemplate",
        "home": [
            ("css", ".listupd > article"),
            ("text", 'name="s"'),  # search uses ?s=
        ],
        "novel": [
            ("css", "h1.entry-title"),
            ("css", ".thumbook"),
            ("css", ".spe"),
            ("css", ".bottom.tags"),
            ("css", ".entry-content"),
            ("css", ".eplister"),
        ],
        "chapter": [
            ("css", "#readernovel, #readerarea, .entry-content"),
        ],
    },
    {
        "name": "NovelMTL",
        "template": "lncrawl.templates.novelmtl.NovelMTLTemplate",
        "home": [
            ("text", "search.html"),
        ],
        "novel": [
            ("css", ".novel-info .novel-title"),
            ("css", "#novel figure.cover img"),
            ("css", ".novel-info .author"),
            ("css", ".categories"),
            ("css", ".summary .content"),
            ("css", "#chapters"),
        ],
        "chapter": [
            ("css", ".chapter-content"),
        ],
    },
]

PAGE_TYPES = ("home", "novel", "chapter")

# Concrete engine templates. A source already subclassing one is not a duplicate.
CONCRETE_CLASSES = {t["template"].rsplit(".", 1)[1] for t in TEMPLATES}

# Pages served by a bot wall even with HTTP 200.
BOT_WALL_RE = re.compile(
    r"Just a moment|cf-mitigated|cf_chl_|Attention Required", re.IGNORECASE
)

# Verdict threshold: share of markers matched over the scored pages.
USE_RATIO = 0.7


def class_name(tpl):
    return tpl["template"].rsplit(".", 1)[1]


def marker_label(marker):
    kind, value = marker
    return value if kind == "css" else f"text {value!r}"


def page_hits(markers, soup, html):
    hits, misses = [], []
    for kind, value in markers:
        if kind == "css":
            found = soup.select_one(value) is not None
        else:
            found = value in html
        (hits if found else misses).append(marker_label((kind, value)))
    return hits, misses


def describe_fetch_error(exc):
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (403, 429, 503):
        return (
            f"HTTP {status}: probable bot wall, curl was blocked. Not final: "
            "retest this URL in a real browser (SOURCE_GUIDE.md section 2, "
            "'Bot walls') before deciding."
        )
    if status:
        return f"HTTP {status}"
    return f"{type(exc).__name__}: {exc}"


def fetch(scraper, url):
    """Return (soup, html, error); exactly one of soup/error is set."""
    try:
        soup = scraper.get_soup(url)
    except Exception as e:
        return None, None, describe_fetch_error(e)
    html = str(soup)
    if BOT_WALL_RE.search(html):
        return None, None, (
            "HTTP 200 but the page is a bot-wall challenge. Retest in a real "
            "browser (SOURCE_GUIDE.md section 2, 'Bot walls')."
        )
    return soup, html, None


def verdict(tpl, scored, matched, total, failed):
    if total and matched / total >= USE_RATIO and "novel" in scored:
        text = f"use {class_name(tpl)}"
    elif matched:
        text = "partial match — check"
        if "novel" not in scored:
            text += " (give a novel URL for a verdict)"
    else:
        text = "no match"
    if failed:
        text += f" [not fetched: {', '.join(failed)}]"
    return text


def run_live(urls):
    from lncrawl.core.scraper import Scraper  # crawler deps, live mode only

    pages = list(zip(PAGE_TYPES, urls))
    origin = urlparse(urls[0])
    scraper = Scraper(f"{origin.scheme}://{origin.netloc}/")
    fetched, errors = {}, {}
    try:
        for page, url in pages:
            print(f"fetching {page}: {url}")
            soup, html, error = fetch(scraper, url)
            if error:
                errors[page] = error
                print(f"  failed: {error}")
            else:
                fetched[page] = (soup, html)
    finally:
        scraper.close()

    if not fetched:
        print("\nNo page could be fetched, so no template can be scored.")
        return

    rows = []
    for tpl in TEMPLATES:
        scored, details = {}, {}
        matched = total = 0
        for page, _ in pages:
            if page not in fetched:
                continue
            soup, html = fetched[page]
            hits, misses = page_hits(tpl[page], soup, html)
            scored[page] = (len(hits), len(tpl[page]))
            matched += len(hits)
            total += len(tpl[page])
            details[page] = (hits, misses)
        ratio = matched / total if total else 0.0
        rows.append(
            {
                "tpl": tpl,
                "scored": scored,
                "details": details,
                "matched": matched,
                "total": total,
                "ratio": ratio,
                "verdict": verdict(tpl, scored, matched, total, list(errors)),
            }
        )

    rows.sort(key=lambda r: (r["ratio"], r["matched"]), reverse=True)

    print()
    header = f"{'#':<3}{'template':<12}{'home':<8}{'novel':<8}{'chapter':<9}{'score':<8}verdict"
    print(header)
    print("-" * len(header))
    for i, row in enumerate(rows, 1):
        cells = []
        for page in PAGE_TYPES:
            if page in row["scored"]:
                h, t = row["scored"][page]
                cells.append(f"{h}/{t}")
            else:
                cells.append("-")
        print(
            f"{i:<3}{row['tpl']['name']:<12}{cells[0]:<8}{cells[1]:<8}{cells[2]:<9}"
            f"{row['matched']}/{row['total']:<6}{row['verdict']}"
        )

    print()
    for row in rows:
        name = row["tpl"]["name"]
        for page in PAGE_TYPES:
            if page not in row["details"]:
                continue
            hits, misses = row["details"][page]
            print(f"{name} / {page}")
            print(f"  hit:    {', '.join(hits) or '-'}")
            print(f"  missed: {', '.join(misses) or '-'}")
    if errors:
        print("\nNot fetched (verdicts above are partial):")
        for page, error in errors.items():
            print(f"  {page}: {error}")


def static_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name):
                    names.add(base.id)
                elif isinstance(base, ast.Attribute):
                    names.add(base.attr)
    return names


def marker_in_source(marker, text):
    kind, value = marker
    if kind == "text":
        return value in text
    # A comma-separated selector counts when any of its parts appears. A class or
    # id must not be a prefix of a longer name (".spe" is not ".speech").
    return any(
        re.search(re.escape(part.strip()) + r"(?![\w-])", text)
        for part in value.split(",")
    )


def run_existing():
    sources_dir = os.path.join(ROOT, "sources")
    rows = []
    scanned = 0
    for dirpath, _, files in os.walk(sources_dir):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            scanned += 1
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            try:
                bases = static_names(ast.parse(text))
            except SyntaxError:
                print(f"skipped (syntax error): {os.path.relpath(path, ROOT)}")
                continue
            if bases & CONCRETE_CLASSES:
                continue
            for tpl in TEMPLATES:
                markers = [m for page in PAGE_TYPES for m in tpl[page]]
                hits = [marker_label(m) for m in markers if marker_in_source(m, text)]
                # Half the markers (at least 2) in one file is a duplicate, not a coincidence.
                if len(hits) >= max(2, math.ceil(len(markers) / 2)):
                    rel = os.path.relpath(path, ROOT)
                    rows.append((rel, class_name(tpl), len(hits), len(markers), hits))

    print(f"sources scanned: {scanned}")
    if not rows:
        print("no hand-written source carries a template's markers")
        return
    rows.sort()
    print(f"\n{'SOURCE':<48}{'TEMPLATE':<22}{'HITS':<8}MATCHED MARKERS")
    for rel, tpl_name, hit, total, hits in rows:
        print(f"{rel:<48}{tpl_name:<22}{hit}/{total:<6}{'; '.join(hits)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("urls", nargs="*", help="home, novel and chapter URL")
    parser.add_argument(
        "--existing",
        action="store_true",
        help="scan sources/ statically for hand-written duplicates of templates",
    )
    args = parser.parse_args()

    if args.existing:
        run_existing()
        return 0

    if not 1 <= len(args.urls) <= 3:
        parser.error("give a home URL, optionally a novel URL and a chapter URL")
    for url in args.urls:
        if urlparse(url).scheme not in ("http", "https"):
            parser.error(f"not an http(s) URL: {url}")
    run_live(args.urls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
