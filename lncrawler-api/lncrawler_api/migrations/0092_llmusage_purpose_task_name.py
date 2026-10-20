"""LLMUsage.purpose now stores the LLMTask name; map the old purpose values onto it."""
from django.db import migrations, models

RENAMES = {"novel": "novel_merge", "tag": "tag_merge"}


def forwards(apps, schema_editor):
    LLMUsage = apps.get_model("lncrawler_api", "LLMUsage")
    for old, new in RENAMES.items():
        LLMUsage.objects.filter(purpose=old).update(purpose=new)


def backwards(apps, schema_editor):
    LLMUsage = apps.get_model("lncrawler_api", "LLMUsage")
    for old, new in RENAMES.items():
        LLMUsage.objects.filter(purpose=new).update(purpose=old)
    # The author judge used to log under "novel"; any other new name would not fit max_length=10.
    LLMUsage.objects.filter(purpose="author_merge").update(purpose="novel")


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0091_placeholdercover'),
    ]

    operations = [
        migrations.AlterField(
            model_name='llmusage',
            name='purpose',
            field=models.CharField(max_length=50),
        ),
        migrations.RunPython(forwards, backwards),
    ]
