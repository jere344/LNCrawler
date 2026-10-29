"""Public audiobook API: the list and detail, progress, plays, downloads, and the audiobook keys of the home page,
the novel detail and the chapter content."""

import json
import os
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
from unittest.mock import patch
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Audiobook,
    AudiobookChapter,
    AudiobookDailyStat,
    AudiobookPart,
    Chapter,
    ExternalSource,
    Job,
    ListeningProgress,
    Novel,
    NovelBookmark,
    NovelFromSource,
    ReadingHistory,
)
from ..services import audiobook_m4b
from .test_audiobooks import AudiobookBase
from .test_seo import _ld

COVER_PATCHES = (
    patch("lncrawler_api.services.audiobook_cover.cover_is_stale", return_value=False),
    patch("lncrawler_api.services.audiobook_cover.cover_key", return_value="c0ver000"),
)


class PublicAudiobookBase(AudiobookBase):
    """The 'foo' audiobook: one published English audiobook with one listenable part of three chapters."""

    def setUp(self):
        super().setUp()
        cache.clear()
        for patcher in COVER_PATCHES:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.source = self.make_source()
        self.chapters = self.add_chapters(self.source, [100, 100, 100])
        self.audiobook = self.make_audiobook(self.source)
        self.audiobook.published = True
        self.audiobook.save()
        self.part = self.make_part(
            self.audiobook, status="done", qa_passed=True, duration_s=3600,
            size_bytes=1000, chapter_start=1, chapter_end=3,
        )
        for offset, chapter in enumerate(self.chapters):
            AudiobookChapter.objects.create(
                part=self.part, chapter=chapter, file_path=f"foo/site/audio/{chapter.chapter_id}.opus",
                duration_s=1200, size_bytes=10, sha256="0" * 64, offset_s=offset * 1200,
            )
        self.user = get_user_model().objects.create_user(username="listener", password="pw12345!")

    def make_public(self, slug, duration_s=3600.0, language="en", published=True):
        """Another novel with a published audiobook of one listenable part and one chapter."""
        novel = Novel.objects.create(title=slug.title(), slug=slug, novel_path=slug)
        source_path = os.path.join(slug, "site")
        os.makedirs(os.path.join(self.tmp, source_path), exist_ok=True)
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"site-{slug}"),
            title=slug.title(),
            source_url=f"http://{slug}/1",
            source_path=source_path,
            source_slug="site",
            language=language,
            status="Ongoing",
        )
        chapter = Chapter.objects.create(
            novel_from_source=source, chapter_id=1, url=f"http://{slug}/1/1", title="Chapter 1", has_content=True,
        )
        audiobook = Audiobook.objects.create(
            novel=novel, source=source, language=language, published=published,
        )
        part = self.make_part(
            audiobook, status="done", qa_passed=True, duration_s=duration_s, chapter_start=1, chapter_end=1,
        )
        AudiobookChapter.objects.create(
            part=part, chapter=chapter, file_path=f"{slug}/audio/1.opus",
            duration_s=duration_s, size_bytes=1, sha256="0" * 64,
        )
        return audiobook

    def chapter_pk(self, number):
        return self.chapters[number - 1].pk

    def cached_path(self, fmt="opus"):
        """Path of the cached .m4b of the part, created on disk."""
        path = audiobook_m4b._cache_path(self.part, fmt)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"m4b")
        return path


