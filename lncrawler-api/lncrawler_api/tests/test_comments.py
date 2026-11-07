"""Comment threads: the plain list response, ``ordering``, nested replies, replies
posted on a chapter, the comment summary of the chapter content payload, and
the write endpoints (add, vote, edit)."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from ..models import Chapter, ExternalSource, Novel, NovelFromSource
from ..models.comments_models import Comment
from ..utils import MAX_MESSAGE_LENGTH
from .helpers import make_novel, make_source


class CommentThreadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.novel = make_novel("Comments", "comments")
        self.source = make_source(self.novel)
        self.source.source_slug = "site"
        self.source.save(update_fields=["source_slug"])
        self.chapter = self.add_chapter(self.source, 1)

    def add_chapter(self, source, number):
        return Chapter.objects.create(
            novel_from_source=source, chapter_id=number, url=f"http://comments/{number}",
            title=f"Chapter {number}", has_content=True,
        )

    def add_source(self, novel, slug):
        return NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"{slug}-site"),
            title=novel.title, source_url=f"http://{slug}/1", source_slug=slug, language="en",
        )

    def chapter_comment(self, message, chapter=None, parent=None, **kwargs):
        chapter = chapter or self.chapter
        return Comment.objects.create(
            chapter=chapter, parent=parent, author_name="reader", message=message, **kwargs
        )

    def get_chapter_comments(self, **params):
        url = reverse("chapter_comments", kwargs={
            "novel_slug": "comments", "source_slug": "site", "chapter_number": 1,
        })
        return self.client.get(url, params)

    def add_reply_chain(self, label, depth=3):
        root = self.chapter_comment(f"{label} root")
        parent = root
        for level in range(1, depth + 1):
            parent = self.chapter_comment(f"{label} level {level}", parent=parent)
        return root

    def get_chapter_content(self):
        url = reverse("chapter_content_by_number", kwargs={
            "novel_slug": "comments", "source_slug": "site", "chapter_number": 1,
        })
        return self.client.get(url)

    def test_chapter_comments_returns_a_plain_list(self):
        comment = self.chapter_comment("Hello")
        response = self.get_chapter_comments()
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual([item["id"] for item in response.data], [str(comment.id)])

    def test_all_roots_are_returned_in_one_response(self):
        roots = [self.chapter_comment(f"Root {index}") for index in range(25)]
        response = self.get_chapter_comments()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 25)
        self.assertEqual(
            {item["id"] for item in response.data}, {str(root.id) for root in roots}
        )

    def test_oldest_root_keeps_its_reply_chain_among_many_roots(self):
        # The oldest of 25 roots sits behind 24 newer ones and still returns its
        # three-level reply chain in the same response.
        old_root = self.chapter_comment("Old root")
        level_1 = self.chapter_comment("Level 1", parent=old_root)
        level_2 = self.chapter_comment("Level 2", parent=level_1)
        level_3 = self.chapter_comment("Level 3", parent=level_2)
        for index in range(24):
            self.chapter_comment(f"Root {index}")

        response = self.get_chapter_comments()
        self.assertEqual(len(response.data), 25)
        oldest = next(item for item in response.data if item["id"] == str(old_root.id))
        reply = oldest["replies"][0]
        self.assertEqual(reply["id"], str(level_1.id))
        self.assertEqual(reply["replies"][0]["id"], str(level_2.id))
        self.assertEqual(reply["replies"][0]["replies"][0]["id"], str(level_3.id))
        self.assertEqual(reply["replies"][0]["replies"][0]["replies"], [])

    def test_replies_are_not_listed_as_roots(self):
        root = self.chapter_comment("Root")
        self.chapter_comment("Reply", parent=root)
        response = self.get_chapter_comments()
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(root.id))

    def test_ordering_top_puts_the_highest_score_first(self):
        # Created oldest first: score 5, then 9, then 5 again (newest).
        first = self.chapter_comment("first", upvotes=5, downvotes=0)
        second = self.chapter_comment("second", upvotes=9, downvotes=0)
        third = self.chapter_comment("third", upvotes=7, downvotes=2)

        top = self.get_chapter_comments(ordering="top").data
        self.assertEqual([c["id"] for c in top], [str(second.id), str(third.id), str(first.id)])

        default = self.get_chapter_comments().data
        self.assertEqual([c["id"] for c in default], [str(third.id), str(second.id), str(first.id)])
        self.assertEqual(
            [c["id"] for c in self.get_chapter_comments(ordering="new").data],
            [str(c["id"]) for c in default],
        )

    def test_novel_comments_ordering_top(self):
        first = Comment.objects.create(novel=self.novel, author_name="reader", message="first", upvotes=5)
        second = Comment.objects.create(novel=self.novel, author_name="reader", message="second", upvotes=9)
        third = Comment.objects.create(
            novel=self.novel, author_name="reader", message="third", upvotes=7, downvotes=2
        )
        url = reverse("novel_comments", kwargs={"novel_slug": "comments"})

        top = self.client.get(url, {"ordering": "top"}).data
        self.assertEqual([c["id"] for c in top], [str(second.id), str(third.id), str(first.id)])

        newest = self.client.get(url).data
        self.assertEqual([c["id"] for c in newest], [str(third.id), str(second.id), str(first.id)])

    def test_replies_are_nested_under_their_root(self):
        root = self.chapter_comment("Root")
        reply = self.chapter_comment("Reply", parent=root)
        nested = self.chapter_comment("Nested", parent=reply)

        results = self.get_chapter_comments().data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], str(root.id))
        self.assertEqual(len(results[0]["replies"]), 1)
        self.assertEqual(results[0]["replies"][0]["id"], str(reply.id))
        self.assertEqual(results[0]["replies"][0]["replies"][0]["id"], str(nested.id))

    def test_thread_query_count_does_not_grow_with_roots(self):
        # Each root carries a three-level reply chain. The reply levels are loaded
        # one query per level, so the count must not depend on the number of roots.
        def count_queries():
            with CaptureQueriesContext(connection) as context:
                response = self.get_chapter_comments()
            self.assertEqual(response.status_code, 200)
            return len(context.captured_queries)

        for index in range(5):
            self.add_reply_chain(f"Small {index}")
        with_five_roots = count_queries()

        for index in range(15):
            self.add_reply_chain(f"Large {index}")
        with_twenty_roots = count_queries()

        self.assertEqual(with_twenty_roots, with_five_roots)

    def test_reply_to_chapter_comment_is_created_with_chapter_labels(self):
        root = self.chapter_comment("Root")
        url = reverse("add_chapter_comment", kwargs={
            "novel_slug": "comments", "source_slug": "site", "chapter_number": 1,
        })
        response = self.client.post(
            url, {"parent_id": str(root.id), "message": "A reply", "author_name": "Replier"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["type"], "chapter")
        self.assertEqual(response.data["source_slug"], "site")
        self.assertEqual(response.data["chapter_display_title"], "Chapter 1")
        self.assertEqual(Comment.objects.get(pk=response.data["id"]).parent_id, root.id)

    def test_reply_on_chapter_route_to_another_chapter_is_not_found(self):
        other_chapter = self.add_chapter(self.source, 2)
        root = self.chapter_comment("On chapter two", chapter=other_chapter)
        url = reverse("add_chapter_comment", kwargs={
            "novel_slug": "comments", "source_slug": "site", "chapter_number": 1,
        })
        response = self.client.post(
            url, {"parent_id": str(root.id), "message": "Reply", "author_name": "Replier"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Comment.objects.filter(message="Reply").exists())

    def test_chapter_content_counts_replies_and_other_sources(self):
        other_source = self.add_source(self.novel, "other")
        other_chapter = self.add_chapter(other_source, 1)

        root = self.chapter_comment("Spoiler root", contains_spoiler=True, upvotes=9, downvotes=1)
        self.chapter_comment("Reply", parent=root, upvotes=20)
        self.chapter_comment("Other source", chapter=other_chapter, upvotes=3)

        # Same chapter number on another novel does not count.
        stranger = make_novel("Stranger", "stranger")
        stranger_source = make_source(stranger)
        self.chapter_comment("Elsewhere", chapter=self.add_chapter(stranger_source, 1))

        data = self.get_chapter_content().data
        self.assertEqual(data["comment_count"], 3)
        self.assertEqual(data["top_comment"]["id"], str(root.id))
        # A spoiler's text is withheld from the summary.
        self.assertIsNone(data["top_comment"]["message"])
        self.assertTrue(data["top_comment"]["contains_spoiler"])
        self.assertEqual(data["top_comment"]["vote_score"], 8)
        self.assertEqual(data["top_comment"]["author_name"], "reader")

    def test_top_comment_message_is_truncated(self):
        self.chapter_comment("x" * 200)
        data = self.get_chapter_content().data
        self.assertEqual(len(data["top_comment"]["message"]), 160)

    def test_chapter_content_without_comments(self):
        data = self.get_chapter_content().data
        self.assertEqual(data["comment_count"], 0)
        self.assertIsNone(data["top_comment"])

    def test_novel_comments_returns_a_plain_list(self):
        novel_comment = Comment.objects.create(
            novel=self.novel, author_name="reader", message="On the novel"
        )
        self.chapter_comment("On a chapter")
        url = reverse("novel_comments", kwargs={"novel_slug": "comments"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 2)
        self.assertIn(str(novel_comment.id), [item["id"] for item in response.data])


class CommentWriteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.novel = make_novel("Writes", "writes")
        self.owner = get_user_model().objects.create_user(username="owner", email="owner@example.com", password="x")
        self.other = get_user_model().objects.create_user(username="other", email="other@example.com", password="x")
        self.add_url = reverse("add_novel_comment", kwargs={"novel_slug": "writes"})

    def make_comment(self, message="Hello", novel=None, **kwargs):
        return Comment.objects.create(
            novel=novel or self.novel, author_name="reader", message=message, **kwargs
        )

    def test_add_comment_creates_a_novel_comment(self):
        response = self.client.post(
            self.add_url, {"message": "  Hello  ", "author_name": "Guest"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["message"], "Hello")
        self.assertEqual(response.data["type"], "novel")
        self.assertEqual(Novel.objects.get(pk=self.novel.pk).comment_count, 1)

    def test_add_comment_rejects_a_blank_message(self):
        response = self.client.post(
            self.add_url, {"message": "   ", "author_name": "Guest"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Comment.objects.exists())

    def test_add_comment_rejects_a_message_that_is_too_long(self):
        response = self.client.post(
            self.add_url,
            {"message": "x" * (MAX_MESSAGE_LENGTH + 1), "author_name": "Guest"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Comment.objects.exists())

    def test_guest_comment_needs_an_author_name(self):
        response = self.client.post(self.add_url, {"message": "Hello"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Author name", response.data["error"])

    def test_reply_with_a_malformed_parent_id_is_bad_request(self):
        response = self.client.post(
            self.add_url,
            {"message": "Hello", "author_name": "Guest", "parent_id": "not-a-uuid"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Comment.objects.exists())

    def test_reply_keeps_the_parent_on_the_same_novel(self):
        root = self.make_comment("Root")
        response = self.client.post(
            self.add_url,
            {"message": "Reply", "author_name": "Guest", "parent_id": str(root.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Comment.objects.get(pk=response.data["id"]).parent_id, root.id)

    def test_reply_to_a_comment_of_another_novel_is_not_found(self):
        other = make_novel("Elsewhere", "elsewhere")
        foreign = self.make_comment("Over there", novel=other)
        response = self.client.post(
            self.add_url,
            {"message": "Hello", "author_name": "Guest", "parent_id": str(foreign.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Comment.objects.filter(message="Hello").exists())

    def test_spoiler_string_false_is_not_a_spoiler(self):
        response = self.client.post(
            self.add_url,
            {"message": "Hello", "author_name": "Guest", "contains_spoiler": "false"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["contains_spoiler"])
        self.assertFalse(Comment.objects.get(pk=response.data["id"]).contains_spoiler)

    def vote_url(self, comment):
        return reverse("vote_comment", kwargs={"comment_id": comment.id})

    def test_vote_rejects_an_unknown_vote_type(self):
        comment = self.make_comment()
        response = self.client.post(self.vote_url(comment), {"vote_type": "sideways"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_switching_a_vote_moves_the_counts(self):
        comment = self.make_comment()

        up = self.client.post(self.vote_url(comment), {"vote_type": "up"}, format="json")
        self.assertEqual(
            (up.data["upvotes"], up.data["downvotes"], up.data["vote_score"]), (1, 0, 1)
        )

        down = self.client.post(self.vote_url(comment), {"vote_type": "down"}, format="json")
        self.assertEqual(
            (down.data["upvotes"], down.data["downvotes"], down.data["vote_score"]), (0, 1, -1)
        )

    def edit_url(self, comment):
        return reverse("edit_comment", kwargs={"comment_id": comment.id})

    def owned_comment(self):
        return Comment.objects.create(
            novel=self.novel, user=self.owner, author_name="owner", message="Original"
        )

    def test_edit_requires_login(self):
        comment = self.owned_comment()
        response = self.client.put(self.edit_url(comment), {"message": "Changed"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_edit_is_forbidden_to_other_users(self):
        comment = self.owned_comment()
        self.client.force_login(self.other)
        response = self.client.put(self.edit_url(comment), {"message": "Changed"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_edit_rejects_a_blank_message(self):
        comment = self.owned_comment()
        self.client.force_login(self.owner)
        response = self.client.put(self.edit_url(comment), {"message": "   "}, format="json")
        self.assertEqual(response.status_code, 400)
        comment.refresh_from_db()
        self.assertEqual(comment.message, "Original")
        self.assertFalse(comment.edited)

    def test_edit_updates_the_message_and_marks_it_edited(self):
        comment = self.owned_comment()
        self.client.force_login(self.owner)
        response = self.client.put(
            self.edit_url(comment), {"message": "  Changed  ", "contains_spoiler": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["edited"])
        comment.refresh_from_db()
        self.assertEqual(comment.message, "Changed")
        self.assertTrue(comment.edited)
        self.assertTrue(comment.contains_spoiler)

    def test_edit_response_leaves_out_the_replies(self):
        comment = self.owned_comment()
        Comment.objects.create(novel=self.novel, parent=comment, author_name="reader", message="Reply")
        self.client.force_login(self.owner)
        response = self.client.put(self.edit_url(comment), {"message": "Changed"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["replies"], [])
