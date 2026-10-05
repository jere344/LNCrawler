import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_board_comments_to_chat(apps, schema_editor):
    Comment = apps.get_model('lncrawler_api', 'Comment')
    ChatMessage = apps.get_model('lncrawler_api', 'ChatMessage')

    board_comments = list(Comment.objects.filter(board__isnull=False))
    if not board_comments:
        return

    originals = {comment.id: comment for comment in board_comments}
    chats = [
        ChatMessage(
            id=comment.id,
            user_id=comment.user_id,
            author_name=comment.author_name,
            message=comment.message,
            contains_spoiler=comment.contains_spoiler,
            ip_address=comment.ip_address,
            edited=comment.edited,
            parent_id=None,
        )
        for comment in board_comments
    ]

    # bulk_create overwrites auto_now_add timestamps; restore them (and reply
    # links) with a bulk_update once every row exists.
    ChatMessage.objects.bulk_create(chats)
    for chat in chats:
        original = originals[chat.id]
        chat.created_at = original.created_at
        chat.parent_id = original.parent_id
    ChatMessage.objects.bulk_update(chats, ['created_at', 'parent_id'])

    Comment.objects.filter(board__isnull=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('lncrawler_api', '0055_job_retry_count'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('author_name', models.CharField(max_length=100)),
                ('message', models.TextField()),
                ('contains_spoiler', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('edited', models.BooleanField(default=False)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='replies', to='lncrawler_api.chatmessage')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chat_messages', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['-created_at'], name='chatmessage_created_at_idx')],
            },
        ),
        # Irreversible: the forward run deletes the source board comments, so a
        # rollback would drop the ChatMessage copies without restoring them.
        # NOTE: Comment.board is removed in 0057, a separate migration, because
        # Postgres cannot ALTER the table in the same transaction as the DELETE
        # above ("pending trigger events").
        migrations.RunPython(migrate_board_comments_to_chat, migrations.RunPython.noop),
    ]
