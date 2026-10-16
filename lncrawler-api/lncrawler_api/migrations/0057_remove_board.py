from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0056_chatmessage_migrate_boards'),
    ]

    operations = [
        # Kept separate from the data migration: Postgres refuses to ALTER a
        # table that still has pending trigger events from the DELETE done in
        # 0056, so the schema change needs its own transaction.
        migrations.RemoveField(
            model_name='comment',
            name='board',
        ),
        migrations.DeleteModel(
            name='Board',
        ),
    ]
