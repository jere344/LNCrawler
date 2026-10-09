"""Tests for the NovelUpdates import service."""

import json

from django.contrib.auth import get_user_model

from django.test import TestCase

from django.urls import reverse

from ..models import (
    Chapter,
    ExternalSource,
    Novel,
    NovelBookmark,
    NovelFromSource,
    ReadingHistory,
)


class NovelUpdatesImportTests(TestCase):
    """Read-only import of a NovelUpdates XML reading-list export."""

    SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<nu_readinglist>
<list>Reading (Manual)<series><title>D-Genesis</title><chp>v0c0</chp></series>
<series><title>Overgeared</title><chp>v0c1</chp></series>
<series><title>Kumo Desu ga, Nani ka?</title><chp>c823</chp></series>
<series><title>Untracked Thing</title><chp/></series>
</list>
<list>Completed<series><title>D-Genesis</title><chp/></series></list>
</nu_readinglist>"""

    def setUp(self):
        from ..models import Volume

        self.user = get_user_model().objects.create_user(
            username="importer", email="importer@example.com", password="pw12345!"
        )
        self.novel = Novel.objects.create(
            title="D-Genesis", slug="d-genesis", novel_path="d-genesis"
        )
        self.source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="Test"),
            title="D-Genesis",
            source_url="http://src/dgenesis",
            source_slug="d-genesis",
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for number in (1, 823):
            Chapter.objects.create(
                novel_from_source=self.source,
                chapter_id=number,
                url=f"http://src/dgenesis/{number}",
                title=f"Chapter {number}",
            )
        Volume.objects.create(
            novel_from_source=self.source, volume_id=1, title="Vol 1", start_chapter=1
        )

    def test_parse_chp_forms(self):
        from ..services.novelupdates_import_service import parse_chp

        self.assertEqual(parse_chp("v0c0"), (0, 0))
        self.assertEqual(parse_chp("v0c1"), (0, 1))
        self.assertEqual(parse_chp("c823"), (0, 823))
        self.assertEqual(parse_chp("57"), (0, 57))
        self.assertEqual(parse_chp("v2c5"), (2, 5))
        self.assertEqual(parse_chp(""), (0, 0))
        self.assertEqual(parse_chp(None), (0, 0))

    def test_folder_name_strips_manual_suffix(self):
        from ..services.novelupdates_import_service import folder_name_for

        self.assertEqual(folder_name_for("Reading (Manual)"), "Reading")
        self.assertEqual(folder_name_for("Completed"), "Completed")

    def test_parse_reads_lists_titles_and_progress(self):
        from ..services.novelupdates_import_service import parse_nu_export

        entries = parse_nu_export(self.SAMPLE.encode("utf-8"))
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[0]["list_name"], "Reading (Manual)")
        self.assertEqual(entries[0]["title"], "D-Genesis")
        self.assertEqual(entries[2]["chapter"], 823)
        self.assertEqual(entries[3]["chapter"], 0)
        self.assertEqual(entries[4]["list_name"], "Completed")

    def test_parse_rejects_foreign_xml(self):
        from ..services.novelupdates_import_service import parse_nu_export

        with self.assertRaises(ValueError):
            parse_nu_export(b"<foo><bar/></foo>")

    def test_parse_endpoint_matches_by_title(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("parse_novelupdates_import"),
            data={
                "file": SimpleUploadedFile(
                    "nu.xml", self.SAMPLE.encode("utf-8"), content_type="application/xml"
                )
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        first = response.data["entries"][0]
        self.assertEqual(first["title"], "D-Genesis")
        self.assertEqual(first["status"], "matched")
        self.assertEqual(first["folder"], "Reading")
        entries = {entry["title"]: entry for entry in response.data["entries"]}
        self.assertEqual(entries["Untracked Thing"]["status"], "unmatched")

    def _apply(self, entries):
        self.client.force_login(self.user)
        return self.client.post(
            reverse("apply_novelupdates_import"),
            data=json.dumps({"entries": entries}),
            content_type="application/json",
        )

    def test_apply_creates_bookmark_folder_and_progress(self):
        response = self._apply(
            [
                {
                    "novel_id": str(self.novel.id),
                    "folder": "Reading",
                    "volume": 0,
                    "chapter": 823,
                }
            ]
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["bookmarked"], 1)
        self.assertEqual(response.data["folders_created"], 1)
        self.assertEqual(response.data["progress_set"], 1)

        bookmark = NovelBookmark.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(bookmark.folder.name, "Reading")
        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 823)

        again = self._apply([{"novel_id": str(self.novel.id), "chapter": 823}])
        self.assertEqual(again.data["already_bookmarked"], 1)
        self.assertEqual(again.data["bookmarked"], 0)

    def test_apply_volume_fallback_uses_start_chapter(self):
        response = self._apply(
            [{"novel_id": str(self.novel.id), "volume": 1, "chapter": 0}]
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["progress_set"], 1)
        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 1)

    def test_apply_requires_authentication(self):
        response = self.client.post(
            reverse("apply_novelupdates_import"),
            data=json.dumps({"entries": []}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_parse_requires_authentication(self):
        response = self.client.post(reverse("parse_novelupdates_import"))
        self.assertIn(response.status_code, (401, 403))

    def test_apply_ignores_non_dict_entries(self):
        response = self._apply(
            [1, "x", None, {"novel_id": str(self.novel.id), "chapter": 1}]
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["bookmarked"], 1)
        self.assertEqual(response.data["skipped"], 3)

    def test_apply_does_not_regress_progress(self):
        ReadingHistory.objects.create(
            user=self.user,
            novel=self.novel,
            source=self.source,
            last_read_chapter=Chapter.objects.get(
                novel_from_source=self.source, chapter_id=823
            ),
        )
        response = self._apply([{"novel_id": str(self.novel.id), "chapter": 1}])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["progress_set"], 0)
        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 823)

    def test_parse_ambiguous_when_titles_collide(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        Novel.objects.create(title="D-Genesis", slug="d-genesis-2", novel_path="d-genesis-2")
        self.client.force_login(self.user)
        sample = (
            b'<nu_readinglist><list>Reading<series><title>D-Genesis</title>'
            b"<chp/></series></list></nu_readinglist>"
        )
        response = self.client.post(
            reverse("parse_novelupdates_import"),
            data={
                "file": SimpleUploadedFile(
                    "nu.xml", sample, content_type="application/xml"
                )
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        entry = response.data["entries"][0]
        self.assertEqual(entry["status"], "ambiguous")
        self.assertIsNone(entry["novel"])
        self.assertEqual(len(entry["candidates"]), 2)
