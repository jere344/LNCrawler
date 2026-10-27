"""Export lncrawler chapters as a few EPUB "volumes" of one Castwright series.

Each EPUB carries the same author and calibre:series metadata with an increasing
series_index, which is what Castwright's series memory keys on to carry voices
from one book to the next.

    docker compose exec castwright /opt/venv/bin/python /bench/make_volumes.py \
        "/novels/<novel>/<source>" --volumes 3 --chapters 5

Reads <source>/json/NNNNN.json (read-only mount) and writes /out/*.epub.
"""
import argparse
import html
import json
import os
import re
import sys
import uuid
import zipfile
from html.parser import HTMLParser


class _Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paras, self._cur = [], []

    def _flush(self):
        text = " ".join("".join(self._cur).split())
        if text:
            self.paras.append(text)
        self._cur = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "div", "h1", "h2", "h3", "li"):
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("p", "div", "h1", "h2", "h3", "li"):
            self._flush()

    def handle_data(self, data):
        self._cur.append(data)

    def close(self):
        super().close()
        self._flush()


def paragraphs(body_html):
    parser = _Paragraphs()
    parser.feed(body_html or "")
    parser.close()
    return [html.unescape(p) for p in parser.paras]


def novel_meta(source_dir):
    title = os.path.basename(os.path.dirname(source_dir.rstrip("/")))
    author = "Unknown"
    try:
        with open(os.path.join(source_dir, "meta.json"), encoding="utf-8") as f:
            novel = json.load(f).get("novel") or {}
        title = novel.get("title") or title
        authors = novel.get("authors") or novel.get("author")
        if isinstance(authors, list) and authors:
            author = ", ".join(map(str, authors))
        elif isinstance(authors, str) and authors.strip():
            author = authors.strip()
    except (OSError, ValueError):
        pass
    return title, author


def xhtml(title, paras, lang):
    body = "\n".join(f"<p>{html.escape(p)}</p>" for p in paras)
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}">'
            f"<head><title>{html.escape(title)}</title></head>"
            f"<body><h1>{html.escape(title)}</h1>\n{body}</body></html>")


def write_epub(path, *, title, author, series, index, lang, chapters):
    book_id = f"urn:uuid:{uuid.uuid4()}"
    items, spine, nav_li, ncx_points = [], [], [], []
    for n, (ch_title, _) in enumerate(chapters, 1):
        items.append(f'<item id="c{n}" href="c{n}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{n}"/>')
        nav_li.append(f'<li><a href="c{n}.xhtml">{html.escape(ch_title)}</a></li>')
        ncx_points.append(f'<navPoint id="p{n}" playOrder="{n}"><navLabel><text>{html.escape(ch_title)}</text>'
                          f'</navLabel><content src="c{n}.xhtml"/></navPoint>')
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>{html.escape(author)}</dc:creator>
    <dc:language>{lang}</dc:language>
    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
    <meta name="calibre:series" content="{html.escape(series)}"/>
    <meta name="calibre:series_index" content="{index}"/>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    {''.join(items)}
  </manifest>
  <spine toc="ncx">{''.join(spine)}</spine>
</package>"""
    nav = (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
           f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
           f'<head><title>{html.escape(title)}</title></head><body>'
           f'<nav epub:type="toc"><ol>{"".join(nav_li)}</ol></nav></body></html>')
    ncx = (f'<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content="{book_id}"/></head>'
           f'<docTitle><text>{html.escape(title)}</text></docTitle><navMap>{"".join(ncx_points)}</navMap></ncx>')
    container = ('<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        for n, (ch_title, paras) in enumerate(chapters, 1):
            z.writestr(f"OEBPS/c{n}.xhtml", xhtml(ch_title, paras, lang), compress_type=zipfile.ZIP_DEFLATED)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source_dir", help="/novels/<novel>/<source>")
    ap.add_argument("--volumes", type=int, default=3)
    ap.add_argument("--chapters", type=int, default=5, help="chapters per volume")
    ap.add_argument("--start", type=int, default=1, help="first chapter number")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--out", default="/out")
    args = ap.parse_args()

    json_dir = os.path.join(args.source_dir, "json")
    if not os.path.isdir(json_dir):
        if os.path.exists(os.path.join(args.source_dir, "json.7z")):
            sys.exit("This source is archived (json.7z). Pick a source with a json/ folder, "
                     "or open its chapters once in lncrawler so they get extracted.")
        sys.exit(f"No json/ folder in {args.source_dir}")
    files = sorted(f for f in os.listdir(json_dir) if re.fullmatch(r"\d+\.json", f))
    files = [f for f in files if int(f[:-5]) >= args.start]
    need = args.volumes * args.chapters
    if len(files) < need:
        sys.exit(f"Only {len(files)} chapters from #{args.start}, need {need}.")

    title, author = novel_meta(args.source_dir)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "novel"
    os.makedirs(args.out, exist_ok=True)
    for v in range(args.volumes):
        chapters = []
        for f in files[v * args.chapters:(v + 1) * args.chapters]:
            with open(os.path.join(json_dir, f), encoding="utf-8") as fh:
                data = json.load(fh)
            paras = paragraphs(data.get("body"))
            ch_title = data.get("title") or f"Chapter {int(f[:-5])}"
            if paras and paras[0].strip().lower() == ch_title.strip().lower():
                paras = paras[1:]
            chapters.append((ch_title, paras))
        first, last = int(files[v * args.chapters][:-5]), int(files[(v + 1) * args.chapters - 1][:-5])
        out = os.path.join(args.out, f"{slug}-part{v + 1}.epub")
        write_epub(out, title=f"{title} - Part {v + 1}, chapters {first}-{last}", author=author,
                   series=title, index=v + 1, lang=args.lang, chapters=chapters)
        words = sum(len(p.split()) for _, ps in chapters for p in ps)
        print(f"{out}  ({len(chapters)} chapters, {words} words)")
    print(f'series "{title}" by {author}: import the parts in order in Castwright.')


if __name__ == "__main__":
    main()
