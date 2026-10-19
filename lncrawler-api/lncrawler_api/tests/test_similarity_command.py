"""Tests for the calculate_similarities management command."""

from io import StringIO

from django.core.management import call_command
from django.db.models import F
from django.test import TestCase

from ..management.commands.calculate_similarities import MIN_SIMILARITY
from ..models import Author, ExternalSource, Novel, NovelFromSource, NovelSimilarity, Tag


class CalculateSimilaritiesCommandTests(TestCase):
    def _novel(self, slug, title, tags=(), authors=()):
        novel = Novel.objects.create(title=title, slug=slug, novel_path=slug)
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"src-{slug}"),
            title=title,
            source_url=f"http://{slug}/1",
            language="en",
        )
        source.tags.set(tags)
        source.authors.set(authors)
        return novel

    def test_related_pair_links_each_other_and_weak_rows_are_dropped(self):
        fantasy = Tag.objects.create(name="Fantasy")
        romance = Tag.objects.create(name="Romance")
        mystery = Tag.objects.create(name="Mystery")
        jane = Author.objects.create(name="Jane Doe")
        john = Author.objects.create(name="John Smith")
        dragon = self._novel("dragon", "Dragon Academy", tags=[fantasy, romance], authors=[jane])
        sky = self._novel("sky", "Sky Kingdom", tags=[fantasy, romance], authors=[jane])
        ocean = self._novel("ocean", "Ocean Quest", tags=[mystery], authors=[john])

        call_command('calculate_similarities', stdout=StringIO())

        pairs = set(NovelSimilarity.objects.values_list('from_novel_id', 'to_novel_id'))
        self.assertIn((dragon.id, sky.id), pairs)
        self.assertIn((sky.id, dragon.id), pairs)
        self.assertFalse(NovelSimilarity.objects.filter(from_novel_id=F('to_novel_id')).exists())
        self.assertFalse(NovelSimilarity.objects.filter(similarity__lt=MIN_SIMILARITY).exists())
        self.assertFalse(NovelSimilarity.objects.filter(to_novel=ocean).exists())
