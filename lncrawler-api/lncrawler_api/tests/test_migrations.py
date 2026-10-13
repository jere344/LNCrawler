"""Tests for data migrations."""

from datetime import timedelta

from django.contrib.auth import get_user_model

from django.db import connection

from django.db.migrations.executor import MigrationExecutor

from django.test import TransactionTestCase

from django.utils import timezone

from ..models import ChatMessage, Comment


class BoardToChatMigrationTests(TransactionTestCase):
    """Exercise the 0056 data migration, which is skipped when the board tables are empty."""

    def test_board_comments_are_copied_to_chat_messages(self):
        migrate_from = [("lncrawler_api", "0055_job_retry_count")]
        migrate_to = [("lncrawler_api", "0057_remove_board")]

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)
        old_apps = executor.loader.project_state(migrate_from).apps
        Board = old_apps.get_model("lncrawler_api", "Board")
        Comment = old_apps.get_model("lncrawler_api", "Comment")

        user = get_user_model().objects.create_user(username="mig", password="pw")
        board = Board.objects.create(name="General", slug="general")
        parent_time = timezone.now() - timedelta(days=3)
        parent = Comment.objects.create(
            board=board,
            user_id=user.pk,
            author_name="mig",
            message="parent",
            contains_spoiler=True,
            ip_address="1.2.3.4",
            edited=True,
        )
        Comment.objects.filter(pk=parent.pk).update(created_at=parent_time)
        reply = Comment.objects.create(
            board=board,
            user_id=user.pk,
            author_name="mig",
            message="reply",
            parent_id=parent.pk,
        )
        reply_time = parent_time + timedelta(minutes=1)
        Comment.objects.filter(pk=reply.pk).update(created_at=reply_time)
        parent_pk, reply_pk = parent.pk, reply.pk

        try:
            executor = MigrationExecutor(connection)
            executor.migrate(migrate_to)
            new_apps = executor.loader.project_state(migrate_to).apps
            ChatMessage = new_apps.get_model("lncrawler_api", "ChatMessage")
            NewComment = new_apps.get_model("lncrawler_api", "Comment")

            self.assertEqual(ChatMessage.objects.count(), 2)
            self.assertFalse(
                NewComment.objects.filter(pk__in=[parent_pk, reply_pk]).exists()
            )

            copied_parent = ChatMessage.objects.get(pk=parent_pk)
            self.assertEqual(copied_parent.message, "parent")
            self.assertEqual(copied_parent.user_id, user.pk)
            self.assertEqual(copied_parent.author_name, "mig")
            self.assertTrue(copied_parent.contains_spoiler)
            self.assertEqual(copied_parent.ip_address, "1.2.3.4")
            self.assertTrue(copied_parent.edited)
            self.assertIsNone(copied_parent.parent_id)
            self.assertEqual(copied_parent.created_at, parent_time)

            copied_reply = ChatMessage.objects.get(pk=reply_pk)
            self.assertEqual(copied_reply.parent_id, parent_pk)
            self.assertEqual(copied_reply.created_at, reply_time)
        finally:
            # Restore the schema to the latest migration for subsequent tests.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class TagNormalizeMigrationTests(TransactionTestCase):
    """Exercise the 0070 backfill: keys are set and tags sharing a key collapse."""

    def test_duplicate_tags_collapse_onto_most_used(self):
        migrate_from = [("lncrawler_api", "0069_tag_normalized_and_merge_models")]
        migrate_to = [("lncrawler_api", "0070_normalize_and_collapse_tags")]

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)
        old_apps = executor.loader.project_state(migrate_from).apps
        Tag = old_apps.get_model("lncrawler_api", "Tag")
        TagAlias = old_apps.get_model("lncrawler_api", "TagAlias")
        Novel = old_apps.get_model("lncrawler_api", "Novel")
        ExternalSource = old_apps.get_model("lncrawler_api", "ExternalSource")
        NovelFromSource = old_apps.get_model("lncrawler_api", "NovelFromSource")
        Through = NovelFromSource.tags.through

        novel = Novel.objects.create(title="N", slug="n-mig")
        external = ExternalSource.objects.create(source_name="mig-src")
        sources = [
            NovelFromSource.objects.create(
                novel=novel, external_source=external, title="N", source_url=f"http://m/{i}"
            )
            for i in range(3)
        ]
        loser = Tag.objects.create(name="Isekai")  # lower id, but fewer sources
        winner = Tag.objects.create(name="ISEKAI")
        Through.objects.create(novelfromsource=sources[0], tag=loser)
        for source in sources:
            Through.objects.create(novelfromsource=source, tag=winner)
        TagAlias.objects.create(name="Old Isekai", tag=loser)
        winner_pk = winner.pk

        try:
            executor = MigrationExecutor(connection)
            executor.migrate(migrate_to)
            new_apps = executor.loader.project_state(migrate_to).apps
            NewTag = new_apps.get_model("lncrawler_api", "Tag")
            NewAlias = new_apps.get_model("lncrawler_api", "TagAlias")

            self.assertEqual(NewTag.objects.filter(normalized="isekai").count(), 1)
            survivor = NewTag.objects.get(normalized="isekai")
            self.assertEqual(survivor.pk, winner_pk)
            self.assertEqual(
                NewAlias.objects.get(name="Isekai").tag_id, winner_pk
            )
            self.assertEqual(
                NewAlias.objects.get(name="Old Isekai").tag_id, winner_pk
            )
            self.assertEqual(NewAlias.objects.get(name="Old Isekai").normalized, "old isekai")
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
