"""Tests for the "Recently Added Novels" and "Novels You Added" home sections."""

import json
import os
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from ..models import ExternalSource, Job, Novel, NovelFromSource
from ..services import DownloaderService


class DownloadAttributionTests(TestCase):
    """A job started by a connected user records that user."""

    def test_search_and_direct_download_record_user(self):
        user = get_user_model().objects.create_user(
            username="u1", email="u1@example.com", password="x"
        )

        job = DownloaderService.start_search("some query", user=user)
        self.assertEqual(job.user, user)

        result = DownloaderService.start_direct_download(
            "http://example.invalid/novel", user=user
        )
        direct = Job.objects.get(id=result["job_id"])
        self.assertEqual(direct.user, user)

    def test_anonymous_jobs_have_no_user(self):
        job = DownloaderService.start_search("some query")
        self.assertIsNone(job.user)


class DownloadViewAuthTests(TestCase):
    """The plain Django downloader views must resolve the token user, since
    login is token-only and no session is established."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="u1", email="u1@example.com", password="x"
        )
        self.token = Token.objects.create(user=self.user)

    def _post(self, name, payload):
        return self.client.post(
            reverse(name),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

    def test_start_search_attributes_token_user(self):
        response = self._post("start_search", {"query": "some query"})
        self.assertEqual(response.status_code, 200, response.content)
        job = Job.objects.get(id=response.json()["job_id"])
        self.assertEqual(job.user, self.user)

    def test_start_direct_download_attributes_token_user(self):
        response = self._post(
            "start_direct_download", {"novel_url": "http://example.invalid/novel"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        job = Job.objects.get(id=response.json()["job_id"])
        self.assertEqual(job.user, self.user)

    def _search_completed_job(self, **kwargs):
        return Job.objects.create(
            status=Job.STATUS_SEARCH_COMPLETED,
            job_type=Job.JOB_TYPE_SEARCH,
            search_results={
                "results": [{"sources": [{"url": "http://example.invalid/novel"}]}]
            },
            **kwargs,
        )

    def test_start_download_fills_missing_user(self):
        job = self._search_completed_job()
        response = self.client.post(
            reverse("start_download", args=[job.id]),
            data=json.dumps({"novel_index": 0, "source_index": 0}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )
        self.assertEqual(response.status_code, 200, response.content)
        job.refresh_from_db()
        self.assertEqual(job.user, self.user)

    def test_start_download_does_not_overwrite_existing_owner(self):
        other = get_user_model().objects.create_user(
            username="u2", email="u2@example.com", password="x"
        )
        job = self._search_completed_job(user=other)
        response = self.client.post(
            reverse("start_download", args=[job.id]),
            data=json.dumps({"novel_index": 0, "source_index": 0}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )
        self.assertEqual(response.status_code, 200, response.content)
        job.refresh_from_db()
        self.assertEqual(job.user, other)

    def test_anonymous_request_stays_unattributed(self):
        response = self.client.post(
            reverse("start_search"),
            data=json.dumps({"query": "some query"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        job = Job.objects.get(id=response.json()["job_id"])
        self.assertIsNone(job.user)

    def test_invalid_token_stays_unattributed(self):
        response = self.client.post(
            reverse("start_search"),
            data=json.dumps({"query": "some query"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Token not-a-real-token",
        )
        self.assertEqual(response.status_code, 200, response.content)
        job = Job.objects.get(id=response.json()["job_id"])
        self.assertIsNone(job.user)


class FromMetaJsonAttributionTests(TestCase):
    """added_by is recorded on creation and never rewritten by an update."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-added-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.override = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = get_user_model().objects.create_user(
            username="u1", email="u1@example.com", password="x"
        )

    def _write_meta(self, title="My Novel", url="http://s/1"):
        directory = os.path.join(self.tmp, "mynovel", "src")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "meta.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"novel": {"title": title, "url": url, "chapters": []}}, handle)
        return path

    def test_added_by_set_on_creation_only(self):
        path = self._write_meta()
        source = NovelFromSource.from_meta_json(path, added_by=self.user)
        self.assertEqual(source.novel.added_by, self.user)

        # A later import (an update) must not clear the original contributor.
        NovelFromSource.from_meta_json(path)
        source.novel.refresh_from_db()
        self.assertEqual(source.novel.added_by, self.user)

    def test_added_by_not_rewritten_by_another_user(self):
        path = self._write_meta()
        source = NovelFromSource.from_meta_json(path, added_by=self.user)
        other = get_user_model().objects.create_user(
            username="u2", email="u2@example.com", password="x"
        )
        NovelFromSource.from_meta_json(path, added_by=other)
        source.novel.refresh_from_db()
        self.assertEqual(source.novel.added_by, self.user)

    def test_added_by_not_set_for_anonymous(self):
        path = self._write_meta()
        source = NovelFromSource.from_meta_json(path)
        self.assertIsNone(source.novel.added_by)


class HomeAddedSectionsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="u1", email="u1@example.com", password="x"
        )
        self.other = get_user_model().objects.create_user(
            username="u2", email="u2@example.com", password="x"
        )

        self.mine = Novel.objects.create(
            title="Mine", slug="mine", novel_path="mine", added_by=self.user
        )
        self.theirs = Novel.objects.create(
            title="Theirs", slug="theirs", novel_path="theirs", added_by=self.other
        )
        self.plain = Novel.objects.create(
            title="Plain", slug="plain", novel_path="plain"
        )
        now = timezone.now()
        Novel.objects.filter(pk=self.mine.pk).update(created_at=now - timedelta(days=3))
        Novel.objects.filter(pk=self.theirs.pk).update(
            created_at=now - timedelta(days=2)
        )
        Novel.objects.filter(pk=self.plain.pk).update(created_at=now - timedelta(days=1))

        for novel in (self.mine, self.theirs, self.plain):
            NovelFromSource.objects.create(
                novel=novel,
                external_source=ExternalSource.objects.create(
                    source_name=f"src-{novel.slug}"
                ),
                title=novel.title,
                source_url=f"http://{novel.slug}/1",
                language="en",
            )

    def test_recently_added_lists_all_novels_newest_first(self):
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200, response.data)
        ids = [n["id"] for n in response.data["recently_added"]]
        self.assertEqual(
            ids, [str(self.plain.id), str(self.theirs.id), str(self.mine.id)]
        )

    def test_novels_you_added_only_for_owner(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home_page"))
        ids = [n["id"] for n in response.data["novels_you_added"]]
        self.assertEqual(ids, [str(self.mine.id)])

        self.client.force_login(self.other)
        response = self.client.get(reverse("home_page"))
        ids = [n["id"] for n in response.data["novels_you_added"]]
        self.assertEqual(ids, [str(self.theirs.id)])

    def test_novels_you_added_empty_for_anonymous(self):
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.data["novels_you_added"], [])

    def test_novels_you_added_ignores_language_filter(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home_page"), {"languages": "fr"})
        ids = [n["id"] for n in response.data["novels_you_added"]]
        self.assertEqual(ids, [str(self.mine.id)])

    def test_novels_you_added_keeps_adult_but_recently_added_excludes_it(self):
        self.mine.is_dmca = True
        self.mine.save(update_fields=["is_dmca"])
        adult = Novel.objects.create(
            title="Adult", slug="adult", novel_path="adult", added_by=self.user
        )
        NovelFromSource.objects.create(
            novel=adult,
            external_source=ExternalSource.objects.create(source_name="adult-src"),
            title="Adult",
            source_url="http://adult/1",
            language="en",
            is_adult=True,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("home_page"))
        added_ids = {n["id"] for n in response.data["recently_added"]}
        mine_ids = {n["id"] for n in response.data["novels_you_added"]}
        # DMCA stays hidden everywhere.
        self.assertNotIn(str(self.mine.id), added_ids)
        self.assertNotIn(str(self.mine.id), mine_ids)
        # Adult is filtered from "Recently Added" but kept in "Novels You Added".
        self.assertNotIn(str(adult.id), added_ids)
        self.assertIn(str(adult.id), mine_ids)

    def test_home_query_count_is_flat(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure(count):
            for index in range(count):
                novel = Novel.objects.create(
                    title=f"Extra {count}-{index}",
                    slug=f"extra-{count}-{index}",
                    novel_path=f"e{count}-{index}",
                    added_by=self.user,
                )
                NovelFromSource.objects.create(
                    novel=novel,
                    external_source=ExternalSource.objects.create(
                        source_name=f"extra-src-{count}-{index}"
                    ),
                    title=novel.title,
                    source_url=f"http://extra/{count}/{index}",
                    language="en",
                )
            self.client.force_login(self.user)
            with CaptureQueriesContext(connection) as captured:
                self.client.get(reverse("home_page"))
            return len(captured)

        self.assertEqual(measure(2), measure(4))
