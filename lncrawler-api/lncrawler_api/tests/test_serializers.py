"""Tests for serializer profiles and query counts."""

from django.db import connection

from django.test import TestCase

from django.urls import reverse

from django.utils import timezone

from ..models import (
    ExternalSource,
    Novel,
    NovelFromSource,
    NovelRating,
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
        "featured": [
            "id", "title", "slug", "avg_rating", "rating_count", "total_views",
            "weekly_views", "prefered_source", "languages", "is_adult",
            "is_bookmarked", "comment_count", "reading_history", "reading_source",
            "is_dmca",
        ],
        "detail": [
            "id", "title", "slug", "sources", "created_at", "updated_at",
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
            "authors", "tags", "chapters_count", "last_chapter_update",
            "latest_available_chapter", "is_adult",
        ],
        "featured": [
            "id", "title", "source_slug", "novel_slug", "cover_min_url",
            "authors", "tags", "chapters_count", "last_chapter_update",
            "latest_available_chapter", "synopsis", "novel_id", "is_adult",
        ],
        "detail": [
            "id", "title", "source_url", "source_name", "source_slug", "authors",
            "tags", "language", "synopsis", "has_crawler", "cover_min_url",
            "chapters_count", "volumes_count", "volumes", "last_chapter_update",
            "upvotes", "downvotes", "vote_score", "user_vote", "novel_id",
            "novel_slug", "novel_title", "cover_url", "latest_available_chapter",
            "first_available_chapter", "reading_history", "overview_url",
            "novelupdates_url", "status", "editors", "translators",
            "alternative_titles", "original_publisher", "english_publisher",
            "is_adult",
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
                    "prev_chapter", "next_chapter", "images_path",
                    "source_overview_image_url",
                ],
            },
            ReadingHistorySerializer: {
                "card": ["id", "last_read_chapter", "last_read_at"],
                "detail": [
                    "id", "novel_slug", "source_slug", "last_read_chapter",
                    "last_read_at", "next_chapter", "source_latest_chapter",
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
