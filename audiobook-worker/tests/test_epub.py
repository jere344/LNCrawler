import zipfile

import pytest

from worker import epub
from worker.epub import EpubChapter, EpubError

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test</dc:title></metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="c1" href="text/chapter%201.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="text/c2.xhtml" media-type="application/xhtml+xml"/>
    <item id="c3" href="text/c3.xhtml" media-type="application/xhtml+xml"/>
    <item id="notes" href="text/notes.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="c2"/>
    <itemref idref="c1"/>
    <itemref idref="nav"/>
    <itemref idref="notes" linear="no"/>
    <itemref idref="c3"/>
  </spine>
</package>"""

CHAPTER_1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Ignored title</title><style>p { color: red }</style></head>
<body>
<h1>Chapter 1</h1>
<p>It was a   dark night.</p>
<p>She said &amp; left.<br/>Then silence.</p>
<div><p>Line in a div</p></div>
<h2>A break</h2>
<p>After the break.</p>
<script>var x = 1;</script>
</body>
</html>"""

CHAPTER_2 = """<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter Two</title></head>
<body>
<p>Chapter Two.</p>
<p>The second chapter begins.</p>
</body>
</html>"""

CHAPTER_3 = """<html xmlns="http://www.w3.org/1999/xhtml">
<body><h1>Chapter 3</h1><p>   </p></body>
</html>"""

NOTES = """<html xmlns="http://www.w3.org/1999/xhtml"><body><p>A footnote.</p></body></html>"""

NAV = """<html xmlns="http://www.w3.org/1999/xhtml"><body><nav><ol><li>Chapter 1</li></ol></nav></body></html>"""


def _files(**overrides: str | bytes | None) -> dict[str, str | bytes]:
    """The book's archive members. A None override leaves the member out."""
    files = {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/content.opf": OPF,
        "OEBPS/nav.xhtml": NAV,
        "OEBPS/text/chapter 1.xhtml": CHAPTER_1,
        "OEBPS/text/c2.xhtml": CHAPTER_2,
        "OEBPS/text/c3.xhtml": CHAPTER_3,
        "OEBPS/text/notes.xhtml": NOTES,
    }
    for name, content in overrides.items():
        if content is None:
            files.pop(name)
        else:
            files[name] = content
    return files


def _write_epub(path, files: dict[str, str | bytes]) -> str:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return str(path)


def _book(tmp_path, **overrides: str | bytes | None) -> str:
    return _write_epub(tmp_path / "book.epub", _files(**overrides))


def _c2(tmp_path, xhtml: str) -> EpubChapter:
    """The first chapter of a book whose spine starts with c2, with c2 replaced by `xhtml`."""
    return epub.read_chapters(_book(tmp_path, **{"OEBPS/text/c2.xhtml": xhtml}))[0]


def test_chapters_follow_spine_order_and_skip_nav_linear_no_and_empty(tmp_path):
    chapters = epub.read_chapters(_book(tmp_path))

    assert [c.title for c in chapters] == ["Chapter Two", "Chapter 1"]
    assert all(isinstance(c, EpubChapter) for c in chapters)


def test_heading_is_not_body_text_and_paragraphs_split_on_blocks_and_br(tmp_path):
    chapter_1 = epub.read_chapters(_book(tmp_path))[1]

    assert chapter_1.text == "\n".join(
        [
            "It was a dark night.",
            "She said & left.",
            "Then silence.",
            "Line in a div",
            "A break",
            "After the break.",
        ]
    )


def test_first_paragraph_repeating_the_title_is_dropped(tmp_path):
    chapter_2 = epub.read_chapters(_book(tmp_path))[0]

    assert chapter_2.title == "Chapter Two"
    assert chapter_2.text == "The second chapter begins."


def test_leading_headings_are_dropped_but_later_headings_stay(tmp_path):
    chapter = _c2(tmp_path, "<html><body><h1>Title</h1><h2>Sub</h2><p>Body one.</p><h3>Mid</h3><p>Body two.</p></body></html>")

    assert chapter.title == "Title"
    assert chapter.text == "Body one.\nMid\nBody two."


def test_heading_beats_title_element(tmp_path):
    chapter = _c2(tmp_path, "<html><head><title>From head</title></head><body><h2>From heading</h2><p>Text.</p></body></html>")

    assert chapter.title == "From heading"


def test_title_repeat_ignores_case_and_punctuation(tmp_path):
    chapter = _c2(tmp_path, "<html><head><title>Chapter Two</title></head><body><p>CHAPTER TWO!</p><p>Real text.</p></body></html>")

    assert chapter.title == "Chapter Two"
    assert chapter.text == "Real text."


def test_chapter_without_title_has_empty_title(tmp_path):
    chapter = _c2(tmp_path, "<html><body><p>Only text.</p></body></html>")

    assert chapter.title == ""
    assert chapter.text == "Only text."


def test_not_a_zip_raises(tmp_path):
    path = tmp_path / "book.epub"
    path.write_bytes(b"this is not a zip")

    with pytest.raises(EpubError, match="not a zip"):
        epub.read_chapters(str(path))


def test_missing_container_raises(tmp_path):
    path = _book(tmp_path, **{"META-INF/container.xml": None})

    with pytest.raises(EpubError, match="container.xml is missing"):
        epub.read_chapters(path)


