"""Tests for the cross-source duplicate candidate finder."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from ..management.commands.find_merge_candidates import combo_certainty, normalize_text
from ..models import (
    AlternativeTitle,
    Author,
    ExternalSource,
    MergeCandidate,
    Novel,
    NovelFromSource,
)
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


class DiscriminantTests(MergeTestCase):
    """Sequel penalty and the path and chapter-length signals."""

    def setUp(self):
        super().setUp()
        self.es = ExternalSource.objects.create(source_name="site")
        self.other_es = ExternalSource.objects.create(source_name="other")

    def _novel(self, title, slug, path=None):
        return Novel.objects.create(title=title, slug=slug, novel_path=path or slug)

    def _review_all(self, **options):
        # review_low=0 keeps sub-threshold pairs so their signals can be checked.
        call_command("find_merge_candidates", review_low=0.0, **options)

    def test_wn_and_ln_editions_are_queued_for_merge(self):
        # WN and LN of one story are one novel: the edition is no penalty.
        self._novel("Foo (WN)", "foo-wn")
        self._novel("Foo (LN)", "foo-ln")

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertNotIn("edition_mismatch", candidate.signals)
        self.assertIn("title", candidate.signals)

    def test_sequel_is_not_queued_on_title_plus_author(self):
        # Trigram similarity plus a shared author would reach review; the sequel
        # number on one side is what keeps the pair out.
        a = self._novel("Dragon Quest", "dq")
        b = self._novel("Dragon Quest 2", "dq-2")
        for novel, es, title, url in (
            (a, self.es, "Dragon Quest", "http://x/dq"),
            (b, self.other_es, "Dragon Quest 2", "http://x/dq2"),
        ):
            self.make_source(novel, es, title, url, novel.slug, es.source_name)
            NovelFromSource.objects.get(novel=novel).authors.add(
                Author.objects.create(name="Shared Author")
            )

        call_command("find_merge_candidates")
        self.assertFalse(MergeCandidate.objects.exists())

        self._review_all()
        candidate = MergeCandidate.objects.get()
        self.assertIn("title", candidate.signals)
        self.assertIn("sequel_mismatch", candidate.signals)
        self.assertLess(candidate.certainty, 0.5)

    def test_same_source_url_is_queued_despite_edition_markers(self):
        a = self._novel("Foo (WN)", "foo-wn")
        b = self._novel("Foo (LN)", "foo-ln")
        self.make_source(a, self.es, "Foo (WN)", "http://x/1", "foo-wn", "site")
        self.make_source(b, self.es, "Foo (LN)", "http://x/1", "foo-ln", "site")

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertIn("src", candidate.signals)
        self.assertGreaterEqual(candidate.certainty, 0.99)

    def test_shared_novel_path_is_queued(self):
        self._novel("Alpha", "alpha", path="shared-folder")
        self._novel("Zeta", "zeta", path="shared-folder")

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertIn("path", candidate.signals)
        self.assertGreaterEqual(candidate.certainty, 0.99)

    def test_author_with_matching_chapter_counts_is_queued(self):
        self._add_translated_pair(chapters=10)

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertIn("author", candidate.signals)
        self.assertIn("chapters", candidate.signals)

    def test_author_alone_is_not_queued(self):
        self._add_translated_pair(chapters=3)

        call_command("find_merge_candidates", trigram_min=-1)

        self.assertFalse(MergeCandidate.objects.exists())

    def test_same_site_different_titles_is_not_penalised(self):
        # A shared novelupdates_url queues the pair; one site listing the two
        # under different titles is no longer a reason to hold it back.
        a = self._novel("Crimson Sky", "crimson")
        b = self._novel("Silent Harbor", "silent")
        for novel, title, url in (
            (a, "Crimson Sky", "http://x/crimson"),
            (b, "Silent Harbor", "http://x/silent"),
        ):
            NovelFromSource.objects.create(
                novel=novel, external_source=self.es, title=title, source_url=url,
                novelupdates_url="https://www.novelupdates.com/series/shared/",
            )

        call_command("find_merge_candidates", trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertNotIn("same_site", candidate.signals)
        self.assertIn("nu", candidate.signals)
        self.assertGreaterEqual(candidate.certainty, 0.9)

    def test_trigram_still_yields_a_title_signal(self):
        self._novel("Lord of the Mysteries", "lotm")
        self._novel("Lord of Mysteries", "lotm-2")

        self._review_all()

        candidate = MergeCandidate.objects.get()
        self.assertGreaterEqual(candidate.signals["title"], 0.4)

    def test_rerunning_does_not_duplicate_rows(self):
        self._novel("Alpha", "alpha", path="shared-folder")
        self._novel("Zeta", "zeta", path="shared-folder")

        call_command("find_merge_candidates", trigram_min=-1)
        call_command("find_merge_candidates", trigram_min=-1)

        self.assertEqual(MergeCandidate.objects.count(), 1)

    def _add_cover(self, novel, phash, url):
        NovelFromSource.objects.create(
            novel=novel, external_source=self.es, title=novel.title,
            source_url=url, cover_phash=phash,
        )

    def test_near_identical_covers_are_queued(self):
        # Unrelated titles: only the cover, 2 bits apart, connects the pair.
        a = self._novel("Alpha Story", "alpha")
        b = self._novel("Beta Tale", "beta")
        self._add_cover(a, "78d050524c5c3cb0", "http://x/alpha")
        self._add_cover(b, "78d050524c5c3cb3", "http://x/beta")

        self._review_all(trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertAlmostEqual(candidate.signals["phash"], 1 - 2 / 16)

    def test_distant_covers_are_not_matched(self):
        a = self._novel("Alpha Story", "alpha")
        b = self._novel("Beta Tale", "beta")
        self._add_cover(a, "78d050524c5c3cb0", "http://x/alpha")
        self._add_cover(b, "872fafadb3a3c34f", "http://x/beta")

        self._review_all(trigram_min=-1)

        self.assertFalse(MergeCandidate.objects.exists())

    def test_covers_at_the_max_distance_are_queued(self):
        # 6 bits spread over 6 different bytes: no 16-bit band survives intact.
        a = self._novel("Alpha Story", "alpha")
        b = self._novel("Beta Tale", "beta")
        self._add_cover(a, "78d050524c5c3cb0", "http://x/alpha")
        self._add_cover(b, "79d151534d5d3cb0", "http://x/beta")

        self._review_all(trigram_min=-1)

        candidate = MergeCandidate.objects.get()
        self.assertAlmostEqual(candidate.signals["phash"], 1 - 6 / 16)

    def test_near_flat_covers_only_match_exactly(self):
        # Blank-ish covers of unrelated novels land a few bits apart.
        a = self._novel("Alpha Story", "alpha")
        b = self._novel("Beta Tale", "beta")
        self._add_cover(a, "0000000010100000", "http://x/alpha")
        self._add_cover(b, "0000000010300800", "http://x/beta")

        self._review_all(trigram_min=-1)

        self.assertFalse(MergeCandidate.objects.filter(signals__has_key="phash").exists())

    def test_near_identical_placeholder_covers_are_ignored(self):
        # Three novels share one default cover, re-encoded slightly differently.
        novels = [
            self._novel("Alpha Story", "alpha"),
            self._novel("Beta Tale", "beta"),
            self._novel("Gamma Saga", "gamma"),
        ]
        for novel, phash in zip(novels, ("78d050524c5c3cb0", "78d050524c5c3cb1", "78d050524c5c3cb3")):
            self._add_cover(novel, phash, f"http://x/{novel.slug}")

        with override_settings(MERGE_PLACEHOLDER_MIN_NOVELS=3):
            self._review_all(trigram_min=-1)

        self.assertFalse(MergeCandidate.objects.filter(signals__has_key="phash").exists())

    def test_fuzzy_match_uses_source_titles(self):
        # Novel.title differs completely; only the source titles are similar.
        a = self._novel("Kingdom Rising", "kingdom")
        b = self._novel("Wang Guo", "wang-guo")
        self.make_source(a, self.es, "Lord of the Mysteries", "http://x/lotm-a", "kingdom", "site")
        self.make_source(b, self.other_es, "Lord of Mysteries", "http://x/lotm-b", "wang-guo", "other")

        self._review_all()

        candidate = MergeCandidate.objects.get()
        self.assertGreaterEqual(candidate.signals["title"], 0.4)

    def test_fuzzy_match_uses_alternative_titles(self):
        a = self._novel("Lord of the Mysteries", "lotm")
        b = self._novel("Gui Mi Zhi Zhu", "gmzz")
        self.make_source(b, self.other_es, "Gui Mi Zhi Zhu", "http://x/gmzz", "gmzz", "other")
        NovelFromSource.objects.get(novel=b).alternative_titles.add(
            AlternativeTitle.objects.create(name="Lord of Mysteries")
        )

        self._review_all()

        candidate = MergeCandidate.objects.get()
        self.assertGreaterEqual(candidate.signals["alt"], 0.4)

    def _add_translated_pair(self, chapters):
        # Different titles, so only the author and the chapter count connect them.
        author = Author.objects.create(name="Shared Author")
        for novel, es, title, url in (
            (self._novel("Kingdom", "kingdom"), self.es, "Kingdom", "http://x/k"),
            (self._novel("Wang Guo", "wang-guo"), self.other_es, "Wang Guo", "http://x/w"),
        ):
            self.make_source(novel, es, title, url, novel.slug, es.source_name, chapters=chapters)
            NovelFromSource.objects.get(novel=novel).authors.add(author)

