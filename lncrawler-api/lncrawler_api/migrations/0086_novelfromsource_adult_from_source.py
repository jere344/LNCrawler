import json
import os

from django.conf import settings
from django.db import migrations, models


def restore_own_flag(apps, schema_editor):
    """Fill adult_from_source from each source's meta.json (the crawler's value)
    and re-derive is_adult = own flag OR an R18 tag.

    Before this field existed, R18 tags overwrote is_adult itself, so the
    current value cannot be trusted as the source's own flag. Tags only ever set
    it to True, so a source that is not adult now has no own flag either: only
    the adult ones need their meta.json read (meta.json lists every chapter, so
    reading all of them would keep the api down for a long time). A source
    without a readable meta.json keeps its current is_adult as its own flag. The
    same restore can be re-run with `manage.py recompute_adult --from-meta`.
    """
    NovelFromSource = apps.get_model("lncrawler_api", "NovelFromSource")
    root = os.path.realpath(settings.LNCRAWL_OUTPUT_PATH)
    own_adult = []
    for pk, source_path in NovelFromSource.objects.filter(is_adult=True).values_list(
        "pk", "source_path"
    ).iterator(chunk_size=500):
        own = True
        if source_path:
            path = os.path.realpath(os.path.join(root, source_path, "meta.json"))
            if path.startswith(root + os.sep) and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        own = bool(((json.load(f) or {}).get("novel") or {}).get("is_adult", False))
                except (OSError, ValueError):
                    pass
        if own:
            own_adult.append(pk)

    for start in range(0, len(own_adult), 1000):
        NovelFromSource.objects.filter(pk__in=own_adult[start:start + 1000]).update(
            adult_from_source=True
        )
    tagged = NovelFromSource.tags.through.objects.filter(tag__is_adult=True).values(
        "novelfromsource_id"
    )
    adult = models.Q(adult_from_source=True) | models.Q(pk__in=tagged)
    NovelFromSource.objects.filter(adult).update(is_adult=True)
    NovelFromSource.objects.exclude(adult).update(is_adult=False)


class Migration(migrations.Migration):
    """Store a source's own adult flag apart from the effective ``is_adult``,
    so unflagging an R18 tag can clear the sources it made adult, and record
    tag flags on merges so undo restores them."""

    dependencies = [
        ("lncrawler_api", "0085_delete_tagllmcall"),
    ]

    operations = [
        migrations.AddField(
            model_name="novelfromsource",
            name="adult_from_source",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tagmerge",
            name="source_was_adult",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tagmerge",
            name="target_was_adult",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.RunPython(restore_own_flag, migrations.RunPython.noop),
    ]