def test_container_without_rootfile_raises(tmp_path):
    empty = '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles/></container>'
    path = _book(tmp_path, **{"META-INF/container.xml": empty})

    with pytest.raises(EpubError, match="names no package document"):
        epub.read_chapters(path)


def test_missing_opf_raises(tmp_path):
    path = _book(tmp_path, **{"OEBPS/content.opf": None})

    with pytest.raises(EpubError, match="content.opf is missing"):
        epub.read_chapters(path)


def test_opf_without_spine_raises(tmp_path):
    opf = OPF.replace("<spine>", "<notspine>").replace("</spine>", "</notspine>")
    path = _book(tmp_path, **{"OEBPS/content.opf": opf})

    with pytest.raises(EpubError, match="has no spine"):
        epub.read_chapters(path)


def test_spine_item_missing_from_archive_raises(tmp_path):
    path = _book(tmp_path, **{"OEBPS/text/c3.xhtml": None})

    with pytest.raises(EpubError, match="c3.xhtml is missing"):
        epub.read_chapters(path)


def test_title_is_the_first_heading_before_any_body_text(tmp_path):
    chapter = _c2(tmp_path, "<html><head><title>From head</title></head><body><p>Intro.</p><h1>Late</h1><p>Rest.</p></body></html>")

    assert chapter.title == "From head"
    assert chapter.text == "Intro.\nLate\nRest."


def test_heading_after_a_later_body_text_is_not_the_title(tmp_path):
    chapter = _c2(tmp_path, "<html><body><h4>Small</h4><h2>Chapter</h2><p>Body.</p><h1>Late</h1></body></html>")

    assert chapter.title == "Chapter"
    assert chapter.text == "Body.\nLate"


def test_definition_and_table_cells_end_lines(tmp_path):
    chapter = _c2(
        tmp_path,
        "<html><body><dl><dt>Term</dt><dd>Definition</dd></dl>"
        "<table><tr><td>One</td><td>Two</td></tr><tr><th>Three</th></tr></table>"
        "<ul><li>Item</li></ul><pre>code</pre><hr/><p>End.</p></body></html>",
    )

    assert chapter.text == "Term\nDefinition\nOne\nTwo\nThree\nItem\ncode\nEnd."


def test_namespace_prefixed_tags_are_read_as_their_local_names(tmp_path):
    chapter = _c2(
        tmp_path,
        '<html xmlns:x="http://www.w3.org/1999/xhtml"><body><x:h1>Prefixed</x:h1>'
        "<x:p>Hello</x:p><x:p>World<x:br/>again</x:p></body></html>",
    )

    assert chapter.title == "Prefixed"
    assert chapter.text == "Hello\nWorld\nagain"


def test_declared_encoding_decodes_the_chapter(tmp_path):
    xhtml = '<?xml version="1.0" encoding="windows-1252"?>\n<html><body><p>Caf\xe9 noir.</p></body></html>'
    path = _book(tmp_path, **{"OEBPS/text/c2.xhtml": xhtml.encode("cp1252")})

    chapter = epub.read_chapters(path)[0]

    assert chapter.text == "Café noir."


def test_meta_charset_decodes_when_there_is_no_xml_declaration(tmp_path):
    xhtml = '<html><head><meta charset="windows-1252"/></head><body><p>Caf\xe9.</p></body></html>'
    path = _book(tmp_path, **{"OEBPS/text/c2.xhtml": xhtml.encode("cp1252")})

    assert epub.read_chapters(path)[0].text == "Café."


def test_unknown_declared_encoding_falls_back_to_utf8(tmp_path):
    xhtml = '<?xml version="1.0" encoding="x-no-such-codec"?>\n<html><body><p>Café.</p></body></html>'
    path = _book(tmp_path, **{"OEBPS/text/c2.xhtml": xhtml.encode("utf-8")})

    assert epub.read_chapters(path)[0].text == "Café."


def test_title_repeat_examples_are_dropped(tmp_path):
    chapter = _c2(tmp_path, "<html><head><title>Ch 1</title></head><body><p>Chapter 1</p><p>Real text.</p></body></html>")
    assert chapter.title == "Ch 1"
    assert chapter.text == "Real text."

    french = (
        "<html><body><h1>Chapitre 1 : Chapitre I – « Un baiser, chère Mère » – Partie I</h1>"
        "<p>Chapitre I</p><p>« Un baiser, chère Mère »</p><p>Partie I</p>"
        "<p>Le fils rentra tard.</p></body></html>"
    )
    chapter = _c2(tmp_path, french)
    assert chapter.title == "Chapitre 1 : Chapitre I – « Un baiser, chère Mère » – Partie I"
    assert chapter.text == "Le fils rentra tard."


def test_cjk_title_does_not_drop_a_sentence(tmp_path):
    chapter = _c2(tmp_path, "<html><body><h1>第一章</h1><p>他走进了房间。</p></body></html>")

    assert chapter.title == "第一章"
    assert chapter.text == "他走进了房间。"


def test_title_repeat_never_drops_every_line_of_a_chapter(tmp_path):
    chapter = _c2(tmp_path, "<html><body><h1>Chapter Two</h1><p>Chapter Two</p><p>Chapter two.</p></body></html>")

    assert chapter.text == "Chapter Two\nChapter two."
