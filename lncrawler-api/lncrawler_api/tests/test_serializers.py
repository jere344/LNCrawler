"""Tests for serializer profiles and query counts."""

from django.db import connection

from django.test import TestCase

from django.urls import reverse

from django.utils import timezone

from ..models import (
    Chapter,
    ExternalSource,
    Novel,
    NovelFromSource,
    NovelRating,
    ReadingHistory,
    WeeklySourceView,
)


class SerializerProfileTests(TestCase):
    """One serializer per model, several profiles: each profile must emit the
    same fields the old per-view classes did, and excluded fields (and their
    queries) must never run."""

    NOVEL_FIELDS = {
        "card": [
            "id", "title", "slug", "avg_rating", "rating_count", "total_views",
            "weekly_views", "prefered_source", "languages", "is_adult",
            "is_bookmarked", "comment_count", "reading_history", "reading_source",
            "is_dmca",
        ],
        "detail": [
            "id", "title", "slug", "sources",
            "avg_rating", "rating_count", "user_rating", "total_views",
            "weekly_views", "prefered_source", "is_adult", "is_bookmarked",
            "comment_count", "reading_history", "reading_source", "similar_novels",
            "reading_lists", "is_dmca",
        ],
        "library": [
            "id", "title", "slug", "avg_rating", "rating_count", "total_views",
            "weekly_views", "prefered_source", "languages", "is_adult",
            "is_bookmarked", "comment_count", "reading_history", "reading_source",
            "is_dmca", "bookmark_id", "note", "folder", "folder_name", "position",
            "user_rating",
        ],
    }

    SOURCE_FIELDS = {
        "card": [
            "id", "title", "source_slug", "novel_slug", "novel_id", "cover_min_url",
            "authors", "tags", "chapters_count", "available_chapters_count",
            "last_chapter_update", "latest_available_chapter", "is_adult",
        ],
        "detail": [
            "id", "title", "source_url", "source_name", "source_slug", "authors",
            "tags", "language", "synopsis", "has_crawler",
            "chapters_count", "available_chapters_count", "volumes",
            "last_chapter_update",
            "upvotes", "downvotes", "vote_score", "user_vote", "novel_id",
            "novel_slug", "novel_title", "cover_url", "latest_available_chapter",
            "first_available_chapter", "reading_history", "overview_url",
            "novelupdates_url", "status", "editors", "translators",
            "alternative_titles", "original_publisher", "english_publisher",
            "is_adult",
        ],
        "summary": [
            "id", "source_slug", "novel_slug", "source_name", "cover_min_url",
            "language", "chapters_count", "available_chapters_count",
            "latest_available_chapter",
            "last_chapter_update", "vote_score", "user_vote",
        ],
    }

    def test_novel_profiles_match_legacy_field_sets(self):
        from ..serializers import NovelSerializer

        for profile, expected in self.NOVEL_FIELDS.items():
            self.assertEqual(
                list(NovelSerializer(profile=profile).fields), expected, profile
            )

    def test_source_profiles_match_legacy_field_sets(self):
        from ..serializers import NovelSourceSerializer

        for profile, expected in self.SOURCE_FIELDS.items():
            self.assertEqual(
                list(NovelSourceSerializer(profile=profile).fields), expected, profile
            )

    def test_other_serializer_profiles_match_expected_field_sets(self):
        """Every merged serializer exposes the same fields its split classes
        used to, through a named profile."""
        from ..serializers import (
            ChapterSerializer,
            CommentSerializer,
            ReadingHistorySerializer,
            ReadingListSerializer,
            ReviewSerializer,
            UserSerializer,
        )

        base_comment = [
            "id", "author_name", "message", "contains_spoiler", "created_at",
            "upvotes", "downvotes", "vote_score", "user", "replies",
            "has_replies", "user_vote",
        ]
        cases = {
            ChapterSerializer: {
                "card": [
                    "id", "chapter_id", "title", "url", "volume", "volume_title",
                    "has_content",
                ],
                "content": [
                    "id", "chapter_id", "title", "novel_title", "novel_id",
                    "novel_slug", "source_id", "source_name", "source_slug", "body",
                    "prev_chapter", "next_chapter", "prev_chapter_id",
                    "next_chapter_id", "images_path",
                    "source_overview_image_url",
                ],
                "unavailable": [
                    "chapter_id", "title", "novel_title", "prev_chapter",
                    "next_chapter",
                ],
            },
            ReadingHistorySerializer: {
                "card": ["id", "last_read_chapter", "last_read_at"],
                "detail": [
                    "id", "novel_slug", "source_slug", "last_read_chapter",
                    "last_read_at", "next_chapter", "unread_chapters",
                    "source_latest_chapter",
                ],
            },
            ReadingListSerializer: {
                "card": [
                    "id", "title", "description", "is_public", "user", "user_role",
                    "collaborators", "items_count", "created_at", "updated_at",
                    "first_item", "items_names",
                ],
                "detail": [
                    "id", "title", "description", "is_public", "user", "user_role",
                    "collaborators", "items", "created_at", "updated_at",
                ],
            },
            CommentSerializer: {
                "novel": base_comment + ["type", "edited"],
                "chapter": base_comment + [
                    "type", "chapter_title", "chapter_id", "source_name",
                    "source_slug", "edited",
                ],
                "profile": base_comment + [
                    "target_type", "target_title", "target_slug",
                    "target_novel_slug", "target_source_slug",
                    "target_chapter_number",
                ],
            },
            ReviewSerializer: {
                "card": [
                    "id", "novel_title", "novel_slug", "user", "title", "content",
                    "rating", "created_at",
                ],
                "detail": [
                    "id", "novel_title", "novel_slug", "user", "title", "content",
                    "rating", "created_at", "updated_at", "reaction_count",
                    "reactions", "current_user_reaction",
                ],
            },
            UserSerializer: {
                "me": [
                    "id", "username", "email", "profile_pic", "banner", "bio",
                    "social_links", "privacy_settings", "date_joined", "last_login",
                    "word_read", "chapters_read_count", "chapters_not_read_yet_count",
                    "preferred_ui_language", "preferred_languages",
                    "language_filter_enabled", "discoverable", "show_r18", "pinned_novels",
                ],
                "compact": ["id", "username", "profile_pic"],
                "public": [
                    "id", "username", "profile_pic", "banner", "bio", "date_joined",
                    "social_links", "friendship_status", "friend_count", "visibility",
                    "pinned_novels", "stats", "currently_reading", "top_genres",
                    "recent_reads",
                ],
            },
        }

        for serializer_class, profiles in cases.items():
            for profile, expected in profiles.items():
                self.assertEqual(
                    list(serializer_class(profile=profile).fields),
                    expected,
                    f"{serializer_class.__name__}:{profile}",
                )

    def test_unknown_profile_is_rejected(self):
        from ..serializers import NovelSerializer

        with self.assertRaises(ValueError):
            NovelSerializer(profile="nope")

    def test_chapter_neighbour_ids_expose_unavailable_gap(self):
        """With chapters [6 available, 7 unavailable, 8 available], the content
        payload reports the *immediate* neighbour (7) separately from the next
        *available* chapter (8), so the reader can detect the gap."""
        from ..serializers import ChapterSerializer

        novel = self._make_novel(1)
        source = novel.sources.first()
        for chapter_id, has_content in [(6, True), (7, False), (8, True)]:
            Chapter.objects.create(
                novel_from_source=source,
                chapter_id=chapter_id,
                url=f"http://site/1/{chapter_id}",
                title=f"Chapter {chapter_id}",
                has_content=has_content,
            )

        chapter_6 = ChapterSerializer(
            source.chapters.get(chapter_id=6), profile="content"
        ).data
        self.assertEqual(chapter_6["next_chapter"], 8)
        self.assertEqual(chapter_6["next_chapter_id"], 7)

        unavailable = ChapterSerializer(
            source.chapters.get(chapter_id=7), profile="unavailable"
        ).data
        self.assertEqual(unavailable["prev_chapter"], 6)
        self.assertEqual(unavailable["next_chapter"], 8)

    def test_library_user_rating_reads_bookmark_without_query(self):
        """The library profile's ``user_rating`` is the pre-annotated owner
        rating on the attached bookmark; it must never hit the ratings table
        (one query per bookmark otherwise)."""
        from types import SimpleNamespace

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from ..serializers import NovelSerializer

        novel = self._make_novel(1)
        novel.library_bookmark = SimpleNamespace(owner_rating=5)

        shown = NovelSerializer(
            novel, profile="library",
            context={"request": None, "show_ratings": True},
        )
        with CaptureQueriesContext(connection) as captured:
            self.assertEqual(shown.get_user_rating(novel), 5)
        self.assertEqual(len(captured), 0)

        hidden = NovelSerializer(
            novel, profile="library",
            context={"request": None, "show_ratings": False},
        )
        self.assertIsNone(hidden.get_user_rating(novel))

    def _make_novel(self, index):
        novel = Novel.objects.create(
            title=f"Novel {index}", slug=f"novel-{index}", novel_path=f"n{index}"
        )
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"site-{index}"),
            title=f"Source {index}",
            source_url=f"http://site/{index}",
            source_slug=f"site-{index}",
            language="en",
            synopsis="A long synopsis",
        )
        NovelRating.objects.create(novel=novel, ip_address="1.1.1.1", rating=4)
        WeeklySourceView.objects.create(source=source, day=timezone.localdate(), views=3)
        return novel

    def _list_queries(self, queryset):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from ..serializers import NovelSerializer

        with CaptureQueriesContext(connection) as captured:
            NovelSerializer(queryset, many=True, context={"request": None}).data
        return len(captured)

    def test_list_profile_query_count_is_flat(self):
        """Serializing 2 vs 4 novels must cost the same: any growth is an N+1."""
        from ..utils.query_helpers import apply_novel_prefetches

        for index in range(4):
            self._make_novel(index)
        queryset = apply_novel_prefetches(Novel.objects.all().order_by("title"), None)
        self.assertEqual(
            self._list_queries(queryset[:2]),
            self._list_queries(queryset[:4]),
        )

    def test_unread_chapters_reads_prefetched_annotation(self):
        """A prefetched history must answer ``unread_chapters`` from the
        annotation, not one COUNT per row (the N+1 the prefetch removes).
        Note ``next_chapter``/``source_latest_chapter`` remain per-row."""
        from django.contrib.auth import get_user_model
        from django.test.utils import CaptureQueriesContext

        from ..serializers import ReadingHistorySerializer
        from ..utils.query_helpers import apply_novel_prefetches

        user = get_user_model().objects.create_user(username="reader", password="x")
        novel = self._make_novel(1)
        source = novel.sources.first()
        read = Chapter.objects.create(
            novel_from_source=source, chapter_id=1,
            url="http://site/1", title="C1",
        )
        for chapter_id in (2, 3):
            Chapter.objects.create(
                novel_from_source=source, chapter_id=chapter_id,
                url=f"http://site/{chapter_id}", title=f"C{chapter_id}",
                has_content=True,
            )
        ReadingHistory.objects.create(
            user=user, novel=novel, source=source, last_read_chapter=read,
        )

        prefetched = apply_novel_prefetches(
            Novel.objects.filter(pk=novel.pk), user
        ).get()
        history = prefetched.user_histories[0]

        with CaptureQueriesContext(connection) as captured:
            value = ReadingHistorySerializer().get_unread_chapters(history)
        self.assertEqual(value, 2)
        self.assertEqual(len(captured), 0)

    def test_card_profile_serializes_without_extra_queries(self):
        """With the card fields annotated, serializing a source card must not
        touch the chapter/volume tables (the old detail-only fallbacks)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from ..serializers import NovelSourceSerializer
        from ..utils.query_helpers import sources_queryset

        self._make_novel(1)
        source = sources_queryset(detailed=False).first()
        with CaptureQueriesContext(connection) as captured:
            NovelSourceSerializer(source, profile="card").data
        self.assertEqual(len(captured), 0)

    def test_available_chapters_count_only_counts_content(self):
        """``available_chapters_count`` must exclude chapters without content
        while ``chapters_count`` keeps the total (the source page shows 25/500),
        both from the annotation and the per-object fallback."""
        from ..serializers import NovelSourceSerializer
        from ..utils.query_helpers import sources_queryset

        source = self._make_novel(1).sources.first()
        for chapter_id, has_content in ((1, True), (2, False), (3, True)):
            Chapter.objects.create(
                novel_from_source=source, chapter_id=chapter_id,
                url=f"http://site/{chapter_id}", title=f"C{chapter_id}",
                has_content=has_content,
            )

        plain = NovelSourceSerializer(source, profile="card").data
        self.assertEqual(plain["chapters_count"], 3)
        self.assertEqual(plain["available_chapters_count"], 2)

        annotated = NovelSourceSerializer(
            sources_queryset(detailed=False).get(pk=source.pk), profile="card"
        ).data
        self.assertEqual(annotated["chapters_count"], 3)
        self.assertEqual(annotated["available_chapters_count"], 2)

    def test_novel_detail_endpoint_serializes_nested_sources(self):
        novel = self._make_novel(1)
        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": novel.slug})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["sources"]), 1)

    def test_similar_novels_fallback_prefers_source_backed_novels(self):
        # A source-less novel's summed views are NULL, which sorts first on a
        # Postgres DESC, so it used to be recommended ahead of real novels and
        # rendered as a broken card (no prefered_source -> no cover).
        from ..serializers import NovelSerializer

        target = Novel.objects.create(title="Target", slug="target", novel_path="t")
        for index in range(3):
            self._make_novel(index).sources.update(total_views=10)
        Novel.objects.create(title="No Source", slug="no-source", novel_path="ns")

        data = NovelSerializer(target, profile="detail", context={"request": None}).data
        titles = [item["title"] for item in data["similar_novels"]]
        self.assertEqual(titles[-1], "No Source")
        self.assertTrue(
            all(item["prefered_source"] for item in data["similar_novels"][:3])
        )

    def test_source_detail_endpoint_serves_full_detail_profile(self):
        self._make_novel(1)
        response = self.client.get(
            reverse("source_detail", kwargs={"novel_slug": "novel-1", "source_slug": "site-1"})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["synopsis"], "A long synopsis")
        self.assertIn("first_available_chapter", response.data)

    def test_source_detail_embeds_novel_detail(self):
        """The source response carries the novel detail (with lightweight
        summary sources) so the page no longer needs a second request."""
        self._make_novel(1)
        response = self.client.get(
            reverse("source_detail", kwargs={"novel_slug": "novel-1", "source_slug": "site-1"})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["novel"]["slug"], "novel-1")
        self.assertEqual(len(response.data["novel"]["sources"]), 1)
        self.assertNotIn("synopsis", response.data["novel"]["sources"][0])

    def test_novel_detail_nested_sources_keep_viewer_vote(self):
        """The summary profile reports the viewer's own vote, so a regression
        in get_user_vote's profile guard silently drops the highlight."""
        from ..models import SourceVote

        novel = self._make_novel(1)
        SourceVote.objects.create(
            source=novel.sources.first(), ip_address="127.0.0.1", vote_type="up"
        )
        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": novel.slug})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sources"][0]["user_vote"], "up")

    def test_summary_sources_serialize_without_per_source_queries(self):
        """Serializing more summary sources must cost the same: any growth is
        an N+1 the summary prefetch failed to collapse."""
        from django.test.utils import CaptureQueriesContext

        from ..serializers import NovelSourceSerializer
        from ..utils.query_helpers import sources_queryset

        novel = self._make_novel(0)
        for index in range(3):
            NovelFromSource.objects.create(
                novel=novel,
                external_source=ExternalSource.objects.create(
                    source_name=f"extra-{index}"
                ),
                title=f"Extra {index}",
                source_url=f"http://extra/{index}",
                source_slug=f"extra-{index}",
                language="en",
            )
        queryset = sources_queryset(summary=True, ip="127.0.0.1").filter(novel=novel)

        # The summary profile's user_vote must come from the prefetch, not a
        # per-source query. With a bare request context a dropped prefetch
        # would silently fall back to a query per source, so assert the to_attr
        # is warm rather than trusting the flat count alone.
        self.assertTrue(all(hasattr(s, "user_votes") for s in queryset))

        def count(number):
            with CaptureQueriesContext(connection) as captured:
                NovelSourceSerializer(
                    queryset[:number], many=True, context={"request": None},
                    profile="summary",
                ).data
            return len(captured)

        self.assertEqual(count(2), count(4))

    def test_prefered_source_breaks_vote_ties_by_content_chapters(self):
        """Two equally-voted sources: the one with more chapters that actually
        have content wins, so the card isn't pointed at an empty source."""
        from ..serializers import NovelSerializer

        novel = Novel.objects.create(title="Tie", slug="tie", novel_path="tie")
        weak = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="weak"),
            title="Weak", source_url="http://weak/1", source_slug="weak",
            language="en", upvotes=2, downvotes=0,
        )
        strong = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="strong"),
            title="Strong", source_url="http://strong/1", source_slug="strong",
            language="en", upvotes=2, downvotes=0,
        )
        for chapter_id, has_content in ((1, True), (2, False)):
            Chapter.objects.create(
                novel_from_source=weak, chapter_id=chapter_id,
                url=f"http://weak/{chapter_id}", title=f"c{chapter_id}",
                has_content=has_content,
            )
        for chapter_id in range(1, 4):
            Chapter.objects.create(
                novel_from_source=strong, chapter_id=chapter_id,
                url=f"http://strong/{chapter_id}", title=f"c{chapter_id}",
                has_content=True,
            )

        data = NovelSerializer(novel, context={"request": None}).data
        self.assertEqual(data["prefered_source"]["source_slug"], "strong")

    def test_unread_chapters_counts_only_content_after_last_read(self):
        from django.contrib.auth import get_user_model

        from ..serializers import ReadingHistorySerializer

        novel = self._make_novel(1)
        source = novel.sources.first()
        chapters = {}
        for chapter_id, has_content in ((1, True), (2, False), (3, True), (4, False)):
            chapters[chapter_id] = Chapter.objects.create(
                novel_from_source=source, chapter_id=chapter_id,
                url=f"http://site/{chapter_id}", title=f"C{chapter_id}",
                has_content=has_content,
            )
        user = get_user_model().objects.create_user(username="reader", password="x")
        history = ReadingHistory.objects.create(
            user=user, novel=novel, source=source, last_read_chapter=chapters[1],
        )

        data = ReadingHistorySerializer(history, profile="detail").data
        # Only chapter 3 has content after chapter 1 (2 and 4 are gaps).
        self.assertEqual(data["unread_chapters"], 1)

    def test_unread_chapters_is_none_without_last_read_chapter(self):
        from django.contrib.auth import get_user_model

        from ..serializers import ReadingHistorySerializer

        novel = self._make_novel(1)
        user = get_user_model().objects.create_user(username="reader2", password="x")
        history = ReadingHistory.objects.create(
            user=user, novel=novel, source=novel.sources.first(),
        )

        data = ReadingHistorySerializer(history, profile="detail").data
        self.assertIsNone(data["unread_chapters"])
