from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0067_job_user_novel_added_by_novel_novel_added_by_idx'),
    ]

    operations = [
        migrations.DeleteModel(
            name='FeaturedNovel',
        ),
    ]
