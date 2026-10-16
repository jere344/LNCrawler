"""Read-only import of a NovelUpdates reading-list XML export.

The export lives behind NovelUpdates > Reading List > Global Settings >
"Export Reading List" and looks like this::

    <nu_readinglist>
      <list>Reading (Manual)
        <series><title>D-Genesis</title><chp>v0c0</chp></series>
        ...
      </list>
    </nu_readinglist>

The list name is the direct text node of ``<list>``; each ``<series>`` holds a
``<title>`` and an optional ``<chp>`` (``vXcY``, ``cY``, ``Y`` or empty). The
file carries no URL or status, so entries are matched by title against the
local library.
"""

import re

from django.db.models import Q
from lxml import etree

from ..models.novels_models import Novel

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

_CHP_RE = re.compile(r"^(?:v(\d+))?c(\d+)$")
_NUM_RE = re.compile(r"^(\d+)$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{4,}")


def _parser():
    # Never resolve external entities and forbid network access: the upload is
    # untrusted. ``huge_tree`` off caps entity expansion (billion laughs).
    return etree.XMLParser(
        resolve_entities=False, no_network=True, huge_tree=False, recover=False
    )


def _safe_int(digits):
    # Progress ids are small; a huge digit string is bogus and int() would raise
    # on Python's digit limit, so treat it as unknown.
    return int(digits) if len(digits) <= 9 else 0


def parse_chp(raw):
    """(volume, chapter) from an NU ``<chp>`` value; ``(0, 0)`` when unknown."""
    if not raw:
        return 0, 0
    value = raw.strip().lower()
    match = _CHP_RE.match(value)
    if match:
        return _safe_int(match.group(1) or "0"), _safe_int(match.group(2))
    match = _NUM_RE.match(value)
    if match:
        return 0, _safe_int(match.group(1))
    return 0, 0


def folder_name_for(list_name):
    """NU's list label as a library folder name ("Reading (Manual)" -> "Reading")."""
    name = (list_name or "").strip()
    return re.sub(r"\s*\((?:manual|auto)\)$", "", name, flags=re.IGNORECASE).strip()


def parse_nu_export(data):
    """Parse export bytes into ``[{list_name, title, volume, chapter}, ...]``.

    Raises ``ValueError`` with a user-facing message when the payload is too
    large, malformed, or not an NU reading-list export.
    """
    if not data:
        raise ValueError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("The uploaded file is too large (max 5 MB).")
    try:
        root = etree.fromstring(data, parser=_parser())
    except (etree.XMLSyntaxError, etree.ParserError) as exc:
        raise ValueError("This is not a valid XML file.") from exc

    if root is None or root.tag != "nu_readinglist":
        raise ValueError("This does not look like a NovelUpdates reading-list export.")

    entries = []
    for list_el in root.findall("list"):
        list_name = (list_el.text or "").strip()
        for series in list_el.findall("series"):
            title = (series.findtext("title") or "").strip()
            if not title:
                continue
            volume, chapter = parse_chp(series.findtext("chp"))
            entries.append(
                {
                    "list_name": list_name,
                    "title": title,
                    "volume": volume,
                    "chapter": chapter,
                }
            )

    if not entries:
        raise ValueError("No series were found in this export.")
    return entries


def _title_query(value):
    return (
        Q(title__icontains=value)
        | Q(sources__title__icontains=value)
        | Q(sources__alternative_titles__name__icontains=value)
    )


def _find_match(title):
    """Return ``(novel, candidates)`` for a title.

    ``novel`` is set on an exact (case-insensitive) title hit. Otherwise
    ``candidates`` holds up to 5 fuzzy matches for the user to pick from.
    """
    exact = list(
        Novel.objects.filter(
            Q(title__iexact=title)
            | Q(sources__title__iexact=title)
            | Q(sources__alternative_titles__name__iexact=title)
        )
        .distinct()
        .order_by("id")[:5]
    )
    if len(exact) == 1:
        return exact[0], []
    if exact:
        # Several novels share the title: let the user disambiguate.
        return None, exact

    candidates = list(
        Novel.objects.filter(_title_query(title)).distinct().order_by("id")[:5]
    )
    if not candidates:
        # Long titles like "... (LN)" rarely match verbatim; retry on the
        # longest significant token.
        tokens = _TOKEN_RE.findall(title)
        if tokens:
            token = max(tokens, key=len)
            candidates = list(
                Novel.objects.filter(_title_query(token)).distinct().order_by("id")[:5]
            )
    return None, candidates


def match_entries(entries):
    """Annotate parsed entries with ``status``, ``novel`` and ``candidates``."""
    for index, entry in enumerate(entries):
        entry["index"] = index
        novel, candidates = _find_match(entry["title"])
        if novel is not None:
            entry["status"] = "matched"
        elif candidates:
            entry["status"] = "ambiguous"
        else:
            entry["status"] = "unmatched"
        entry["novel"] = novel
        entry["candidates"] = candidates
    return entries
