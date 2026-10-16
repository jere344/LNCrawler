"""Replace Chapter's unique_together + partial has_content index with one covering unique index.

The UniqueConstraint on (novel_from_source, chapter_id) INCLUDE (has_content)
serves the uniqueness check and the has_content lookups, so the separate
partial index chapter_source_chapter_idx (duplicate key columns) is dropped.

Ordering: the new constraint is added first so uniqueness is never unenforced,
then the old unique_together is cleared, then the redundant index is removed.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0080_widen_url_fields'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='chapter',
            constraint=models.UniqueConstraint(
                fields=('novel_from_source', 'chapter_id'),
                include=('has_content',),
                name='chapter_source_chapter_uniq',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='chapter',
            unique_together=set(),
        ),
        migrations.RemoveIndex(
            model_name='chapter',
            name='chapter_source_chapter_idx',
        ),
    ]