class AudiobookListTests(PublicAudiobookBase):
    def test_lists_a_visible_audiobook_with_its_totals(self):
        response = self.client.get(reverse("list_audiobooks"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        card = response.json()["results"][0]
        self.assertEqual(card["slug"], "foo")
        self.assertEqual(card["parts"], 1)
        self.assertEqual(card["chapters"], 3)
        self.assertEqual(card["duration_s"], 3600)
        self.assertIsNone(card["progress"])

    def test_part_not_listenable_is_not_counted(self):
        self.make_part(self.audiobook, index=2, status="queued", chapter_start=4, chapter_end=6)

        card = self.client.get(reverse("list_audiobooks")).json()["results"][0]

        self.assertEqual(card["parts"], 1)
        self.assertEqual(card["chapters"], 3)

    def test_unpublished_retired_dmca_and_unlistenable_are_hidden(self):
        self.audiobook.published = False
        self.audiobook.save()
        self.assertEqual(self.client.get(reverse("list_audiobooks")).json()["count"], 0)

        self.audiobook.published = True
        self.audiobook.status = "retired"
        self.audiobook.save()
        self.assertEqual(self.client.get(reverse("list_audiobooks")).json()["count"], 0)

        self.audiobook.status = "active"
        self.audiobook.save()
        self.novel.is_dmca = True
        self.novel.save()
        self.assertEqual(self.client.get(reverse("list_audiobooks")).json()["count"], 0)

        self.novel.is_dmca = False
        self.novel.save()
        AudiobookPart.objects.filter(pk=self.part.pk).update(qa_passed=False, approved=False)
        self.assertEqual(self.client.get(reverse("list_audiobooks")).json()["count"], 0)

    def test_popular_sort_uses_recent_plays_and_downloads(self):
        quiet = self.make_public("quiet")
        AudiobookDailyStat.bump(quiet.pk, plays=2)
        AudiobookDailyStat.bump(self.audiobook.pk, plays=5, downloads=1)

        results = self.client.get(reverse("list_audiobooks")).json()["results"]

        self.assertEqual([card["slug"] for card in results], ["foo", "quiet"])

    def test_longest_sort_uses_public_duration(self):
        self.make_public("long-one", duration_s=7200)

        results = self.client.get(reverse("list_audiobooks"), {"sort": "longest"}).json()["results"]

        self.assertEqual([card["slug"] for card in results], ["long-one", "foo"])

    def test_q_filters_by_novel_title(self):
        self.make_public("zzz-other")

        results = self.client.get(reverse("list_audiobooks"), {"q": "Foo"}).json()["results"]

        self.assertEqual([card["slug"] for card in results], ["foo"])

    def test_lang_filters_by_language(self):
        self.make_public("french-one", language="fr")

        all_results = self.client.get(reverse("list_audiobooks")).json()["results"]
        french = self.client.get(reverse("list_audiobooks"), {"lang": "fr"}).json()["results"]

        self.assertEqual(len(all_results), 2)
        self.assertEqual([card["slug"] for card in french], ["french-one"])

    def test_languages_lists_every_visible_language_for_the_filter(self):
        self.make_public("french-one", language="fr")
        adult = self.make_public("adult-one", language="de")
        adult.source.is_adult = True
        adult.source.save()

        body = self.client.get(reverse("list_audiobooks"), {"lang": "fr"}).json()
        self.assertEqual(body["languages"], ["de", "en", "fr"])

        self.user.show_r18 = "no"
        self.user.save()
        self.client.force_login(self.user)
        body = self.client.get(reverse("list_audiobooks")).json()
        self.assertEqual(body["languages"], ["en", "fr"])

    def test_listening_needs_a_login(self):
        response = self.client.get(reverse("list_audiobooks"), {"listening": "1"})

        self.assertEqual(response.status_code, 401)

    def test_listening_lists_unfinished_audiobooks(self):
        self.client.force_login(self.user)
        ListeningProgress.objects.create(
            user=self.user, audiobook=self.audiobook, chapter=self.chapters[0], position_s=10,
        )

        results = self.client.get(reverse("list_audiobooks"), {"listening": "1"}).json()["results"]

        self.assertEqual([card["slug"] for card in results], ["foo"])
        self.assertEqual(results[0]["progress"]["position_s"], 10)

        ListeningProgress.objects.filter(user=self.user).update(finished=True)
        results = self.client.get(reverse("list_audiobooks"), {"listening": "1"}).json()["results"]
        self.assertEqual(results, [])

    def test_pagination_envelope(self):
        for number in range(24):
            self.make_public(f"novel-{number:02}")

        body = self.client.get(reverse("list_audiobooks")).json()

        self.assertEqual(body["count"], 25)
        self.assertEqual(body["total_pages"], 2)
        self.assertEqual(body["current_page"], 1)
        self.assertEqual(len(body["results"]), 24)


class AudiobookDetailTests(PublicAudiobookBase):
    def test_detail_shape(self):
        response = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"}))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["slug"], "foo")
        self.assertIn("audiobooks/foo/feed.xml", body["feed_url"])
        self.assertEqual(body["parts"][0]["state"], "available")
        self.assertEqual(len(body["parts"][0]["chapters"]), 3)
        self.assertTrue(body["parts"][0]["chapters"][0]["audio_url"].endswith("?g=0"))
        self.assertEqual(body["parts"][0]["downloads"]["opus"], {"cached": False})

    def test_detail_reports_cached_downloads_without_touching_the_file(self):
        path = self.cached_path()
        os.utime(path, (1000, 1000))

        body = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"})).json()

        self.assertTrue(body["parts"][0]["downloads"]["opus"]["cached"])
        self.assertEqual(os.path.getmtime(path), 1000)

    def test_parts_carry_engine_and_estimated_duration(self):
        self.part.engine = "kokoro-82m"
        self.part.estimated_duration_s = 3500
        self.part.save()
        self.make_part(
            self.audiobook, index=2, status="queued", chapter_start=4, chapter_end=6, estimated_duration_s=1800,
        )

        parts = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"})).json()["parts"]

        self.assertEqual(parts[0]["engine"], "kokoro-82m")
        self.assertEqual(parts[0]["estimated_duration_s"], 3500)
        self.assertIsNone(parts[1]["engine"])
        self.assertEqual(parts[1]["estimated_duration_s"], 1800)

    def test_cast_keeps_a_stripped_and_capped_description(self):
        self.audiobook.cast = {
            'Narrator': {'role': 'narrator', 'engine': 'kokoro', 'description': '  calm narrator  '},
            'Mara': {'role': 'main', 'engine': 'kokoro'},
            'Bob': {'role': 'minor', 'engine': 'kokoro', 'description': 'x' * 400},
        }
        self.audiobook.save()

        cast = {member["name"]: member for member in self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"})).json()["cast"]}

        self.assertEqual(cast["Narrator"]["description"], "calm narrator")
        self.assertIsNone(cast["Mara"]["description"])
        self.assertEqual(len(cast["Bob"]["description"]), 300)

    def test_one_volume_is_not_has_volumes(self):
        for chapter in self.chapters:
            chapter.volume = 1
            chapter.save()

        body = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"})).json()

        self.assertFalse(body["has_volumes"])
        self.assertEqual(body["parts"][0]["volumes"], [{"number": 1, "title": None}])

    def test_several_volumes_list_each_part_volumes_and_chapter_volume(self):
        self.chapters[0].volume = 1
        self.chapters[0].volume_title = "Beginnings"
        self.chapters[0].save()
        self.chapters[1].volume = 2
        self.chapters[1].save()
        self.chapters[2].volume = 2
        self.chapters[2].save()
        self.add_chapters(self.source, [100, 100], first_id=4, write_files=False)
        Chapter.objects.filter(novel_from_source=self.source, chapter_id__gte=4).update(volume=3)
        self.make_part(self.audiobook, index=2, status="queued", chapter_start=4, chapter_end=5)

        body = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"})).json()

        self.assertTrue(body["has_volumes"])
        self.assertEqual(body["parts"][0]["volumes"], [{"number": 1, "title": "Beginnings"}, {"number": 2, "title": None}])
        self.assertEqual(body["parts"][1]["volumes"], [{"number": 3, "title": None}])
        self.assertEqual(
            [(chapter["volume"], chapter["volume_title"]) for chapter in body["parts"][0]["chapters"]],
            [(1, "Beginnings"), (2, None), (2, None)],
        )

    def test_query_count_does_not_grow_with_parts(self):
        url = reverse("audiobook_detail", kwargs={"slug": "foo"})
        self.client.get(url)
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)

        # Listenable parts with chapters, so the chapter, download and volume paths all run for them
        chapters = self.add_chapters(self.source, [100, 100], first_id=4, write_files=False)
        for index, chapter in enumerate(chapters[3:], start=2):
            part = self.make_part(
                self.audiobook, index=index, status="done", qa_passed=True, duration_s=1200, size_bytes=10,
                chapter_start=chapter.chapter_id, chapter_end=chapter.chapter_id, chapter_ids=[chapter.pk],
            )
            AudiobookChapter.objects.create(
                part=part, chapter=chapter, file_path=f"foo/site/audio/{chapter.chapter_id}.opus",
                duration_s=1200, size_bytes=10, sha256="0" * 64, offset_s=0,
            )
        with CaptureQueriesContext(connection) as after:
            self.client.get(url)

        self.assertEqual(len(after.captured_queries), len(before.captured_queries))

    def test_unknown_language_is_404(self):
        response = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"}), {"lang": "xx"})

        self.assertEqual(response.status_code, 404)

    def test_unpublished_is_404(self):
        self.audiobook.published = False
        self.audiobook.save()

        response = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"}))

        self.assertEqual(response.status_code, 404)

    def test_dmca_detail_is_served_and_flagged_but_hidden_from_lists(self):
        self.novel.is_dmca = True
        self.novel.save()

        response = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_dmca"])
        self.assertEqual(self.client.get(reverse("list_audiobooks")).json()["count"], 0)

    def make_edition(self, language, published=True, status="active"):
        """An audiobook of the 'foo' novel in another language, with one listenable part."""
        source = self.make_source(name=f"site-{language}", language=language)
        audiobook = Audiobook.objects.create(
            novel=self.novel, source=source, language=language, published=published, status=status,
        )
        self.make_part(audiobook, status="done", qa_passed=True, duration_s=3600)
        return audiobook

    def test_other_languages_lists_the_other_visible_editions(self):
        self.make_edition("fr")
        self.make_edition("de", published=False)
        self.make_edition("es", status="retired")

        body = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"})).json()

        self.assertEqual(body["other_languages"], ["fr"])

    def test_adult_detail_is_served_to_show_r18_no_and_flagged_but_hidden_from_lists(self):
        self.source.is_adult = True
        self.source.save()
        self.user.show_r18 = "no"
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("audiobook_detail", kwargs={"slug": "foo"}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_adult"])
        self.assertFalse(response.json()["is_dmca"])
        self.assertEqual(self.client.get(reverse("list_audiobooks")).json()["count"], 0)


class AudiobookProgressTests(PublicAudiobookBase):
    def url(self):
        return reverse("audiobook_progress", kwargs={"slug": "foo"})

    def put(self, payload, method="put"):
        return getattr(self.client, method)(self.url(), json.dumps(payload), content_type="application/json")

    def test_anonymous_is_refused(self):
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))
        self.assertIn(self.put({"chapter_id": self.chapter_pk(1), "position_s": 1}).status_code, (401, 403))

    def test_put_saves_the_position(self):
        self.client.force_login(self.user)

        response = self.put({"chapter_id": self.chapter_pk(1), "position_s": 50, "speed": 1.5})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["progress"]["position_s"], 50)
        progress = ListeningProgress.objects.get(user=self.user, audiobook=self.audiobook)
        self.assertEqual(progress.speed, 1.5)
        self.assertFalse(ReadingHistory.objects.filter(user=self.user).exists())

    def test_dmca_audiobook_can_still_be_resumed(self):
        self.client.force_login(self.user)
        self.novel.is_dmca = True
        self.novel.save()

        response = self.put({"chapter_id": self.chapter_pk(1), "position_s": 50})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ListeningProgress.objects.get(user=self.user, audiobook=self.audiobook).position_s, 50)

    def test_post_is_accepted_too(self):
        self.client.force_login(self.user)

        response = self.put({"chapter_id": self.chapter_pk(2), "position_s": 5}, method="post")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["progress"]["chapter_number"], 2)

    def test_position_and_speed_are_clamped(self):
        self.client.force_login(self.user)

        self.put({"chapter_id": self.chapter_pk(1), "position_s": 99999, "speed": 9})

        progress = ListeningProgress.objects.get(user=self.user, audiobook=self.audiobook)
        self.assertEqual(progress.position_s, 1200)
        self.assertEqual(progress.speed, 3.0)

    def test_chapter_must_belong_to_the_audiobook(self):
        self.client.force_login(self.user)
        other = self.make_public("other-book")

        response = self.put({"chapter_id": other.parts.get().chapters.get().chapter.pk, "position_s": 1})

        self.assertEqual(response.status_code, 400)

    def test_bad_values_are_400(self):
        self.client.force_login(self.user)
        self.assertEqual(self.put({"chapter_id": self.chapter_pk(1)}).status_code, 400)
        self.assertEqual(self.put({"chapter_id": self.chapter_pk(1), "position_s": "abc"}).status_code, 400)
        self.assertEqual(
            self.put({"chapter_id": self.chapter_pk(1), "position_s": 1, "finished": "yes"}).status_code, 400,
        )
        self.assertEqual(self.put([1, 2]).status_code, 400)

    def test_reading_history_moves_at_ninety_percent(self):
        self.client.force_login(self.user)

        self.put({"chapter_id": self.chapter_pk(1), "position_s": 1000})
        self.assertFalse(ReadingHistory.objects.filter(user=self.user).exists())

        self.put({"chapter_id": self.chapter_pk(1), "position_s": 1080})
        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 1)

    def test_finished_moves_reading_history_forward_only(self):
        self.client.force_login(self.user)

        self.put({"chapter_id": self.chapter_pk(2), "position_s": 0, "finished": True})
        self.put({"chapter_id": self.chapter_pk(1), "position_s": 1200, "finished": True})

        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 2)

    def test_zero_length_chapter_never_moves_reading_history(self):
        self.client.force_login(self.user)
        AudiobookChapter.objects.filter(chapter=self.chapters[0]).update(duration_s=0)

        self.put({"chapter_id": self.chapter_pk(1), "position_s": 0})

        self.assertFalse(ReadingHistory.objects.filter(user=self.user).exists())


