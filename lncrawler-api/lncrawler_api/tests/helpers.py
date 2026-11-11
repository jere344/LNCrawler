"""Shared fixtures and helpers for the lncrawler_api test suite."""

import json
import os
import shutil
import tempfile
import uuid

from django.core.cache import cache

from django.test import TestCase, override_settings

from ..models import Chapter, ExternalSource, Novel, NovelFromSource
from ..models.sources_models import refresh_novel_adult
from ..services.chapter_stats import refresh_chapter_stats
from ..services.novel_naming import refresh_naming


def write_chapter(source_dir, number, body_size=3000):
    """Write a chapter JSON file big enough to count as real content."""
    json_dir = os.path.join(source_dir, "json")
    os.makedirs(json_dir, exist_ok=True)
    path = os.path.join(json_dir, f"{number:05}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {"title": f"Chapter {number}", "body": "word " * (body_size // 5)},
            handle,
        )
    return path


def make_novel(title, slug, novel_path=None, **source_fields):
    """A novel with one English source titled ``title``; that source names the novel.

    ``source_fields`` set other fields of that source (language, votes, ...). The novel's
    path defaults to its slug. Tests that count their own sources, or that need the adult or
    language majority to come from their own sources, use ``bare_novel`` instead.
    """
    novel = bare_novel(slug, novel_path)
    make_source(novel, title=title, **source_fields)
    return novel


def bare_novel(slug, novel_path=None):
    """A novel with no sources yet: the first ``make_source`` call names it."""
    return Novel.objects.create(slug=slug, novel_path=novel_path or slug)


def make_source(novel, language="en", external=None, **fields):
    """An English (or ``language``) source of ``novel``, on ``external`` or else on its own external site.

    ``fields`` override the defaults (title, source_url) and set any other source field. The
    novel's canonical source is refreshed afterwards, as the write paths do.
    """
    # Unique per call: a novel may get several sources from this helper, and tests create their own
    # ExternalSource rows with hand-picked names, so the defaults must never repeat.
    tag = uuid.uuid4().hex[:8]
    if external is None:
        external = ExternalSource.objects.create(source_name=f"src-{novel.slug}-{tag}")
    values = {"title": str(novel), "source_url": f"http://{novel.slug}-{tag}/1", **fields}
    source = NovelFromSource.objects.create(
        novel=novel, external_source=external, language=language, **values
    )
    refresh_naming(novel)
    return source


def set_adult(source, value=True):
    """Save the adult flag of ``source`` and re-derive its novel, as the write paths do."""
    source.is_adult = value
    source.save(update_fields=["is_adult"])
    refresh_novel_adult([source.novel_id])


class MergeTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-merge-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        self.output.enable()
        self.addCleanup(self.output.disable)

    def make_source(
        self,
        novel,
        external_source,
        title,
        url,
        novel_folder,
        source_folder,
        chapters=0,
    ):
        abs_dir = os.path.join(self.tmp, novel_folder, source_folder)
        os.makedirs(abs_dir, exist_ok=True)
        for number in range(1, chapters + 1):
            write_chapter(abs_dir, number)
        if novel.novel_path != novel_folder:
            novel.novel_path = novel_folder
            novel.save(update_fields=["novel_path"])
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=external_source,
            title=title,
            source_url=url,
            source_folder=source_folder,
            source_slug=source_folder,
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for number in range(1, chapters + 1):
            Chapter.objects.create(
                novel_from_source=source,
                chapter_id=number,
                url=f"{url}/ch{number}",
                title=f"Chapter {number}",
            )
        # Reload: the stored stats were written after the instance was created.
        refresh_chapter_stats([source.pk])
        source.refresh_from_db()
        refresh_naming(novel)
        return source


class LanguageAwareSourceTestCase(TestCase):
    """Shared fixtures: one novel with an English and a French source."""

    def setUp(self):
        cache.clear()
        self.novel = Novel.objects.create(slug="bilingue", novel_path="b")
        self.en_source = make_source(
            self.novel,
            external=ExternalSource.objects.create(source_name="en-site"),
            title="English",
            source_url="http://en/1",
            language="en",
            upvotes=0,
            downvotes=5,
        )
        self.fr_source = make_source(
            self.novel,
            external=ExternalSource.objects.create(source_name="fr-site"),
            title="Français",
            source_url="http://fr/1",
            language="fr",
            upvotes=3,
            downvotes=0,
        )

    def _novel_slugs(self, response):
        return [n["slug"] for n in response.data["top_novels"]]
