from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0046_readinglist_is_public_readinglistcollaborator'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='novelfromsource',
            index=models.Index(fields=['-last_chapter_update'], name='nfs_last_chapter_upd_idx'),
        ),
        migrations.AddIndex(
            model_name='novelfromsource',
            index=models.Index(fields=['language'], name='nfs_language_idx'),
        ),
        migrations.AddIndex(
            model_name='novelfromsource',
            index=models.Index(fields=['-total_views'], name='nfs_total_views_idx'),
        ),
        migrations.AddIndex(
            model_name='novel',
            index=models.Index(fields=['-created_at'], name='novel_created_at_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['-created_at'], name='review_created_at_idx'),
        ),
        migrations.AddIndex(
            model_name='chapter',
            index=models.Index(
                fields=['novel_from_source', 'chapter_id'],
                name='chapter_source_chapter_idx',
                condition=models.Q(has_content=True),
            ),
        ),
    ]
