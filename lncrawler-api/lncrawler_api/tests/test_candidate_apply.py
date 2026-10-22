"""Tests for applying and undoing candidates: the two-phase novel apply, novel undo,
the claim refusal, and the no-re-proposal rule after an undo.

Covers ``candidate_service`` (``_apply_two_phase``, ``_undo_novel``, ``_ensure_unclaimed``)
and the ``candidate_blocks`` reads after an undo.
"""

import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from ..models import Author, Candidate, ExternalSource, Novel, NovelFromSource, Tag
from ..services import llm_tasks
from ..services.candidate_blocks import blocked_pairs, pair_key
from ..services.candidate_service import (
    CandidateError,
    apply_candidate,
    redecide_candidate,
    reject_candidate,
    undo_candidate,
)
from ..services.author_merge_service import merge_authors
from ..services.merge_service import merge_tags
from .helpers import MergeTestCase, make_novel
from .test_candidate_finders import pair_row

YES = {"answer": "yes", "confidence": 0.9, "reason": "same work"}


def two_novels(test):
    """Two novels with two sources each, on four different sites: both sides move over."""
    first = make_novel("Alpha Tale", "alpha-tale")
    second = make_novel("Beta Tale", "beta-tale")
    for novel in (first, second):
        for site in ("site-1", "site-2"):
            test.make_source(
                novel, ExternalSource.objects.create(source_name=f"{novel.slug}-{site}"),
                novel.title, f"http://{novel.slug}/{site}",
                novel.slug, f"{novel.slug}-{site}",
            )
    return first, second


def novel_pair(first, second, status=Candidate.STATUS_REVIEW, **extra):
    extra.setdefault("verdict", YES)
    return pair_row(
        Candidate.KIND_NOVEL_MERGE, [str(first.pk), str(second.pk)], status, **extra,
    )


class TwoPhaseNovelApplyTests(TransactionTestCase):
    """``apply_in_transaction`` is False for novels: the change runs in autocommit."""

    make_source = MergeTestCase.make_source

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-merge-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        output.enable()
        self.addCleanup(output.disable)

    def test_change_runs_outside_a_transaction_with_the_claim_held(self):
        first, second = two_novels(self)
        candidate = novel_pair(first, second)
        original = llm_tasks.NovelMergeTask.apply_change
        seen = {}

        def probe(task, cand, judgement):
            seen["atomic"] = connection.in_atomic_block
            seen["claimed"] = Candidate.objects.get(pk=cand.pk).claimed_at is not None
            return original(task, cand, judgement)

        with mock.patch.object(llm_tasks.NovelMergeTask, "apply_change", probe):
            apply_candidate(candidate)

        self.assertFalse(seen["atomic"])
        self.assertTrue(seen["claimed"])
        candidate.refresh_from_db()
        self.assertIsNone(candidate.claimed_at)
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(candidate.decided_by, Candidate.DECIDED_HUMAN)

    def test_apply_merges_and_records_the_undo_entry(self):
        first, second = two_novels(self)
        candidate = novel_pair(first, second)

        apply_candidate(candidate)

        candidate.refresh_from_db()
        entry = candidate.undo[0]
        self.assertEqual(entry["type"], "novel_merge")
        self.assertEqual(len(entry["moved_source_ids"]), 2)
        self.assertEqual(Novel.objects.filter(pk__in=[first.pk, second.pk]).count(), 1)
        self.assertTrue(Novel.objects.filter(pk=entry["target_id"]).exists())

    def test_claimed_candidate_is_refused(self):
        first, second = two_novels(self)
        candidate = novel_pair(first, second, claimed_at=timezone.now())

        with self.assertRaisesMessage(CandidateError, "being judged"):
            apply_candidate(candidate)

        self.assertEqual(Novel.objects.filter(pk__in=[first.pk, second.pk]).count(), 2)

    def test_candidate_that_moved_on_is_refused(self):
        first, second = two_novels(self)
        candidate = novel_pair(first, second)
        # The in-memory copy still says review; the row was rejected meanwhile.
        Candidate.objects.filter(pk=candidate.pk).update(status=Candidate.STATUS_REJECTED)

        with self.assertRaisesMessage(CandidateError, "changed while it was being decided"):
            apply_candidate(candidate)

        self.assertEqual(Novel.objects.filter(pk__in=[first.pk, second.pk]).count(), 2)