class AudiobookPlayTests(PublicAudiobookBase):
    def url(self):
        return reverse("audiobook_play", kwargs={"slug": "foo"})

    def test_every_play_call_counts(self):
        for _ in range(3):
            response = self.client.post(
                self.url(), json.dumps({"chapter_id": self.chapter_pk(1)}), content_type="application/json",
            )
            self.assertEqual(response.status_code, 204)

        plays = sum(stat.plays for stat in AudiobookDailyStat.objects.filter(audiobook=self.audiobook))
        self.assertEqual(plays, 3)

    def test_dmca_audiobook_still_counts_plays(self):
        self.novel.is_dmca = True
        self.novel.save()

        response = self.client.post(
            self.url(), json.dumps({"chapter_id": self.chapter_pk(1)}), content_type="application/json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(AudiobookDailyStat.objects.get(audiobook=self.audiobook).plays, 1)

    def test_listened_seconds_are_clamped(self):
        self.client.post(
            self.url(), json.dumps({"chapter_id": self.chapter_pk(1), "listened_s": 9999}),
            content_type="application/json",
        )

        stat = AudiobookDailyStat.objects.get(audiobook=self.audiobook)
        self.assertEqual(stat.listen_seconds, 300)

    def test_unknown_chapter_is_400(self):
        response = self.client.post(
            self.url(), json.dumps({"chapter_id": 999999}), content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)


class AudiobookDownloadTests(PublicAudiobookBase):
    def url(self, index=1):
        return reverse("audiobook_download", kwargs={"slug": "foo", "index": index})

    def test_unknown_format_is_400(self):
        self.assertEqual(self.client.get(self.url(), {"format": "mp3"}).status_code, 400)

    def test_unknown_part_is_404(self):
        self.assertEqual(self.client.get(self.url(index=2)).status_code, 404)

    def test_missing_build_starts_a_job(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response["Retry-After"], "5")
        self.assertEqual(response.json()["status"], "building")
        job = Job.objects.get(job_type=Job.JOB_TYPE_M4B)
        self.assertEqual(job.query, f"m4b:{self.part.pk}:opus")

    def test_active_job_is_reused(self):
        job = audiobook_m4b.enqueue_m4b_job(self.part, "opus")

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 202)
        self.assertEqual(Job.objects.filter(job_type=Job.JOB_TYPE_M4B).count(), 1)
        self.assertEqual(Job.objects.get(job_type=Job.JOB_TYPE_M4B).pk, job.pk)

    def test_cached_file_is_served_and_counted(self):
        self.cached_path()

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mp4")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"m4b")
        self.assertEqual(AudiobookDailyStat.objects.get(audiobook=self.audiobook).downloads, 1)

    def test_range_that_does_not_start_the_file_is_not_counted(self):
        self.cached_path()

        response = self.client.get(self.url(), HTTP_RANGE="bytes=100-")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AudiobookDailyStat.objects.filter(audiobook=self.audiobook, downloads__gt=0).exists())

    def test_behind_nginx_the_file_is_sent_by_accel_redirect(self):
        path = self.cached_path()

        response = self.client.get(self.url(), HTTP_X_REAL_IP="203.0.113.7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mp4")
        self.assertEqual(response["X-Accel-Redirect"], "/_m4b/" + os.path.relpath(
            path, self.tmp,
        ).replace(os.sep, "/"))

    def test_downloads_are_not_limited(self):
        self.cached_path()

        statuses = [self.client.get(self.url()).status_code for _ in range(5)]

        self.assertEqual(statuses, [200] * 5)
        self.assertEqual(AudiobookDailyStat.objects.get(audiobook=self.audiobook).downloads, 5)

    def test_dmca_audiobook_can_still_be_downloaded(self):
        self.cached_path()
        self.novel.is_dmca = True
        self.novel.save()

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AudiobookDailyStat.objects.get(audiobook=self.audiobook).downloads, 1)

    def test_dmca_audiobook_build_can_still_be_started(self):
        self.novel.is_dmca = True
        self.novel.save()

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 202)
        self.assertEqual(Job.objects.filter(job_type=Job.JOB_TYPE_M4B).count(), 1)

    def test_check_reports_a_cached_file_without_serving_or_counting_it(self):
        self.cached_path()

        checks = [self.client.get(self.url(), {"check": "1"}) for _ in range(3)]
        served = self.client.get(self.url())

        for response in checks:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ready"})
        self.assertEqual(served.status_code, 200)
        # Only the real request counts: the three checks did not.
        self.assertEqual(AudiobookDailyStat.objects.get(audiobook=self.audiobook).downloads, 1)

    def test_check_on_a_missing_file_starts_the_build_as_usual(self):
        response = self.client.get(self.url(), {"check": "1"})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "building")
        self.assertEqual(Job.objects.filter(job_type=Job.JOB_TYPE_M4B).count(), 1)


