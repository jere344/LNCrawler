"""Stored paths are names relative to their parent.

The properties return the full paths the API always returned. A rename of the novel folder changes
``Novel.novel_path`` only; a source move changes ``novel`` and ``source_folder`` only.
"""

import os
import shutil
import tempfile
from urllib.parse import quote

from django.conf import settings
from django.test import TestCase, override_settings

from ..models import Audiobook, AudiobookChapter, AudiobookPart, Chapter, NovelFromSource
from ..models.source_helpers import resolve_output_path
from ..services.novel_operations import file_journal, move_source_to_novel
from ..utils.media_utils import build_media_url
from .helpers import bare_novel, make_source


class PathTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-source-paths-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        output.enable()
        self.addCleanup(output.disable)

    def write(self, *parts):
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"x")
        return path


class SourcePathPropertyTests(PathTestCase):
    def test_properties_return_the_full_paths(self):
        novel = bare_novel("lotm", "lotm")
        source = make_source(
            novel,
            source_folder="site",
            cover_file="cover.jpg",
            cover_min_file="cover.min.webp",
            overview_picture_file="overview.jpg",
        )
        source = NovelFromSource.objects.get(pk=source.pk)  # as stored

        self.assertEqual(source.source_path, os.path.join("lotm", "site"))
        self.assertEqual(source.cover_path, os.path.join("lotm", "site", "cover.jpg"))
        self.assertEqual(source.cover_min_path, os.path.join("lotm", "site", "cover.min.webp"))
        self.assertEqual(source.overview_picture_path, os.path.join("lotm", "site", "overview.jpg"))
        self.assertEqual(source.absolute_source_path, resolve_output_path("lotm", "site"))

    def test_media_urls_are_the_same_as_before(self):
        novel = bare_novel("lotm", "lotm")
        source = make_source(novel, source_folder="site", cover_file="cover.jpg")

        self.assertEqual(
            build_media_url(source.cover_path),
            quote(f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}lotm/site/cover.jpg", safe=":/"),
        )

    def test_missing_folder_or_file_gives_none(self):
        novel = bare_novel("lotm", "lotm")
        source = make_source(novel, source_folder=None, cover_file=None)

        self.assertIsNone(source.source_path)
        self.assertIsNone(source.cover_path)
        self.assertIsNone(source.cover_min_path)
        self.assertIsNone(source.overview_picture_path)
        self.assertIsNone(source.absolute_source_path)

    def test_audiobook_paths_are_relative_to_the_source_folder(self):
        novel = bare_novel("lotm", "lotm")
        source = make_source(novel, source_folder="site")
        audiobook = Audiobook.objects.create(novel=novel, source=source, cover_file="audio/cover.jpg")
        chapter = Chapter.objects.create(novel_from_source=source, chapter_id=7, url="http://x/7", title="C7")
        part = AudiobookPart.objects.create(
            audiobook=audiobook, index=1, chapter_start=7, chapter_end=7, status="done",
        )
        row = AudiobookChapter.objects.create(
            part=part, chapter=chapter, file_in_source="audio/part-001/g1/00007.ogg",
            duration_s=1, size_bytes=1, sha256="0" * 64,
        )
        audiobook = Audiobook.objects.get(pk=audiobook.pk)
        row = AudiobookChapter.objects.get(pk=row.pk)

        self.assertEqual(audiobook.cover_path, os.path.join("lotm", "site", "audio", "cover.jpg"))
        self.assertEqual(row.file_path, os.path.join("lotm", "site", "audio", "part-001", "g1", "00007.ogg"))
        self.assertEqual(
            part.upload_path({"file_in_source": "audio/part-001/g1/00007.ogg"}),
            os.path.join("lotm", "site", "audio", "part-001", "g1", "00007.ogg"),
        )

    def test_audiobook_without_cover_has_an_empty_path(self):
        novel = bare_novel("lotm", "lotm")
        source = make_source(novel, source_folder="site")
        audiobook = Audiobook.objects.create(novel=novel, source=source)

        self.assertEqual(audiobook.cover_path, "")


