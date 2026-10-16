import django.db.models.deletion
from django.db import migrations, models


def _preferred_source_id(NovelFromSource, novel_id):
    """
    Mirror of the serializer's get_prefered_source: highest (upvotes - downvotes),
    then upvotes, then title. Returns the source id to attach the novel's
    historical views to, or None when the novel has no sources.
    """
    sources = list(
        NovelFromSource.objects.filter(novel_id=novel_id).order_by('-upvotes', 'title')
    )
    if not sources:
        return None
    return max(sources, key=lambda s: (s.upvotes - s.downvotes, s.upvotes)).id


def migrate_views_to_sources(apps, schema_editor):
    NovelViewCount = apps.get_model("lncrawler_api", "NovelViewCount")
    WeeklyNovelView = apps.get_model("lncrawler_api", "WeeklyNovelView")
    NovelFromSource = apps.get_model("lncrawler_api", "NovelFromSource")
    WeeklySourceView = apps.get_model("lncrawler_api", "WeeklySourceView")

    # All-time totals become the projection column on the preferred source.
    for view_count in NovelViewCount.objects.all():
        source_id = _preferred_source_id(NovelFromSource, view_count.novel_id)
        if source_id is None:
            continue
        NovelFromSource.objects.filter(pk=source_id).update(
            total_views=view_count.views
        )

    # Weekly/day buckets are re-pointed from the novel to the same preferred
    # source. Buckets for one novel collapse onto a single source, so identical
    # (source, granularity, day) rows are summed.
    buckets = {}
    for bucket in WeeklyNovelView.objects.all():
        source_id = _preferred_source_id(NovelFromSource, bucket.novel_id)
        if source_id is None:
            continue
        key = (source_id, bucket.granularity, bucket.day)
        buckets[key] = buckets.get(key, 0) + bucket.views

    WeeklySourceView.objects.bulk_create(
        [
            WeeklySourceView(
                source_id=source_id,
                granularity=granularity,
                day=day,
                views=views,
            )
            for (source_id, granularity, day), views in buckets.items()
        ],
        batch_size=2000,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0043_weeklynovelview_daily_buckets'),
    ]

    operations = [
        migrations.AddField(
            model_name='novelfromsource',
            name='total_views',
            field=models.BigIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='WeeklySourceView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField()),
                ('granularity', models.CharField(choices=[('day', 'day'), ('week', 'week')], default='day', max_length=4)),
                ('views', models.PositiveIntegerField(default=0)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='weekly_views', to='lncrawler_api.novelfromsource')),
            ],
        ),
        # Data must move off the old tables before their columns/rows are dropped.
        migrations.RunPython(migrate_views_to_sources, noop),
        migrations.AlterUniqueTogether(
            name='weeklynovelview',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='weeklynovelview',
            name='novel',
        ),
        migrations.DeleteModel(
            name='NovelViewCount',
        ),
        migrations.DeleteModel(
            name='WeeklyNovelView',
        ),
        migrations.AddIndex(
            model_name='weeklysourceview',
            index=models.Index(fields=['granularity', 'day'], name='lncrawler_a_granula_0f0c26_idx'),
        ),
        migrations.AddIndex(
            model_name='weeklysourceview',
            index=models.Index(fields=['source', 'granularity', 'day'], name='lncrawler_a_source__9b1fe9_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='weeklysourceview',
            unique_together={('source', 'granularity', 'day')},
        ),
    ]