class AudiobookDailyStatTests(PublicAudiobookBase):
    def test_bump_adds_to_todays_row(self):
        AudiobookDailyStat.bump(self.audiobook.pk, plays=2, downloads=1, listen_seconds=10)
        AudiobookDailyStat.bump(self.audiobook.pk, plays=1)

        stats = AudiobookDailyStat.objects.filter(audiobook=self.audiobook)
        self.assertEqual(stats.count(), 1)
        self.assertEqual(stats.get().plays, 3)
        self.assertEqual(stats.get().downloads, 1)
        self.assertEqual(stats.get().listen_seconds, 10)


class AudiobookInPagesTests(PublicAudiobookBase):
    def test_chapter_content_carries_audio_url(self):
        body = self.client.get(
            reverse("chapter_content_by_number", kwargs={
                "novel_slug": "foo", "source_slug": "site", "chapter_number": 1,
            }),
        ).json()

        self.assertTrue(body["audio_url"].endswith("?g=0"))
        self.assertEqual(body["audio_duration_s"], 1200)

    def test_chapter_audio_url_is_none_when_hidden(self):
        self.audiobook.published = False
        self.audiobook.save()

        body = self.client.get(
            reverse("chapter_content_by_number", kwargs={
                "novel_slug": "foo", "source_slug": "site", "chapter_number": 1,
            }),
        ).json()

        self.assertIsNone(body["audio_url"])
        self.assertIsNone(body["audio_duration_s"])

    def test_novel_detail_lists_audiobook_languages_and_durations(self):
        body = self.client.get(reverse("novel_detail_by_slug", kwargs={"novel_slug": "foo"})).json()

        self.assertEqual(body["audiobooks"], [{"language": "en", "duration_s": 3600.0}])

    def test_home_has_featured_popular_and_continue_listening(self):
        self.audiobook.featured = True
        self.audiobook.save()
        popular = self.make_public("popular-one")
        AudiobookDailyStat.bump(popular.pk, plays=3)
        self.client.force_login(self.user)
        ListeningProgress.objects.create(user=self.user, audiobook=popular, position_s=5)

        block = self.client.get(reverse("home_page")).json()["audiobooks"]

        self.assertEqual(block["featured"]["slug"], "foo")
        self.assertEqual([card["slug"] for card in block["popular"]], ["popular-one"])
        self.assertEqual([card["slug"] for card in block["continue_listening"]], ["popular-one"])

    def test_home_anonymous_has_no_continue_listening(self):
        block = self.client.get(reverse("home_page")).json()["audiobooks"]

        self.assertEqual(block["continue_listening"], [])
        self.assertIsNone(block["featured"])

    def test_home_has_no_novels_you_added(self):
        self.client.force_login(self.user)
        body = self.client.get(reverse("home_page")).json()

        self.assertNotIn("novels_you_added", body)

    def test_home_rechecks_takedowns_after_the_cache(self):
        self.audiobook.featured = True
        self.audiobook.save()
        self.client.get(reverse("home_page"))

        self.novel.is_dmca = True
        self.novel.save()
        block = self.client.get(reverse("home_page")).json()["audiobooks"]

        self.assertIsNone(block["featured"])
        self.assertEqual(block["popular"], [])


