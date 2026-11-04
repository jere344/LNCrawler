# -*- coding: utf-8 -*-
"""Quality-control dump of one source file. See SOURCE_GUIDE.md section 6b.

Usage:
    python -I tools/qc_source.py sources/en/r/royalroad.py [--novel URL ...]
        [--class Name] [--chapters 5] [--out DIR] [--seed N]

For every enabled crawler class in the file: pick two novels (``--novel`` or
the first ``browse_novels`` results), run ``read_novel_info`` + ``format_novel``
as the downloader does, fetch the cover, then download N random chapters of the
first novel and 2 of the second. Writes ``<out>/<Class>/report.md`` (metadata,
chapter list, volumes, body samples, automatic flags), ``data.json`` and the
covers as ``cover_<n>.jpg`` so they can be looked at.

Flags are heuristics: a flag is a lead to check against the live page, not a
verdict, and a clean report does not prove the extraction right (a publisher
shown on the page but never extracted raises no flag).
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import traceback
from collections import Counter
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bs4 import BeautifulSoup  # noqa: E402

from lncrawl.core.crawler import Crawler  # noqa: E402
from lncrawl.core.downloader import _drop_title_line  # noqa: E402
from lncrawl.core.novel_info import format_novel  # noqa: E402
from lncrawl.core.sources import _apply_module, _import_module_from_path  # noqa: E402

DATE_RE = re.compile(
    r"\b(19|20)\d\d[-/.]\d{1,2}[-/.]\d{1,2}\b|\b\d{1,2}[-/.]\d{1,2}[-/.](19|20)?\d\d\b"
    r"|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? (19|20)\d\d\b"
    r"|\b\d+ (seconds?|minutes?|hours?|days?|weeks?|months?|years?) ago\b"
    r"|\d{4}年\d{1,2}月|\d{1,2}月\d{1,2}日",
    re.I,
)
COUNT_RE = re.compile(
    r"\b\d[\d,.]*\s*(k|m)?\s*(words?|chapters?|views?|reads?|likes?|comments?|chars?|pages?|votes?)\b"
    r"|字|阅读|点击|万字",
    re.I,
)
STATUS_WORDS = {"ongoing", "completed", "complete", "hiatus", "dropped", "連載中", "完結", "连载", "完结"}
PLACEHOLDER_RE = re.compile(
    r"placeholder|no[-_]?image|no[-_]?cover|nocover|noimg|default[-_.]|blank\.|logo|"
    r"avatar|thumb[-_]?default|image[-_]?not|missing|empty|lazy|loading|spacer|1x1",
    re.I,
)
SYNOPSIS_JUNK_RE = re.compile(
    r"read more|show more|show less|\bmore\b\s*$|click here|read (it )?(online|free)|"
    r"alternative names?:|author\(s\)?:|genres?:|status:|tags?:|views?:|rating|"
    r"https?://|\bchapters?\s*\d+|latest chapter|bookmark|add to library|"
    r"translated by|translator:|publisher:|release[ds]?:",
    re.I,
)
NAV_RE = re.compile(
    r"previous chapter|next chapter|table of contents|\bprev\b|\bnext\b|上一章|下一章|目录|返回书页|"
    r"chương trước|chương sau|chapitre précédent|chapitre suivant|이전화|다음화|前へ|次へ",
    re.I,
)
WATERMARK_RE = re.compile(
    r"patreon|ko-?fi|discord\.gg|discord|paypal|support (us|me|the translator)|"
    r"read (it )?(at|on)\b|visit (us|our|the site|\w+\.\w+)|for the (latest|fastest)|find (this|more)|original(ly)? (at|on|from)|"
    r"(please )?(don't|do not) (copy|repost|steal)|stolen|if you('re| are) (not )?reading this|"
    r"translat(ed|ion) by|edited by|proofread|tl ?note|t/n:|\[tl|"
    r"©|copyright|all rights reserved|https?://|www\.|\.com\b|\.net\b|\.org\b|"
    r"本章未完|请记住|最新章节|手机阅读|天才一秒|笔趣阁|免费阅读|加入书签|"
    r"novel(bin|full|fire|pub|updates)|lightnovel|webnovel|wuxiaworld|freewebnovel",
    re.I,
)
MOJIBAKE_RE = re.compile(r"Ã.|â€|ï¿½|�")


def text_of(html):
    soup = BeautifulSoup(html or "", "lxml")
    lines = [x.strip() for x in soup.get_text("\n").split("\n")]
    return soup, [x for x in lines if x]


def flag_value(value, kind):
    out = []
    v = str(value).strip()
    if not v:
        out.append(f"empty {kind}")
        return out
    if DATE_RE.search(v):
        out.append(f"{kind} looks like a date: {v!r}")
    if COUNT_RE.search(v):
        out.append(f"{kind} looks like a count: {v!r}")
    if re.fullmatch(r"[\d\s,.%:/-]+", v):
        out.append(f"{kind} is only digits: {v!r}")
    if v.lower() in STATUS_WORDS:
        out.append(f"{kind} is a status word: {v!r}")
    if "http" in v or "www." in v:
        out.append(f"{kind} contains a URL: {v!r}")
    if len(v) > (60 if kind == "tag" else 80):
        out.append(f"{kind} is very long ({len(v)} chars): {v[:80]!r}")
    if re.search(r"^(author|by|tags?|genres?|status|translator)\s*[:：]", v, re.I):
        out.append(f"{kind} keeps its label: {v!r}")
    return out


def check_cover(crawler, url, out_dir, n):
    info = {"url": url}
    if not url:
        info["flags"] = ["no cover (fine if the site has none)"]
        return info
    flags = []
    if not url.startswith(("http://", "https://", "data:")):
        flags.append("cover URL is not absolute")
    if PLACEHOLDER_RE.search(urlparse(url).path):
        flags.append("cover URL looks like a placeholder")
    try:
        img = crawler.download_image(url)
        info["size"] = img.size
        info["format"] = img.format
        w, h = img.size
        if w < 100 or h < 100:
            flags.append(f"cover is tiny {w}x{h}")
        if h and not 0.4 <= w / h <= 1.6:
            flags.append(f"cover has an odd aspect ratio {w}x{h}")
        small = img.convert("L").resize((16, 16))
        info["phash"] = hashlib.sha1(small.tobytes()).hexdigest()[:12]
        colors = img.convert("RGB").resize((32, 32)).getcolors(1024) or []
        if len(colors) < 12:
            flags.append(f"cover has only {len(colors)} colors (blank/logo?)")
        path = os.path.join(out_dir, f"cover_{n}.jpg")
        thumb = img.convert("RGB")
        thumb.thumbnail((300, 450))
        thumb.save(path, "JPEG")
        info["file"] = path
    except Exception as e:
        flags.append(f"cover download failed: {type(e).__name__}: {str(e)[:120]}")
    info["flags"] = flags
    return info


def check_chapters(crawler):
    flags = []
    chapters = crawler.chapters
    volumes = crawler.volumes
    if not chapters:
        return ["NO CHAPTERS"]
    ids = [c["id"] for c in chapters]
    if ids != list(range(1, len(ids) + 1)):
        flags.append("chapter ids are not sequential from 1")
    urls = Counter(c["url"] for c in chapters)
    dup = [u for u, k in urls.items() if k > 1]
    if dup:
        flags.append(f"{len(dup)} duplicate chapter URLs, e.g. {dup[0]}")
    titles = Counter(c["title"] for c in chapters)
    dupt = [t for t, k in titles.items() if k > 1]
    if dupt:
        flags.append(f"{len(dupt)} duplicate chapter titles, e.g. {dupt[0]!r}")
    seen = Counter()
    for c in chapters:
        t = str(c.get("title") or "")
        if not t.strip():
            seen["empty title"] += 1
        if DATE_RE.search(t):
            seen["title with a date"] += 1
        if COUNT_RE.search(t):
            seen["title with a count"] += 1
        if re.search(r"[\[(【](new|hot|free|vip|locked|updated?)[\])】]|\s(NEW|HOT|VIP|FREE)$|🔒", t, re.I):
            seen["title with a badge word"] += 1
        if len(t) > 150:
            seen["title over 150 chars"] += 1
        if re.search(r"\s{2,}|\n", t):
            seen["title with extra whitespace"] += 1
    for k, n in seen.items():
        ex = next(
            c["title"]
            for c in chapters
            if (k == "empty title" and not str(c.get("title") or "").strip())
            or (k == "title with a date" and DATE_RE.search(str(c.get("title"))))
            or (k == "title with a count" and COUNT_RE.search(str(c.get("title"))))
            or (k == "title with a badge word" and re.search(r"[\[(【](new|hot|free|vip|locked|updated?)[\])】]|\s(NEW|HOT|VIP|FREE)$|🔒", str(c.get("title")), re.I))
            or (k == "title over 150 chars" and len(str(c.get("title"))) > 150)
            or (k == "title with extra whitespace" and re.search(r"\s{2,}|\n", str(c.get("title"))))
        )
        flags.append(f"{n} chapters: {k}, e.g. {ex!r}")
    vol_mention = sum(
        1 for c in chapters if re.search(r"\b(vol(ume)?\.?|book|arc|part)\s*\d+|第.{1,4}[卷部]|巻", str(c["title"]), re.I)
    )
    if len(volumes) <= 1 and vol_mention > len(chapters) * 0.3:
        flags.append(f"{vol_mention} chapter titles mention a volume/book/arc but only {len(volumes)} volume(s) extracted")
    vol_ids = [v["id"] for v in volumes]
    if volumes:
        loose = sum(1 for c in chapters if c.get("volume") not in vol_ids)
        if loose:
            flags.append(f"{loose} chapters are in no volume")
    order = [c.get("volume") for c in chapters]
    runs = [v for i, v in enumerate(order) if i == 0 or v != order[i - 1]]
    if len(runs) != len(set(runs)):
        flags.append("volumes are not contiguous in reading order (chapters interleave)")
    if len(volumes) > 1:
        vt = Counter(v.get("title") or "" for v in volumes)
        if vt.get("", 0):
            flags.append(f"{vt['']} volumes without a title")
        if any(k > 1 for t, k in vt.items() if t):
            flags.append("duplicate volume titles")
        covers = [v.get("cover_url") for v in volumes if v.get("cover_url")]
        if covers and crawler.novel_cover in covers:
            flags.append("a volume cover reuses the novel cover")
        if covers and len(set(covers)) < len(covers):
            flags.append("volume covers repeat (placeholder?)")
        for v in volumes:
            if re.fullmatch(r"(volume|vol\.?|卷)\s*\d+", str(v.get("title") or ""), re.I):
                flags.append(f"generic volume title {v.get('title')!r}: check the site has no real name")
                break
    return flags


def check_body(html, title, host):
    flags = []
    # The downloader drops a leading line that repeats the title; check what it saves.
    html = _drop_title_line(html, title)
    soup, lines = text_of(html)
    text = "\n".join(lines)
    if len(text) < 300:
        flags.append(f"short body ({len(text)} chars)")
    for tag in ("script", "style", "iframe", "form", "button", "ins", "noscript", "nav"):
        if soup.find(tag):
            flags.append(f"body contains <{tag}>")
    links = soup.find_all("a")
    if links:
        flags.append(f"body contains {len(links)} <a> links, e.g. {links[0].get_text(strip=True)[:40]!r} -> {str(links[0].get('href'))[:60]}")
    paras = len(soup.find_all("p"))
    brs = len(soup.find_all("br"))
    if paras <= 1 and brs < 3 and len(text) > 1500:
        flags.append("body is one block with no paragraph breaks")
    if paras > 5 and brs > paras * 2:
        flags.append(f"<br> heavy ({brs} br vs {paras} p): check paragraphs are split")
    long_para = max((len(p.get_text()) for p in soup.find_all("p")), default=0)
    if long_para > 4000:
        flags.append(f"a <p> of {long_para} chars: paragraphs probably merged")
    empty_p = sum(1 for p in soup.find_all("p") if not p.get_text(strip=True) and not p.find("img"))
    if empty_p > 5:
        flags.append(f"{empty_p} empty <p>")
    t0 = re.sub(r"\W+", "", str(title)).lower()
    if lines and t0 and re.sub(r"\W+", "", lines[0]).lower().startswith(t0[:20]):
        flags.append(f"body starts with the chapter title {lines[0][:60]!r} (downloader adds an <h1>: duplicate heading)")
    for i, line in enumerate(lines):
        where = "head" if i < 3 else "tail" if i >= len(lines) - 3 else "middle"
        if NAV_RE.search(line) and len(line) < 80:
            flags.append(f"nav text ({where}): {line[:80]!r}")
        m = WATERMARK_RE.search(line)
        if m:
            flags.append(f"watermark/credit? ({where}) [{m.group(0)}]: {line[:120]!r}")
        if host and host.split(".")[-2] in line.lower():
            flags.append(f"site name in text ({where}): {line[:120]!r}")
    if MOJIBAKE_RE.search(text):
        flags.append("mojibake / replacement characters")
    hidden = soup.select('[style*="display:none"], [style*="display: none"], [hidden]')
    if hidden:
        flags.append(f"{len(hidden)} hidden elements kept in body: {hidden[0].get_text(strip=True)[:60]!r}")
    # Collapse repeats (one watermark line per paragraph adds the same flag many times).
    return list(dict.fromkeys(flags))[:25]


def pick_novels(cls, urls):
    if urls:
        return urls, []
    notes = []
    c = cls()
    c.initialize()
    try:
        res = c.browse_novels(0, 12)
        found = [r.url for r in res if getattr(r, "url", None)]
    except NotImplementedError:
        found, notes = [], ["browse_novels not implemented"]
    except Exception as e:
        found, notes = [], [f"browse_novels failed: {type(e).__name__}: {str(e)[:150]}"]
    if not found:
        return [], notes + ["no novel URL: pass --novel"]
    picks = [found[0]]
    if len(found) > 1:
        picks.append(random.choice(found[1:]))
    return picks, notes


def run_novel(cls, url, out_dir, n, n_chapters):
    c = cls()
    c.initialize()
    c.novel_url = url
    c.read_novel_info()
    raw = {
        "author": c.novel_author,
        "tags": list(getattr(c, "novel_tags", []) or []),
        "genres": list(getattr(c, "genres", []) or []),
    }
    format_novel(c)
    meta = {
        "url": url,
        "title": c.novel_title,
        "author_raw": raw["author"],
        "authors": [x.strip() for x in c.novel_author.split(",") if x.strip()],
        "tags": c.novel_tags,
        "alternative_titles": c.alternative_titles,
        "status": str(getattr(c, "status", None)),
        "edition": getattr(c, "novel_edition", "") or None,
        "translators": getattr(c, "translators", None),
        "editors": getattr(c, "editors", None),
        "original_publisher": getattr(c, "original_publisher", None),
        "english_publisher": getattr(c, "english_publisher", None),
        "language": c.language,
        "is_adult": getattr(c, "is_adult", False),
        "has_mtl": c.has_mtl,
        "synopsis": c.novel_synopsis,
    }
    flags = []
    if not c.novel_title:
        flags.append("empty title")
    for a in meta["authors"] or [""]:
        flags += flag_value(a, "author")
        if a and a.lower() == (c.novel_title or "").lower():
            flags.append("author equals the title")
    for t in c.novel_tags:
        flags += flag_value(t, "tag")
    if len(c.novel_tags) > 60:
        flags.append(f"{len(c.novel_tags)} tags (site-wide list scraped?)")
    syn = c.novel_synopsis or ""
    s_text = "\n".join(text_of(syn)[1]) if "<" in syn else syn
    if len(s_text) < 40:
        flags.append(f"synopsis short/empty ({len(s_text)} chars)")
    if len(s_text) > 6000:
        flags.append(f"synopsis very long ({len(s_text)} chars): page text scraped?")
    for m in SYNOPSIS_JUNK_RE.finditer(s_text):
        flags.append(f"synopsis junk? [{m.group(0)}]: ...{s_text[max(0, m.start() - 40):m.end() + 40]!r}...")
    if meta["status"] in ("None", "NovelStatus.unknown", "unknown"):
        flags.append("status unknown (fine if the site shows none)")
    cover = check_cover(c, c.novel_cover, out_dir, n)
    meta["cover"] = cover

    vols = []
    for v in c.volumes:
        chs = [x for x in c.chapters if x.get("volume") == v["id"]]
        vols.append(
            {
                "id": v["id"],
                "title": v.get("title"),
                "chapter_count": len(chs),
                "first": chs[0]["title"] if chs else None,
                "last": chs[-1]["title"] if chs else None,
                "cover_url": v.get("cover_url"),
            }
        )
    ch_flags = check_chapters(c)
    host = urlparse(url).hostname or ""
    samples = []
    pool = list(c.chapters)
    picks = sorted(random.sample(pool, min(n_chapters, len(pool))), key=lambda x: x["id"])
    for ch in picks:
        item = {"id": ch["id"], "title": ch["title"], "url": ch["url"], "volume": ch.get("volume")}
        try:
            body = c.download_chapter_body(ch) or ""
            _, lines = text_of(body)
            item.update(
                html_len=len(body),
                text_len=sum(len(x) for x in lines),
                html_head=body[:400],
                text_head=lines[:6],
                text_tail=lines[-6:],
                lines=lines,
                flags=check_body(body, ch["title"], host),
            )
        except Exception as e:
            item["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        samples.append(item)
    chapters = [{"id": x["id"], "title": x["title"], "volume": x.get("volume"), "url": x["url"]} for x in c.chapters]
    return {"meta": meta, "flags": flags, "volumes": vols, "chapter_flags": ch_flags, "chapters": chapters, "samples": samples}


def cross_checks(novels):
    flags = []
    if len(novels) < 2:
        return flags
    a, b = novels[0]["meta"], novels[1]["meta"]
    pa, pb = a["cover"].get("phash"), b["cover"].get("phash")
    if pa and pa == pb:
        flags.append("both novels have the same cover image: placeholder")
    sa, sb = a["synopsis"] or "", b["synopsis"] or ""
    if sa and sa == sb:
        flags.append("both novels have the same synopsis: site description scraped")
    pre = os.path.commonprefix([sa, sb])
    suf = os.path.commonprefix([sa[::-1], sb[::-1]])[::-1]
    if len(pre.strip()) > 30 and sa != sb:
        flags.append(f"synopses share a prefix (boilerplate?): {pre[:100]!r}")
    if len(suf.strip()) > 30 and sa != sb:
        flags.append(f"synopses share a suffix (boilerplate?): {suf[-100:]!r}")
    if a["tags"] and a["tags"] == b["tags"] and len(a["tags"]) > 3:
        flags.append("both novels have identical tags: site-wide list?")
    if a["authors"] and a["authors"] == b["authors"]:
        flags.append(f"both novels have the same author {a['authors']}: check it's real")
    # Lines that recur across chapters of different novels are boilerplate or watermarks.
    counts = Counter()
    for nv in novels:
        for s in nv["samples"]:
            for line in set(s.get("lines") or []):
                if len(line) > 15:
                    counts[line] += 1
    total = sum(len(nv["samples"]) for nv in novels)
    for line, k in counts.most_common(8):
        if k >= 3 and k >= total / 2:
            flags.append(f"line repeated in {k}/{total} chapters (boilerplate/watermark): {line[:120]!r}")
    return flags


def write_report(path, cls, novels, cross, notes):
    out = [f"# QC {cls.__name__} ({cls.file_path})", ""]
    out.append(f"base_url: {cls.base_url}  version: {cls.version}  language: {cls.language}")
    for note in notes:
        out.append(f"- NOTE: {note}")
    if cross:
        out += ["", "## Cross-novel flags"] + [f"- {f}" for f in cross]
    for i, nv in enumerate(novels):
        if "error" in nv:
            out += ["", f"## Novel {i}: {nv['url']}", "", "ERROR:", "```", nv["error"], "```"]
            continue
        m = nv["meta"]
        out += ["", f"## Novel {i}: {m['title']}", f"url: {m['url']}", ""]
        for k in (
            "author_raw", "authors", "tags", "alternative_titles", "status", "edition",
            "translators", "editors", "original_publisher", "english_publisher", "is_adult", "has_mtl",
        ):
            out.append(f"- {k}: {m[k]!r}")
        cov = m["cover"]
        out.append(f"- cover: {cov.get('url')} size={cov.get('size')} file={cov.get('file')}")
        out += ["", "### Synopsis", "```", (m["synopsis"] or "")[:3000], "```"]
        out += ["", "### Metadata flags"] + [f"- {f}" for f in nv["flags"] + cov.get("flags", [])]
        out += ["", f"### Chapter list ({len(nv['chapters'])} chapters, {len(nv['volumes'])} volumes)"]
        out += [f"- {f}" for f in nv["chapter_flags"]]
        out.append("")
        for v in nv["volumes"][:40]:
            out.append(
                f"- vol {v['id']} {v['title']!r}: {v['chapter_count']} ch, {v['first']!r} .. {v['last']!r}"
                + (f", cover {v['cover_url']}" if v["cover_url"] else "")
            )
        if len(nv["volumes"]) > 40:
            out.append(f"- ... {len(nv['volumes']) - 40} more volumes")
        out += ["", "first 8 / last 4 chapter titles:"]
        chs = nv["chapters"]
        for ch in chs[:8] + chs[-4:] if len(chs) > 12 else chs:
            out.append(f"  {ch['id']}: {ch['title']!r} (vol {ch['volume']})")
        out += ["", "### Chapter samples"]
        for s in nv["samples"]:
            out += ["", f"#### ch {s['id']}: {s['title']!r} — {s['url']}"]
            if "error" in s:
                out.append(f"ERROR: {s['error']}")
                continue
            out.append(f"html {s['html_len']} chars, text {s['text_len']} chars")
            out += [f"- FLAG {f}" for f in s["flags"]]
            out += ["html head:", "```html", s["html_head"], "```"]
            out += ["text head:"] + [f"> {x[:200]}" for x in s["text_head"]]
            out += ["text tail:"] + [f"> {x[:200]}" for x in s["text_tail"]]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--novel", action="append", default=[])
    ap.add_argument("--class", dest="cls")
    ap.add_argument("--chapters", type=int, default=5)
    ap.add_argument("--out", default="qc_out")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.seed)

    path = os.path.abspath(args.source)
    module = _import_module_from_path(path)
    classes = [c for c in _apply_module(path, module) if issubclass(c, Crawler)]
    if args.cls:
        classes = [c for c in classes if c.__name__ == args.cls]
    for cls in classes:
        if cls.is_disabled:
            print(f"{cls.__name__}: disabled ({cls.disable_reason})")
            continue
        out_dir = os.path.join(args.out, cls.__name__)
        os.makedirs(out_dir, exist_ok=True)
        urls, notes = pick_novels(cls, args.novel)
        if getattr(cls, "login_required", False):
            notes.append("login_required: needs credentials in the environment")
        novels = []
        for n, url in enumerate(urls[:2]):
            try:
                novels.append(run_novel(cls, url, out_dir, n, args.chapters if n == 0 else 2))
            except Exception:
                novels.append({"url": url, "error": traceback.format_exc()[-1500:]})
        ok = [x for x in novels if "error" not in x]
        cross = cross_checks(ok)
        report = os.path.join(out_dir, "report.md")
        write_report(report, cls, novels, cross, notes)
        with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump({"notes": notes, "cross": cross, "novels": novels}, f, ensure_ascii=False, indent=1, default=str)
        n_flags = len(cross) + sum(len(x.get("flags", [])) + len(x.get("chapter_flags", [])) for x in ok)
        print(f"{cls.__name__}: {len(ok)}/{len(urls)} novels ok, {n_flags} flags -> {report}")


if __name__ == "__main__":
    main()
