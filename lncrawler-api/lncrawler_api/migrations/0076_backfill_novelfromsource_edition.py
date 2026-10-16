"""Data step: backfill ``edition`` from the title markers of existing sources.

"Foo (WN)" -> "Web Novel". Rows whose title names no single edition keep "".

The marker logic is inlined on purpose: a migration must not depend on the
app code, which changes after it has run. It mirrors title_signals.edition_markers
and edition_label_from_title as they were when this migration was written.
Rows are grouped by label and updated in bulk, in chunks.
"""
import re
import unicodedata

from django.db import migrations

CHUNK_SIZE = 1000

_PAREN_RE = re.compile(r"[\(\[\{][^)\]\}]*[\)\]\}]")
_BRACKET_CONTENT_RE = re.compile(r"[\(\[\{]([^)\]\}]*)[\)\]\}]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPELLINGS = {
    "wn": ("wn", "web novel", "webnovel"),
    "ln": ("ln", "light novel", "lightnovel"),
    "raw": ("raw",),
}
_LABELS = {"wn": "Web Novel", "ln": "Light Novel", "raw": "Raw"}


def _fold(value):
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _words(value):
    return " ".join(_NON_WORD_RE.sub(" ", value).split())


def _markers(title):
    folded = _fold(title)
    candidates = [_words(part) for part in _BRACKET_CONTENT_RE.findall(folded)]
    tail = _words(_PAREN_RE.sub(" ", folded))
    found = set()
    for marker, spellings in _SPELLINGS.items():
        for spelling in spellings:
            if any(c == spelling for c in candidates) or tail.endswith(" " + spelling):
                found.add(marker)
    return found


def _label(title):
    markers = _markers(title)
    if len(markers) == 1:
        return _LABELS[next(iter(markers))]
    return ""


def backfill_edition_from_title(apps, schema_editor):
    NovelFromSource = apps.get_model('lncrawler_api', 'NovelFromSource')

    rows = list(NovelFromSource.objects.values_list('pk', 'title'))
    pks_by_label = {}
    for pk, title in rows:
        label = _label(title or '')
        if label:
            pks_by_label.setdefault(label, []).append(pk)

    for label, pks in pks_by_label.items():
        for start in range(0, len(pks), CHUNK_SIZE):
            NovelFromSource.objects.filter(
                pk__in=pks[start:start + CHUNK_SIZE]
            ).update(edition=label)


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0075_novelfromsource_edition'),
    ]

    operations = [
        migrations.RunPython(backfill_edition_from_title, migrations.RunPython.noop),
    ]