class AudiobookFlagsInPagesTests(PublicAudiobookBase):
    def novel_cards(self):
        return {card["slug"]: card["has_audiobook"] for card in self.client.get(reverse("list_novels")).json()["results"]}

    def test_novel_cards_flag_novels_with_a_public_audiobook(self):
        Novel.objects.create(title="Baz", slug="baz", novel_path="baz")
        self.make_public("bar")

        cards = self.novel_cards()

        self.assertEqual(cards, {"foo": True, "bar": True, "baz": False})

    def test_unpublished_retired_or_unlistenable_does_not_flag_the_novel(self):
        self.audiobook.published = False
        self.audiobook.save()
        self.assertFalse(self.novel_cards()["foo"])

        self.audiobook.published = True
        self.audiobook.status = "retired"
        self.audiobook.save()
        self.assertFalse(self.novel_cards()["foo"])

        self.audiobook.status = "active"
        self.audiobook.save()
        self.part.status = "failed"
        self.part.save()
        self.assertFalse(self.novel_cards()["foo"])

    def test_source_detail_names_the_visible_audiobook_of_its_language(self):
        url = reverse("source_detail", kwargs={"novel_slug": "foo", "source_slug": "site"})

        self.assertEqual(
            self.client.get(url).json()["audiobook"],
            {"language": "en", "duration_s": 3600.0, "slug": "foo", "is_adult": False},
        )

    def test_source_detail_has_no_audiobook_in_another_language_or_when_hidden(self):
        self.make_source("fr", language="fr")
        french_url = reverse("source_detail", kwargs={"novel_slug": "foo", "source_slug": "fr"})
        self.assertIsNone(self.client.get(french_url).json()["audiobook"])

        self.audiobook.published = False
        self.audiobook.save()
        url = reverse("source_detail", kwargs={"novel_slug": "foo", "source_slug": "site"})
        self.assertIsNone(self.client.get(url).json()["audiobook"])

    def test_chapter_list_flags_chapters_with_public_audio(self):
        self.add_chapters(self.source, [100], first_id=4, write_files=False)
        url = reverse("novel_chapters_by_source", kwargs={"novel_slug": "foo", "source_slug": "site"})

        chapters = self.client.get(url).json()["chapters"]

        self.assertEqual([chapter["has_audio"] for chapter in chapters], [True, True, True, False])


