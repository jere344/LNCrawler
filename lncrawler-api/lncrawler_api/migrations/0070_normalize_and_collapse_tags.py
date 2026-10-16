"""Backfill ``Tag.normalized``/``TagAlias.normalized`` and collapse duplicate tags.

Tags that share a comparison key (case, accent, plural or punctuation variants
of the same name) are folded into one survivor: the tag with the most novel
sources (lowest id on a tie). Sources are re-linked to the survivor, the
duplicate's aliases are repointed, and the duplicate's old name becomes an
alias so a future import of it still resolves.

The key logic is copied here on purpose: a migration must not import app code
that may change after it was written.
"""
import re
import unicodedata
from collections import defaultdict

from django.db import migrations
from django.db.models import Count

_NON_ALNUM_RE = re.compile(r"[\W_]+")


def _singular(word):
    if len(word) <= 3 or not word.isalpha():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def _normalize(name):
    name = name or ""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    key = " ".join(_singular(word) for word in _NON_ALNUM_RE.sub(" ", stripped).split())
    if not key:
        key = " ".join(name.casefold().split())
    return key[:100]


def backfill_and_collapse(apps, schema_editor):
    Tag = apps.get_model("lncrawler_api", "Tag")
    TagAlias = apps.get_model("lncrawler_api", "TagAlias")
    Through = apps.get_model("lncrawler_api", "NovelFromSource").tags.through

    aliases = list(TagAlias.objects.only("id", "name"))
    for alias in aliases:
        alias.normalized = _normalize(alias.name)
    TagAlias.objects.bulk_update(aliases, ["normalized"], batch_size=1000)

    tags = list(Tag.objects.only("id", "name"))
    tags_by_id = {tag.id: tag for tag in tags}
    for tag in tags:
        tag.normalized = _normalize(tag.name)
    Tag.objects.bulk_update(tags, ["normalized"], batch_size=1000)

    groups = defaultdict(list)
    for tag in tags:
        groups[tag.normalized].append(tag.id)
    duplicate_groups = {key: ids for key, ids in groups.items() if len(ids) > 1}
    if not duplicate_groups:
        return

    links = dict(
        Through.objects.order_by()
        .values("tag_id")
        .annotate(n=Count("id"))
        .values_list("tag_id", "n")
    )

    for key, ids in duplicate_groups.items():
        survivor_id = min(ids, key=lambda tag_id: (-links.get(tag_id, 0), tag_id))
        for dup_id in ids:
            if dup_id == survivor_id:
                continue
            dup = tags_by_id[dup_id]

            # Re-link the duplicate's sources onto the survivor, skipping the ones
            # that already carry it (the through table is unique per pair).
            dup_source_ids = list(
                Through.objects.filter(tag_id=dup_id).values_list("novelfromsource_id", flat=True)
            )
            already = set(
                Through.objects.filter(
                    tag_id=survivor_id, novelfromsource_id__in=dup_source_ids
                ).values_list("novelfromsource_id", flat=True)
            )
            Through.objects.bulk_create(
                [
                    Through(novelfromsource_id=source_id, tag_id=survivor_id)
                    for source_id in dup_source_ids
                    if source_id not in already
                ],
                batch_size=1000,
            )

            # Aliases follow the survivor; the duplicate's own name becomes one.
            TagAlias.objects.filter(tag_id=dup_id).update(tag_id=survivor_id)
            if not TagAlias.objects.filter(name=dup.name).exists():
                TagAlias.objects.create(name=dup.name, normalized=key, tag_id=survivor_id)

            Through.objects.filter(tag_id=dup_id).delete()
            Tag.objects.filter(pk=dup_id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0069_tag_normalized_and_merge_models'),
    ]

    operations = [
        migrations.RunPython(backfill_and_collapse, migrations.RunPython.noop),
    ]
