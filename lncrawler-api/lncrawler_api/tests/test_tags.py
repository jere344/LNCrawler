"""Tests for tag autocomplete, similarity and merging."""

from django.test import TestCase

from django.urls import reverse

from ..models import ExternalSource, Novel, NovelFromSource, Tag, TagAlias

from ..services import merge_similar_tags


class TagAutocompleteAliasTests(TestCase):
    """A merged-away tag name must still surface its canonical tag."""

    def setUp(self):
        self.novel = Novel.objects.create(title="Isekai Tale", slug="it", novel_path="it")
        self.canonical = Tag.objects.create(name="Isekai")
        source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="tag-site"),
            title="Isekai Tale",
            source_url="http://tag/1",
        )
        source.tags.add(self.canonical)
        TagAlias.objects.create(name="isekai", tag=self.canonical)

    def _suggest(self, query):
        response = self.client.get(
            reverse("autocomplete_suggestion"), {"type": "tag", "query": query}
        )
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_alias_query_returns_canonical_tag(self):
        suggestions = self._suggest("isekai")
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["name"], "Isekai")
        self.assertEqual(suggestions[0]["alias"], "isekai")
        self.assertEqual(suggestions[0]["count"], 1)

    def test_canonical_and_alias_merge_into_one_entry(self):
        # "Isekai" (canonical) and "isekai" (alias) both match case-insensitively.
        self.assertEqual(len(self._suggest("sekai")), 1)


class TagSimilarityTests(TestCase):
    """The auto-merge heuristic must catch obvious variants, not real tags."""

    def _sim(self, a, b):
        from ..services.merge_service import _tag_similarity

        return _tag_similarity(a, b)

    def test_case_only_difference_is_similar(self):
        self.assertGreaterEqual(self._sim("Isekai", "isekai"), 0.9)

    def test_plural_and_singular_are_similar(self):
        self.assertGreaterEqual(self._sim("action", "actions"), 0.9)

    def test_distinct_tags_are_not_similar(self):
        self.assertLess(self._sim("action", "romance"), 0.9)
        self.assertLess(self._sim("Isekai", "Isekaijoucho"), 0.9)

    def test_shared_prefix_words_are_not_similar(self):
        # Near but distinct sub-genres must survive.
        self.assertLess(self._sim("Science Fiction", "Science Fantasy"), 0.9)

    def test_direction_swapped_words_are_not_similar(self):
        # The classic false positives: one word changed, opposite meaning.
        self.assertLess(self._sim("Western Fantasy", "Eastern Fantasy"), 0.9)
        self.assertLess(self._sim("Female Protagonist", "Male Protagonist"), 0.9)
        self.assertLess(self._sim("Adapted to Manhua", "Adapted to Manhwa"), 0.9)

    def test_accents_fold(self):
        self.assertGreaterEqual(self._sim("Réincarnation", "reincarnation"), 0.9)


class MergeSimilarTagsTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="s"),
            title="N",
            source_url="http://s/1",
        )

    def _tag(self, name, count=0):
        tag = Tag.objects.create(name=name)
        for _ in range(count):
            self.source.tags.add(tag)
        return tag

    def test_auto_merge_keeps_most_used_spelling(self):
        # "isekai" carries the data, so it wins over the uppercase spare.
        canonical = self._tag("isekai", count=1)
        self._tag("Isekai")

        results = merge_similar_tags()

        self.assertEqual(len(results), 1)
        self.assertEqual(Tag.objects.get(name="isekai"), canonical)
        self.assertFalse(Tag.objects.filter(name="Isekai").exists())
        self.assertEqual(TagAlias.objects.get(name="Isekai").tag, canonical)
        self.assertEqual(self.source.tags.count(), 1)

    def test_distinct_tags_are_left_alone(self):
        self._tag("Action")
        self._tag("Romance")
        self.assertEqual(merge_similar_tags(), [])
        self.assertEqual(Tag.objects.count(), 2)

    def test_dry_run_changes_nothing(self):
        self._tag("action", count=1)
        self._tag("actions")

        results = merge_similar_tags(dry_run=True)

        self.assertEqual(results, [("action", ["actions"])])
        self.assertEqual(Tag.objects.count(), 2)

    def test_aliased_name_resolves_on_reimport(self):
        # After auto-merge, importing the old spelling must not recreate it.
        self._tag("Isekai", count=1)
        self._tag("isekai")
        merge_similar_tags()

        self.assertEqual(Tag.resolve("isekai"), Tag.objects.get(name="Isekai"))
        self.assertFalse(Tag.objects.filter(name="isekai").exists())