class AudiobookFlagsInOtherCardSurfacesTests(PublicAudiobookBase):
    """The novel cards built outside list_novels carry has_audiobook too."""

    def setUp(self):
        super().setUp()
        self.make_public("bar")
        self.foo = Novel.objects.get(slug="foo")

    def flags(self, results):
        return {card["slug"]: card["has_audiobook"] for card in results}

    def test_search_cards(self):
        Novel.objects.create(title="Baz", slug="baz", novel_path="baz")

        results = self.client.get(reverse("search_novels")).json()["results"]

        self.assertEqual(self.flags(results), {"foo": True, "bar": True, "baz": False})

    def test_home_ranking_cards(self):
        top = self.client.get(reverse("home_page")).json()["top_novels"]

        self.assertEqual(self.flags(top), {"foo": True, "bar": True})

    def test_library_cards(self):
        NovelBookmark.objects.create(user=self.user, novel=self.foo)
        self.client.force_login(self.user)

        results = self.client.get(reverse("user_library", kwargs={"username": self.user.username})).json()["results"]

        self.assertEqual(self.flags(results), {"foo": True})

    def test_reading_history_cards(self):
        ReadingHistory.objects.create(user=self.user, novel=self.foo, source=self.source)
        self.client.force_login(self.user)

        results = self.client.get(reverse("list_reading_history")).json()["results"]

        self.assertEqual(self.flags(results), {"foo": True})


ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
PODCAST = "{https://podcastindex.org/namespace/1.0}"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
SITE_URL = settings.SITE_URL.rstrip("/")


class PodcastFeedTests(PublicAudiobookBase):
    def feed(self, slug="foo", query=""):
        return self.client.get(reverse("audiobook_feed", args=[slug]) + query)

    def test_channel_and_namespaces(self):
        response = self.feed()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "public, max-age=3600")
        root = ET.fromstring(response.content)
        channel = root.find("channel")
        self.assertEqual(channel.findtext("title"), "Foo (Generated audiobook)")
        self.assertTrue(channel.findtext("description").startswith("Generated audiobook made from the site text"))
        self.assertEqual(channel.findtext("link"), f"{SITE_URL}/audiobooks/foo/")
        self.assertEqual(channel.findtext(f"{ITUNES}explicit"), "false")
        self.assertEqual(channel.findtext(f"{ITUNES}type"), "serial")
        self.assertEqual(channel.find(f"{ITUNES}category").get("text"), "Arts")
        self.assertEqual(channel.find(f"{ITUNES}category/{ITUNES}category").get("text"), "Books")
        narrators = [p.text for p in channel.findall(f"{PODCAST}person") if p.get("role") == "narrator"]
        self.assertEqual(len(narrators), 1)

    def test_one_item_per_listenable_chapter_newest_first(self):
        # A part awaiting QA is not in the feed.
        self.make_part(
            self.audiobook, index=2, status="done", qa_passed=False, duration_s=10,
            chapter_start=1, chapter_end=1,
        )
        pending = Chapter.objects.create(
            novel_from_source=self.source, chapter_id=4, url="http://foo/1/4", title="Pending", has_content=True,
        )
        AudiobookChapter.objects.create(
            part=AudiobookPart.objects.get(audiobook=self.audiobook, index=2), chapter=pending,
            file_path="foo/site/audio/pending.opus", duration_s=10, size_bytes=1, sha256="0" * 64,
        )

        items = ET.fromstring(self.feed().content).find("channel").findall("item")

        self.assertEqual([item.findtext(f"{ITUNES}episode") for item in items], ["3", "2", "1"])
        self.assertEqual({item.findtext(f"{ITUNES}season") for item in items}, {"1"})
        self.assertEqual([item.findtext(f"{ITUNES}episodeType") for item in items], ["full"] * 3)
        dates = [parsedate_to_datetime(item.findtext("pubDate")) for item in items]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_enclosure_and_guid(self):
        items = ET.fromstring(self.feed().content).find("channel").findall("item")
        first = items[0]

        enclosure = first.find("enclosure")
        self.assertTrue(enclosure.get("url").endswith(f"?g={self.part.generation}"))
        self.assertEqual(enclosure.get("length"), "10")
        self.assertEqual(enclosure.get("type"), "audio/ogg")
        guid = first.find("guid")
        self.assertEqual(guid.get("isPermaLink"), "false")
        self.assertEqual(guid.text, f"{self.chapter_pk(3)}-g{self.part.generation}")
        self.assertEqual(first.findtext(f"{ITUNES}duration"), "1200")

    def test_guid_changes_with_generation(self):
        before = ET.fromstring(self.feed().content).find("channel/item/guid").text
        self.part.generation += 1
        self.part.save()

        after = ET.fromstring(self.feed().content).find("channel/item/guid").text

        self.assertNotEqual(before, after)

    def test_pubdate_follows_chapter_offset(self):
        self.part.completed_at = timezone.now() - timedelta(days=1)
        self.part.save()

        items = ET.fromstring(self.feed().content).find("channel").findall("item")
        newest, middle, oldest = (parsedate_to_datetime(item.findtext("pubDate")) for item in items)

        self.assertEqual((middle - oldest).total_seconds(), 1200)
        self.assertEqual((newest - middle).total_seconds(), 1200)

    def test_hidden_audiobooks_are_404(self):
        self.audiobook.published = False
        self.audiobook.save()
        self.assertEqual(self.feed().status_code, 404)

        self.audiobook.published = True
        self.audiobook.save()
        self.source.is_adult = True
        self.source.save()
        self.assertEqual(self.feed().status_code, 200)

        self.source.is_adult = False
        self.source.save()
        self.novel.is_dmca = True
        self.novel.save()
        self.assertEqual(self.feed().status_code, 404)