class NovelUndoTests(MergeTestCase):
    make_source = MergeTestCase.make_source

    def applied(self):
        """A novel pair applied through the service; returns (candidate, entry)."""
        first, second = two_novels(self)
        candidate = novel_pair(first, second)
        apply_candidate(candidate)
        candidate.refresh_from_db()
        return candidate, candidate.undo[0]

    def test_undo_restores_the_novel_under_its_old_id(self):
        candidate, entry = self.applied()
        moved = list(NovelFromSource.objects.filter(pk__in=entry["moved_source_ids"]))

        undo_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_UNDONE)
        restored = Novel.objects.get(pk=entry["source_id"])
        self.assertEqual(restored.slug, entry["slug"])
        self.assertEqual(restored.title, entry["title"])
        for source in moved:
            source.refresh_from_db()
            self.assertEqual(str(source.novel_id), entry["source_id"])

    def test_undo_refused_when_the_moved_sources_are_gone(self):
        candidate, entry = self.applied()
        NovelFromSource.objects.filter(pk__in=entry["moved_source_ids"]).delete()

        with self.assertRaisesMessage(CandidateError, "no longer exist"):
            undo_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)

    def test_undo_refused_when_the_sources_are_spread_over_novels(self):
        candidate, entry = self.applied()
        other = make_novel("Gamma Tale", "gamma-tale")
        moved = entry["moved_source_ids"]
        NovelFromSource.objects.filter(pk=moved[0]).update(novel=other)

        with self.assertRaisesMessage(CandidateError, "spread over several novels"):
            undo_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertFalse(Novel.objects.filter(pk=entry["source_id"]).exists())

    def test_undo_refused_when_the_merged_away_id_is_taken(self):
        candidate, entry = self.applied()
        Novel.objects.create(pk=entry["source_id"], title="Taken", slug="taken-id")

        with self.assertRaisesMessage(CandidateError, "id is taken"):
            undo_candidate(candidate)

    def test_undo_refused_when_the_slug_is_taken(self):
        candidate, entry = self.applied()
        Novel.objects.create(title="Squatter", slug=entry["slug"])

        with self.assertRaises(CandidateError):
            undo_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)


class UndoBlocksReproposalTests(MergeTestCase):
    def test_undone_tag_merge_pair_is_blocked(self):
        source = Tag.objects.create(name="Old Tag")
        target = Tag.objects.create(name="New Tag")
        merge_tags(source, target)
        row = Candidate.objects.get(kind=Candidate.KIND_TAG_MERGE)

        undo_candidate(row)

        row.refresh_from_db()
        self.assertEqual(row.status, Candidate.STATUS_UNDONE)
        self.assertEqual(blocked_pairs(Candidate.KIND_TAG_MERGE), {pair_key(*row.target_ids)})

    def test_undone_author_merge_is_not_queued_again(self):
        source = Author.objects.create(name="Tomato Eater")
        target = Author.objects.create(name="tomato  eater")
        merge_authors(source, target)
        row = Candidate.objects.get(kind=Candidate.KIND_AUTHOR_MERGE)

        undo_candidate(row)
        call_command("find_author_candidates", stdout=StringIO())

        self.assertEqual(Candidate.objects.filter(kind=Candidate.KIND_AUTHOR_MERGE).count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.status, Candidate.STATUS_UNDONE)

    def test_claimed_review_candidate_cannot_be_rejected(self):
        candidate = pair_row(
            Candidate.KIND_TAG_MERGE, [1, 2], Candidate.STATUS_REVIEW,
            claimed_at=timezone.now(),
        )

        with self.assertRaisesMessage(CandidateError, "being judged"):
            reject_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)


class RedecideTests(TransactionTestCase):
    """``redecide_candidate`` runs the stored LLM verdict through the current rules."""

    make_source = MergeTestCase.make_source

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-merge-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        output.enable()
        self.addCleanup(output.disable)

    def test_rejected_llm_verdict_that_now_clears_the_threshold_is_applied(self):
        first, second = two_novels(self)
        candidate = novel_pair(
            first, second, status=Candidate.STATUS_REJECTED,
            verdict={"answer": "yes", "confidence": 0.99, "reason": "same work"},
            decided_by=Candidate.DECIDED_LLM,
        )

        redecide_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(candidate.decided_by, Candidate.DECIDED_LLM)
        self.assertEqual(Novel.objects.filter(pk__in=[first.pk, second.pk]).count(), 1)

    def test_review_verdict_below_the_threshold_stays_in_review(self):
        first, second = two_novels(self)
        candidate = novel_pair(
            first, second, decided_by=Candidate.DECIDED_LLM,
            verdict={"answer": "yes", "confidence": 0.5, "reason": "unsure"},
        )

        redecide_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(candidate.decided_by, "")
        self.assertEqual(Novel.objects.filter(pk__in=[first.pk, second.pk]).count(), 2)

    def test_rejected_verdict_is_rejected_again_as_llm(self):
        first, second = two_novels(self)
        candidate = novel_pair(
            first, second, status=Candidate.STATUS_REVIEW,
            verdict={"answer": "no", "confidence": 0.99, "reason": "different"},
            decided_by=Candidate.DECIDED_LLM,
        )

        redecide_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(candidate.decided_by, Candidate.DECIDED_LLM)

    def test_human_decision_is_refused(self):
        first, second = two_novels(self)
        candidate = novel_pair(
            first, second, status=Candidate.STATUS_REJECTED,
            decided_by=Candidate.DECIDED_HUMAN,
        )

        with self.assertRaisesMessage(CandidateError, "made by the LLM"):
            redecide_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