class RenameAndMoveTests(PathTestCase):
    def test_renaming_the_novel_folder_moves_every_computed_path(self):
        novel = bare_novel("lotm", "lotm")
        source = make_source(
            novel, source_folder="site", cover_file="cover.jpg",
            cover_min_file="cover.min.webp", overview_picture_file="overview.jpg",
        )
        audiobook = Audiobook.objects.create(novel=novel, source=source, cover_file="audio/cover.jpg")
        chapter = Chapter.objects.create(novel_from_source=source, chapter_id=1, url="http://x/1", title="C1")
        part = AudiobookPart.objects.create(audiobook=audiobook, index=1, chapter_start=1, chapter_end=1)
        AudiobookChapter.objects.create(
            part=part, chapter=chapter, file_in_source="audio/part-001/g1/00001.ogg",
            duration_s=1, size_bytes=1, sha256="0" * 64,
        )
        stored_before = NovelFromSource.objects.values().get(pk=source.pk)

        novel.novel_path = "lord of the mysteries"
        novel.save(update_fields=["novel_path"])

        renamed = NovelFromSource.objects.select_related("novel").get(pk=source.pk)
        folder = os.path.join("lord of the mysteries", "site")
        self.assertEqual(renamed.source_path, folder)
        self.assertEqual(renamed.cover_path, os.path.join(folder, "cover.jpg"))
        self.assertEqual(renamed.cover_min_path, os.path.join(folder, "cover.min.webp"))
        self.assertEqual(renamed.overview_picture_path, os.path.join(folder, "overview.jpg"))
        self.assertEqual(
            Audiobook.objects.get(pk=audiobook.pk).cover_path, os.path.join(folder, "audio", "cover.jpg"),
        )
        self.assertEqual(
            AudiobookChapter.objects.get(chapter=chapter).file_path,
            os.path.join(folder, "audio", "part-001", "g1", "00001.ogg"),
        )
        # Only the novel folder changed: the source row itself is untouched.
        self.assertEqual(NovelFromSource.objects.values().get(pk=source.pk), stored_before)

    def test_moving_a_source_changes_only_its_novel_and_folder(self):
        src_novel = bare_novel("alpha", "alpha")
        dst_novel = bare_novel("beta", "beta")
        source = make_source(
            src_novel, source_folder="site", cover_file="cover.jpg",
            cover_min_file="cover.min.webp", overview_picture_file="overview.jpg",
        )
        for name in ("cover.jpg", "cover.min.webp", "overview.jpg"):
            self.write("alpha", "site", name)
        before = NovelFromSource.objects.values().get(pk=source.pk)

        source = NovelFromSource.objects.get(pk=source.pk)
        with file_journal() as files:
            move_source_to_novel(source, dst_novel, files=files)

        after = NovelFromSource.objects.values().get(pk=source.pk)
        changed = {key for key in before if before[key] != after[key]}
        self.assertLessEqual(changed, {"novel_id", "source_slug", "updated_at"})
        self.assertEqual(after["novel_id"], dst_novel.pk)
        self.assertEqual(after["source_folder"], "site")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "beta", "site", "cover.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "alpha", "site")))

        moved = NovelFromSource.objects.select_related("novel").get(pk=source.pk)
        self.assertEqual(moved.cover_path, os.path.join("beta", "site", "cover.jpg"))
        self.assertIn("/beta/site/cover.jpg", build_media_url(moved.cover_path))

    def test_moving_a_source_into_a_folder_name_already_taken_changes_the_folder_too(self):
        src_novel = bare_novel("alpha", "alpha")
        dst_novel = bare_novel("beta", "beta")
        make_source(dst_novel, source_folder="site")
        source = make_source(src_novel, source_folder="site", cover_file="cover.jpg")
        self.write("alpha", "site", "cover.jpg")
        before = NovelFromSource.objects.values().get(pk=source.pk)

        source = NovelFromSource.objects.get(pk=source.pk)
        with file_journal() as files:
            move_source_to_novel(source, dst_novel, files=files)

        after = NovelFromSource.objects.values().get(pk=source.pk)
        changed = {key for key in before if before[key] != after[key]}
        self.assertLessEqual(changed, {"novel_id", "source_folder", "source_slug", "updated_at"})
        self.assertNotEqual(after["source_folder"], "site")
        moved = NovelFromSource.objects.select_related("novel").get(pk=source.pk)
        self.assertEqual(moved.cover_path, os.path.join("beta", after["source_folder"], "cover.jpg"))
        self.assertTrue(os.path.isfile(moved.absolute_source_path + os.sep + "cover.jpg"))