class AudiobookSitemapTests(PublicAudiobookBase):
    def section(self):
        response = self.client.get(
            reverse("django.contrib.sitemaps.views.sitemap", kwargs={"section": "audiobooks"})
        )
        self.assertEqual(response.status_code, 200)
        root = ET.fromstring(response.content)
        paths = []
        for loc in root.findall(f"{SITEMAP_NS}url/{SITEMAP_NS}loc"):
            parts = urlsplit(loc.text)
            paths.append(parts.path + (f"?{parts.query}" if parts.query else ""))
        return paths

    def test_lists_listings_and_visible_audiobooks_only(self):
        self.make_public("bar")
        self.make_public("hidden-one", published=False)
        self.make_public("baz", language="fr")

        self.assertEqual(
            self.section(),
            ["/audiobooks/", "/audiobooks/bar/", "/audiobooks/baz/?lang=fr", "/audiobooks/foo/"],
        )


class SeoAudiobookTests(PublicAudiobookBase):
    def test_detail_jsonld_and_head(self):
        self.part.duration_s = 45000
        self.part.save()

        response = self.client.get(reverse("seo_audiobook", args=["foo"]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'<link rel="canonical" href="{SITE_URL}/audiobooks/foo/">', html)
        self.assertIn('<meta property="og:audio" content="', html)
        self.assertIn('<meta property="og:audio:type" content="audio/ogg">', html)
        self.assertIn('<meta property="og:type" content="book">', html)
        book = next(block for block in _ld(response) if block.get("@type") == "Audiobook")
        self.assertEqual(book["duration"], "PT12H30M")
        self.assertEqual(book["readBy"]["@type"], "Person")
        self.assertEqual(book["url"], f"{SITE_URL}/audiobooks/foo/")
        self.assertEqual(book["inLanguage"], "en")
        self.assertEqual(book["readBy"]["name"], "Generated voices (LNCrawler)")
        self.assertIn("<title>Foo \u2013 Generated audiobook</title>", html)
        self.assertIn("Generated audiobook: Foo, narrated with generated voices.", html)
        self.assertIn("Not an official audiobook.", html)

    def test_detail_hidden_is_404_and_dmca_is_451(self):
        self.audiobook.published = False
        self.audiobook.save()
        self.assertEqual(self.client.get(reverse("seo_audiobook", args=["foo"])).status_code, 404)

        self.audiobook.published = True
        self.audiobook.save()
        self.novel.is_dmca = True
        self.novel.save()
        self.assertEqual(self.client.get(reverse("seo_audiobook", args=["foo"])).status_code, 451)

    def test_list_shows_visible_audiobooks_only(self):
        self.make_public("bar")
        self.make_public("hidden-one", published=False)

        html = self.client.get(reverse("seo_audiobooks")).content.decode()

        self.assertIn("/audiobooks/bar/", html)
        self.assertIn("/audiobooks/foo/", html)
        self.assertNotIn("/audiobooks/hidden-one/", html)

    def test_seo_novel_links_its_audiobook(self):
        html = self.client.get(reverse("seo_novel", args=["foo"])).content.decode()

        self.assertIn(f'href="{SITE_URL}/audiobooks/foo/"', html)


class AudiobookAdultTests(PublicAudiobookBase):
    """Adult audiobooks: visible to guests and to the viewers who allow adult content, hidden only from the logged-in
    viewers who chose 'no'. The SEO pages and the sitemap never list them."""

    def setUp(self):
        super().setUp()
        self.source.is_adult = True
        self.source.save()

    def listed(self):
        return [card["slug"] for card in self.client.get(reverse("list_audiobooks")).json()["results"]]

    def test_guest_sees_adult_audiobook_flagged(self):
        response = self.client.get(reverse("list_audiobooks"))

        self.assertEqual(response.json()["results"][0]["slug"], "foo")
        self.assertTrue(response.json()["results"][0]["is_adult"])

    def test_show_r18_no_hides_adult_audiobook(self):
        self.user.show_r18 = "no"
        self.user.save()
        self.client.force_login(self.user)

        self.assertEqual(self.listed(), [])

    def test_show_r18_blur_and_yes_see_adult_audiobook(self):
        for choice in ("blur", "yes"):
            with self.subTest(show_r18=choice):
                self.user.show_r18 = choice
                self.user.save()
                self.client.force_login(self.user)

                self.assertEqual(self.listed(), ["foo"])

    def test_seo_pages_exclude_adult_audiobooks(self):
        html = self.client.get(reverse("seo_audiobooks")).content.decode()

        self.assertNotIn("/audiobooks/foo/", html)
        self.assertEqual(self.client.get(reverse("seo_audiobook", args=["foo"])).status_code, 404)

    def test_sitemap_excludes_adult_audiobooks(self):
        response = self.client.get(
            reverse("django.contrib.sitemaps.views.sitemap", kwargs={"section": "audiobooks"})
        )

        self.assertNotIn(b"/audiobooks/foo/", response.content)

    def test_adult_novel_hides_its_audiobook_for_show_r18_no(self):
        # A novel is adult when more than half of its sources are: two adult sources of three make it adult
        self.source.is_adult = False
        self.source.save()
        for slug in ("adult-a", "adult-b"):
            NovelFromSource.objects.create(
                novel=self.novel, external_source=ExternalSource.objects.create(source_name=f"site-{slug}"),
                title="Foo", source_url=f"http://foo/{slug}", source_path=f"foo/{slug}", source_slug=slug,
                language="de", status="Ongoing", is_adult=True,
            )
        self.user.show_r18 = "no"
        self.user.save()
        self.client.force_login(self.user)

        self.assertEqual(self.listed(), [])


class CatalogFeedTests(PublicAudiobookBase):
    def feed(self, query=""):
        return self.client.get(reverse("audiobook_catalog_feed") + query)

    def items(self, response):
        return ET.fromstring(response.content).find("channel").findall("item")

    def test_headers_and_channel(self):
        response = self.feed()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "public, max-age=3600")
        channel = ET.fromstring(response.content).find("channel")
        self.assertEqual(channel.findtext("title"), "LNCrawler generated audiobooks")
        self.assertEqual(channel.findtext("link"), f"{SITE_URL}/audiobooks/")

    def test_item_shape(self):
        item = self.items(self.feed())[0]

        self.assertEqual(item.findtext("title"), "Foo — Part 1 (Generated audiobook)")
        self.assertEqual(item.findtext("link"), f"{SITE_URL}/audiobooks/foo/")
        self.assertEqual(item.find("guid").text, f"{self.part.pk}-g{self.part.generation}")
        self.assertEqual(item.find("guid").get("isPermaLink"), "false")
        self.assertIn("Chapters 1–3, ", item.findtext("description"))
        self.assertIn("Generated audiobook, not an official one.", item.findtext("description"))
        self.assertIsNotNone(item.findtext("pubDate"))

    def test_default_and_unknown_modes_exclude_adult(self):
        self.source.is_adult = True
        self.source.save()

        self.assertEqual(self.items(self.feed()), [])
        self.assertEqual(self.items(self.feed("?adult=bogus")), [])

    def test_only_lists_adult_and_titles_the_channel(self):
        self.source.is_adult = True
        self.source.save()

        response = self.feed("?adult=only")

        self.assertEqual(len(self.items(response)), 1)
        self.assertEqual(ET.fromstring(response.content).find("channel").findtext("title"),
                         "LNCrawler generated audiobooks (adult)")

    def test_include_lists_everything_and_titles_the_channel(self):
        self.source.is_adult = True
        self.source.save()
        self.make_public("bar")

        response = self.feed("?adult=include")

        self.assertEqual(len(self.items(response)), 2)
        self.assertEqual(ET.fromstring(response.content).find("channel").findtext("title"),
                         "LNCrawler generated audiobooks (all)")

    def test_exclude_keeps_adult_out_and_plain_books_in(self):
        self.source.is_adult = True
        self.source.save()
        self.make_public("bar")

        titles = [item.findtext("title") for item in self.items(self.feed("?adult=exclude"))]

        self.assertEqual(titles, ["Bar — Part 1 (Generated audiobook)"])

    def test_dmca_unpublished_and_unlistenable_are_not_listed(self):
        self.novel.is_dmca = True
        self.novel.save()
        self.make_public("hidden-one", published=False)

        self.assertEqual(self.items(self.feed("?adult=include")), [])

    def test_one_item_per_listenable_part_newest_first(self):
        self.make_part(self.audiobook, index=2, status="done", qa_passed=True, duration_s=600,
                       chapter_start=4, chapter_end=4)
        self.make_part(self.audiobook, index=3, status="queued", chapter_start=5, chapter_end=6)
        AudiobookPart.objects.filter(pk=self.part.pk).update(completed_at=timezone.now() - timedelta(days=1))
        AudiobookPart.objects.filter(audiobook=self.audiobook, index=2).update(completed_at=timezone.now())

        titles = [item.findtext("title") for item in self.items(self.feed())]

        self.assertEqual(titles, [
            "Foo — Part 2 (Generated audiobook)",
            "Foo — Part 1 (Generated audiobook)",
        ])

    def test_limit_is_applied(self):
        with patch("lncrawler_api.services.audiobook_feed.CATALOG_LIMIT", 2):
            for slug in ("bar", "baz"):
                self.make_public(slug)

            self.assertEqual(len(self.items(self.feed())), 2)

    def test_list_response_carries_the_catalog_feed_url_without_the_adult_param(self):
        response = self.client.get(reverse("list_audiobooks"))

        self.assertEqual(response.json()["catalog_feed_url"], f"{settings.SITE_API_URL}/audiobooks/feed.xml")
