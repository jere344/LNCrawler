"""Tests for the cross-source duplicate candidate finder."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from ..management.commands.find_merge_candidates import combo_certainty, normalize_text
from ..models import ExternalSource, MergeCandidate, Novel, NovelFromSource
from .helpers import MergeTestCase


class NormalizeTests(MergeTestCase):
    def test_strips_parentheticals_case_and_punctuation(self):
        self.assertEqual(normalize_text("Worm (Parahumans #1)"), "worm")
        self.assertEqual(normalize_text("Worm"), "worm")
        self.assertEqual(normalize_text("Lord of the Mysteries!"), "lord of the mysteries")

    def test_certainty_grows_with_corroborating_signals(self):
        self.assertGreater(
            combo_certainty({"title": 1.0, "author": 1.0}),
            combo_certainty({"title": 1.0}),
        )


class FindMergeCandidatesTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.es = ExternalSource.objects.create(source_name="site")

    def _novel(self, title, slug):
        return Novel.objects.create(title=title, slug=slug, novel_path=slug)

    def test_normalized_title_creates_a_review_candidate(self):
        self._novel("Worm (Parahumans #1)", "worm-para")
        self._novel("Worm", "worm")

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertEqual(candidate.status, MergeCandidate.STATUS_PENDING)
        self.assertEqual(candidate.decision, MergeCandidate.DECISION_REVIEW)
        self.assertIn("title", candidate.signals)

    def test_placeholder_cover_is_ignored(self):
        a = self._novel("Alpha Story", "alpha")
        b = self._novel("Beta Story", "beta")
        for novel, slug in ((a, "alpha"), (b, "beta")):
            NovelFromSource.objects.create(
                novel=novel,
                external_source=self.es,
                title=novel.title,
                source_url=f"http://x/{slug}",
                cover_phash="f" * 16,
            )

        with override_settings(MERGE_PLACEHOLDER_MIN_NOVELS=2):
            call_command("find_merge_candidates", trigram_min=-1)

        self.assertFalse(MergeCandidate.objects.exists())

    def test_rejected_pair_is_not_requeued(self):
        a = self._novel("Same Title", "same-a")
        b = self._novel("Same Title", "same-b")
        MergeCandidate.objects.create(
            novel_a=a, novel_b=b, title_a=a.title, title_b=b.title,
            status=MergeCandidate.STATUS_REJECTED,
        )

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertEqual(candidate.status, MergeCandidate.STATUS_REJECTED)


class MergeCandidateReviewViewTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        user = get_user_model().objects.create_superuser("admin", "a@a.com", "pw")
        self.client.force_login(user)
        self.es = ExternalSource.objects.create(source_name="site")
        self.a = Novel.objects.create(title="Worm (Parahumans #1)", slug="worm-para", novel_path="worm-para")
        self.b = Novel.objects.create(title="Worm", slug="worm", novel_path="worm")
        self.make_source(self.a, self.es, "Worm (Parahumans #1)", "http://x/a", "worm-para", "site")
        self.make_source(self.b, self.es, "Worm", "http://x/b", "worm", "site")
        self.candidate = MergeCandidate.objects.create(
            novel_a=self.a,
            novel_b=self.b,
            title_a=self.a.title,
            title_b=self.b.title,
            certainty=0.9,
        )

    def review_url(self):
        return reverse("admin:lncrawler_api_mergecandidate_review")

    def test_page_shows_the_highest_certainty_candidate(self):
        response = self.client.get(self.review_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Worm (Parahumans #1)")
        self.assertContains(response, "Worm")

    def test_merge_action_merges_and_advances(self):
        response = self.client.post(
            self.review_url(), {"candidate": str(self.candidate.pk), "action": "merge"}
        )
        self.assertRedirects(response, self.review_url())
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_MERGED)
        self.assertEqual(Novel.objects.count(), 1)

    def test_reject_action_marks_rejected(self):
        self.client.post(
            self.review_url(), {"candidate": str(self.candidate.pk), "action": "reject"}
        )
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_REJECTED)

    def test_skip_action_leaves_the_candidate_pending(self):
        self.client.post(
            self.review_url(), {"candidate": str(self.candidate.pk), "action": "skip"}
        )
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_PENDING)

    def test_changelist_exposes_the_review_button(self):
        response = self.client.get(
            reverse("admin:lncrawler_api_mergecandidate_changelist")
        )
        self.assertContains(response, self.review_url())
