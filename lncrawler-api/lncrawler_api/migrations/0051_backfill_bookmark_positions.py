from django.db import migrations


def backfill_positions(apps, schema_editor):
    NovelBookmark = apps.get_model('lncrawler_api', 'NovelBookmark')
    user_ids = (
        NovelBookmark.objects.order_by()
        .values_list('user_id', flat=True)
        .distinct()
    )
    for user_id in user_ids:
        bookmarks = NovelBookmark.objects.filter(user_id=user_id).order_by('created_at')
        for index, bookmark in enumerate(bookmarks):
            NovelBookmark.objects.filter(pk=bookmark.pk).update(position=index)


def reverse(apps, schema_editor):
    NovelBookmark = apps.get_model('lncrawler_api', 'NovelBookmark')
    NovelBookmark.objects.update(position=0)


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0050_libraryfolder_alter_novelbookmark_options_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_positions, reverse),
    ]
