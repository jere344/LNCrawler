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

    def test_same_source_url_creates_a_candidate(self):
        # A renamed novel has no title overlap; the shared source URL still wins.
        a = self._novel("Old Name", "old-name")
        b = self._novel("Brand New Name", "brand-new-name")
        for novel, title in ((a, "Old Name"), (b, "Brand New Name")):
            NovelFromSource.objects.create(
                novel=novel, external_source=self.es, title=title, source_url="http://x/1"
            )

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertIn("src", candidate.signals)
        self.assertGreaterEqual(candidate.certainty, 0.99)

    def test_blank_source_urls_do_not_block_together(self):
        a = self._novel("Alpha", "alpha")
        b = self._novel("Beta", "beta")
        for novel, title in ((a, "Alpha"), (b, "Beta")):
            NovelFromSource.objects.create(
                novel=novel, external_source=self.es, title=title, source_url=""
            )

        call_command("find_merge_candidates", trigram_min=-1)

        self.assertFalse(MergeCandidate.objects.exists())


class SurvivorPickTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.es = ExternalSource.objects.create(source_name="site")

    def test_keeps_the_novel_with_more_chapters(self):
        from ..services.merge_service import pick_merge_survivor

        thin = Novel.objects.create(title="Thin", slug="thin", novel_path="thin")
        fat = Novel.objects.create(title="Fat", slug="fat", novel_path="fat")
        self.make_source(thin, self.es, "Thin", "http://x/1", "thin", "site", chapters=1)
        self.make_source(fat, self.es, "Fat", "http://x/2", "fat", "site", chapters=5)

        self.assertIs(pick_merge_survivor(thin, fat), fat)
        self.assertIs(pick_merge_survivor(fat, thin), fat)

    def test_merge_survives_a_stale_null_fk_candidate(self):
        # A prior merge can leave an audit row whose other FK is already NULL;
        # Postgres LEAST/GREATEST ignore NULL, so its effective pair key is
        # (B, B). Merging A into B nulls this active row's novel_a -> (B, B),
        # which must NOT collide with the stale row (the constraint is partial).
        from ..services.merge_service import merge_novels

        a = Novel.objects.create(title="A", slug="a", novel_path="a")
        b = Novel.objects.create(title="B", slug="b", novel_path="b")
        MergeCandidate.objects.create(
            novel_a=b, novel_b=None, title_a=b.title,
            status=MergeCandidate.STATUS_SKIPPED, certainty=0.5,
        )
        MergeCandidate.objects.create(
            novel_a=a, novel_b=b, title_a=a.title, title_b=b.title,
            status=MergeCandidate.STATUS_PENDING, certainty=0.9,
        )

        merge_novels(a, b)

        self.assertFalse(Novel.objects.filter(pk=a.pk).exists())
        self.assertTrue(Novel.objects.filter(pk=b.pk).exists())

    def test_deleting_a_novel_directly_survives_a_stale_null_fk_candidate(self):
        # Same SET_NULL collapse as above, but via the admin/model delete path
        # (Novel.delete()), not a merge.
        a = Novel.objects.create(title="A", slug="a", novel_path="a")
        b = Novel.objects.create(title="B", slug="b", novel_path="b")
        MergeCandidate.objects.create(
            novel_a=b, novel_b=None, title_a=b.title,
            status=MergeCandidate.STATUS_SKIPPED, certainty=0.5,
        )
        MergeCandidate.objects.create(
            novel_a=a, novel_b=b, title_a=a.title, title_b=b.title,
            status=MergeCandidate.STATUS_PENDING, certainty=0.9,
        )

        a.delete()

        self.assertFalse(Novel.objects.filter(pk=a.pk).exists())
        self.assertTrue(Novel.objects.filter(pk=b.pk).exists())


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

    def test_merge_keeps_the_most_complete_side(self):
        # Both novels share one source URL (a rename/bad import): the merge must
        # survive the fuller copy and drop the thinner one.
        thin = Novel.objects.create(title="Fate Points A", slug="fp-thin", novel_path="fp-thin")
        fat = Novel.objects.create(title="Fate Points B", slug="fp-fat", novel_path="fp-fat")
        self.make_source(thin, self.es, "Fate Points A", "http://rr/58682", "fp-thin", "site", chapters=1)
        self.make_source(fat, self.es, "Fate Points B", "http://rr/58682", "fp-fat", "site", chapters=5)
        c = MergeCandidate.objects.create(
            novel_a=thin, novel_b=fat, title_a=thin.title, title_b=fat.title, certainty=0.99
        )

        self.client.post(self.review_url(), {"candidate": str(c.pk), "action": "merge"})

        c.refresh_from_db()
        self.assertEqual(c.status, MergeCandidate.STATUS_MERGED)
        survivor = Novel.objects.get(pk=fat.pk)
        self.assertEqual(survivor.sources.get().chapters.count(), 5)
        self.assertFalse(Novel.objects.filter(pk=thin.pk).exists())

    def test_skip_action_leaves_the_candidate_pending(self):
        self.client.post(
            self.review_url(), {"candidate": str(self.candidate.pk), "action": "skip"}
        )
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_PENDING)

    def test_skip_advances_and_reset_restores(self):
        c = Novel.objects.create(title="Frieren", slug="frieren-c", novel_path="frieren-c")
        d = Novel.objects.create(title="Frieren", slug="frieren-d", novel_path="frieren-d")
        MergeCandidate.objects.create(
            novel_a=c, novel_b=d, title_a=c.title, title_b=d.title, certainty=0.4
        )

        self.client.post(
            self.review_url(), {"candidate": str(self.candidate.pk), "action": "skip"}
        )
        self.assertIn(
            str(self.candidate.pk),
            self.client.session.get("merge_review_skipped", []),
        )

        # The skipped candidate is gone from the pass; the next one shows instead.
        response = self.client.get(self.review_url())
        self.assertContains(response, "Frieren")
        self.assertContains(response, "40.0%")
        self.assertNotContains(response, "90.0%")

        # When the pass is exhausted the skipped ones can be reviewed again.
        self.client.post(self.review_url(), {"action": "reset"})
        response = self.client.get(self.review_url())
        self.assertContains(response, "90.0%")

    def test_changelist_exposes_the_review_button(self):
        response = self.client.get(
            reverse("admin:lncrawler_api_mergecandidate_changelist")
        )
        self.assertContains(response, self.review_url())
