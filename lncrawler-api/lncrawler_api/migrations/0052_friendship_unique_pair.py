from django.db import migrations, models
from django.db.models.functions import Least, Greatest


def dedupe_friendships(apps, schema_editor):
    Friendship = apps.get_model('lncrawler_api', 'Friendship')
    seen = {}
    # Prefer keeping an accepted row; otherwise the oldest, so the survivor is
    # deterministic. created_at is auto_now_add, so ordering by it is stable.
    rows = Friendship.objects.order_by('created_at')
    for f in rows:
        key = frozenset((f.requester_id, f.addressee_id))
        keeper = seen.get(key)
        if keeper is None:
            seen[key] = f
            continue
        if keeper.status != 'accepted' and f.status == 'accepted':
            keeper.delete()
            seen[key] = f
        else:
            f.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0051_backfill_bookmark_positions'),
    ]

    operations = [
        migrations.RunPython(dedupe_friendships, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='friendship',
            constraint=models.UniqueConstraint(
                Least('requester', 'addressee'),
                Greatest('requester', 'addressee'),
                name='friendship_unique_pair',
            ),
        ),
    ]
