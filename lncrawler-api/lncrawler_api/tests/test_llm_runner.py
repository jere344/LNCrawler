"""Tests for the candidate runner (services/llm_tasks.py) and the human actions (services/candidate_service.py)."""

import hashlib
import json
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from ..models import Author, Candidate, ExternalSource, Novel, Tag
from ..services import candidate_service, llm_service, llm_tasks
from ..services.author_merge_service import merge_authors
from ..services.merge_service import fold_tag, merge_novels
from ..services.candidate_service import CandidateError
from ..services.llm_service import LLMError, RateLimited
from .helpers import MergeTestCase, make_novel
from .llm_helpers import llm_chain


def make_candidate(kind, target_ids, names=(), **extra):
    # Same shape as the finder signature: a hash, so UUID novel ids fit the 64 characters.
    signature = hashlib.sha1(",".join(sorted(str(pk) for pk in target_ids)).encode()).hexdigest()
    return Candidate.objects.create(
        kind=kind,
        target_ids=list(target_ids),
        target_names=list(names),
        signature=signature,
        **extra,
    )


def reply(payload):
    return json.dumps(payload), 10, "provider", None


class DecideRuleTests(SimpleTestCase):
    def test_confident_yes_is_applied(self):
        self.assertEqual(
            llm_tasks.decide("yes", 0.96, 0.95, []), (Candidate.STATUS_APPLIED, "")
        )

    def test_low_confidence_yes_waits_for_review(self):
        status, _reason = llm_tasks.decide("yes", 0.5, 0.95, [])
        self.assertEqual(status, Candidate.STATUS_REVIEW)

    def test_missing_confidence_counts_as_zero(self):
        status, _reason = llm_tasks.decide("yes", None, 0.95, [])
        self.assertEqual(status, Candidate.STATUS_REVIEW)

    def test_safeguard_sends_a_confident_yes_to_review(self):
        status, reason = llm_tasks.decide("yes", 0.99, 0.95, ["pair in a chain"])
        self.assertEqual((status, reason), (Candidate.STATUS_REVIEW, "pair in a chain"))

    def test_confident_no_is_rejected(self):
        self.assertEqual(llm_tasks.decide("no", 0.96, 0.95, []), (Candidate.STATUS_REJECTED, ""))

    def test_low_confidence_no_waits_for_review(self):
        status, _reason = llm_tasks.decide("no", 0.5, 0.95, [])
        self.assertEqual(status, Candidate.STATUS_REVIEW)

    def test_low_confidence_no_is_rejected_when_not_reviewed(self):
        status, _reason = llm_tasks.decide("no", 0.1, 0.85, [], review_uncertain_no=False)
        self.assertEqual(status, Candidate.STATUS_REJECTED)

    def test_unsure_waits_for_review(self):
        status, reason = llm_tasks.decide("unsure", 0.99, 0.95, [])
        self.assertEqual((status, reason), (Candidate.STATUS_REVIEW, "unsure"))


@override_settings(**llm_chain())
class RunnerTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.chat = mock.patch.object(llm_service, "chat").start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(llm_service, "can_afford", return_value=True).start()

    def run_all(self, **kwargs):
        return llm_tasks.run_queue(**kwargs)

    def release_backoff(self):
        Candidate.objects.update(not_before=None)

    def make_tags(self, *names):
        return [Tag.objects.create(name=name) for name in names]

    def r18_candidate(self, tag):
        return make_candidate("tag_r18", [tag.pk], [tag.name])

    def test_explicit_tag_is_flagged_and_omitted_tag_is_rejected(self):
        smut, romance = self.make_tags("Smut", "Romance")
        smut_candidate = self.r18_candidate(smut)
        romance_candidate = self.r18_candidate(romance)
        self.chat.return_value = reply({"tags": [{"id": smut.pk, "rating": "explicit", "confidence": 0.97}]})

        self.run_all(task_names=["tag_r18"])

        smut_candidate.refresh_from_db()
        romance_candidate.refresh_from_db()
        smut.refresh_from_db()
        self.assertEqual(smut_candidate.status, Candidate.STATUS_APPLIED)
        self.assertTrue(smut.is_adult)
        self.assertEqual(romance_candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(romance_candidate.decided_by, Candidate.DECIDED_LLM)

    def test_low_confidence_explicit_tag_waits_for_review(self):
        (edgy,) = self.make_tags("Edgy")
        candidate = self.r18_candidate(edgy)
        self.chat.return_value = reply({"tags": [{"id": edgy.pk, "rating": "explicit", "confidence": 0.5}]})

        self.run_all(task_names=["tag_r18"])

        candidate.refresh_from_db()
        edgy.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertFalse(edgy.is_adult)

    def test_claims_are_packed_per_kind(self):
        first, second = self.make_tags("First", "Second")
        self.r18_candidate(first)
        self.r18_candidate(second)
        self.chat.return_value = reply({"tags": []})

        self.run_all(task_names=["tag_r18"])

        self.assertEqual(self.chat.call_count, 1)
        self.assertEqual(self.chat.call_args.kwargs["candidate_ids"], list(
            Candidate.objects.order_by("pk").values_list("pk", flat=True)
        ))

    def test_three_failed_attempts_set_error(self):
        (tag,) = self.make_tags("Failing")
        candidate = self.r18_candidate(tag)
        self.chat.side_effect = LLMError("boom")

        for _ in range(3):
            self.release_backoff()
            self.run_all(task_names=["tag_r18"])

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_ERROR)
        self.assertEqual(candidate.attempts, 3)

    def test_rate_limit_keeps_attempts_and_stops_the_run(self):
        (tag,) = self.make_tags("Limited")
        candidate = self.r18_candidate(tag)
        self.chat.side_effect = RateLimited(retry_after=30)

        counts = self.run_all(task_names=["tag_r18"])

        candidate.refresh_from_db()
        self.assertTrue(counts["rate_limited"])
        self.assertEqual(candidate.attempts, 0)
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertGreater(candidate.not_before, timezone.now())

    def test_missing_answer_is_retried_alone(self):
        left = Author.objects.create(name="Alpha Author")
        right = Author.objects.create(name="Beta Author")
        other = Author.objects.create(name="Gamma Author")
        other_right = Author.objects.create(name="Delta Author")
        answered = make_candidate(
            "author_merge", [left.pk, right.pk], ["Alpha Author", "Beta Author"]
        )
        missing = make_candidate(
            "author_merge", [other.pk, other_right.pk], ["Gamma Author", "Delta Author"]
        )
        self.chat.return_value = reply({"results": [{
            "id": answered.pk, "names": "Alpha Author / Beta Author", "evidence": "other",
            "relation": "different", "confidence": 0.9,
        }]})

        self.run_all(task_names=["author_merge"])

        missing.refresh_from_db()
        self.assertEqual(missing.status, Candidate.STATUS_PENDING)
        self.assertEqual(missing.attempts, 1)
        self.release_backoff()
        self.chat.return_value = reply({"results": []})
        self.chat.side_effect = None
        self.run_all(task_names=["author_merge"])
        self.assertEqual(self.chat.call_args.kwargs["candidate_ids"], [missing.pk])

    def test_stuck_claim_is_reset_and_judged(self):
        (tag,) = self.make_tags("Stuck")
        candidate = self.r18_candidate(tag)
        Candidate.objects.filter(pk=candidate.pk).update(
            claimed_at=timezone.now() - timedelta(minutes=31)
        )
        self.chat.return_value = reply({"tags": []})

        self.run_all(task_names=["tag_r18"])

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertIsNone(candidate.claimed_at)

    def test_budget_stops_before_any_call(self):
        (tag,) = self.make_tags("Budget")
        candidate = self.r18_candidate(tag)
        with mock.patch.object(llm_service, "can_afford", return_value=False):
            counts = self.run_all(task_names=["tag_r18"])

        candidate.refresh_from_db()
        self.assertEqual(self.chat.call_count, 0)
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(counts["done"], 0)

    def test_late_answer_on_a_decided_candidate_is_dropped(self):
        (tag,) = self.make_tags("Decided")
        candidate = self.r18_candidate(tag)
        Candidate.objects.filter(pk=candidate.pk).update(
            status=Candidate.STATUS_REJECTED, decided_by=Candidate.DECIDED_HUMAN,
        )
        counts = {"done": 0, "failed": 0, "retry": 0, "rate_limited": False}
        judgement = {"answer": "yes", "confidence": 0.99, "reason": "", "rating": "explicit"}

        llm_tasks._settle_one(
            llm_tasks.REGISTRY["tag_r18"], candidate.pk, timezone.now(), judgement, None, counts, None,
        )

        candidate.refresh_from_db()
        tag.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertFalse(tag.is_adult)
        self.assertEqual(counts["done"], 0)

    def test_tag_r18_undo_clears_the_flag(self):
        (tag,) = self.make_tags("Undo me")
        candidate = self.r18_candidate(tag)
        self.chat.return_value = reply({"tags": [{"id": tag.pk, "rating": "explicit", "confidence": 0.97}]})
        self.run_all(task_names=["tag_r18"])
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)

        candidate_service.undo_candidate(candidate)

        candidate.refresh_from_db()
        tag.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_UNDONE)
        self.assertFalse(tag.is_adult)

    def test_human_reject_and_rejudge(self):
        (tag,) = self.make_tags("Human")
        candidate = self.r18_candidate(tag)
        with self.assertRaises(CandidateError):
            candidate_service.reject_candidate(candidate)
        Candidate.objects.filter(pk=candidate.pk).update(status=Candidate.STATUS_REVIEW)
        candidate.refresh_from_db()

        candidate_service.reject_candidate(candidate)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(candidate.decided_by, Candidate.DECIDED_HUMAN)

        candidate.attempts = 3
        candidate.status = Candidate.STATUS_ERROR
        candidate.save()
        candidate_service.rejudge_candidate(candidate)
        candidate.refresh_from_db()
        self.assertEqual((candidate.status, candidate.attempts), (Candidate.STATUS_PENDING, 0))

    def test_novel_undo_restores_old_id_and_slug(self):
        alpha = make_novel("Alpha", "alpha")
        beta = make_novel("Beta", "beta")
        site_a = ExternalSource.objects.create(source_name="site-a")
        site_b = ExternalSource.objects.create(source_name="site-b")
        self.make_source(alpha, site_a, "A", "https://a.example/n", alpha.novel_path, "src-a")
        self.make_source(beta, site_b, "B", "https://b.example/n", beta.novel_path, "src-b")
        candidate = make_candidate(
            "novel_merge", [str(alpha.pk), str(beta.pk)], ["Alpha", "Beta"],
            status=Candidate.STATUS_REVIEW, verdict={"answer": "yes", "confidence": 0.97},
        )

        candidate_service.apply_candidate(candidate)
        candidate.refresh_from_db()
        entry = candidate.undo[0]
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)

        candidate_service.undo_candidate(candidate)

        restored = Novel.objects.get(pk=entry["source_id"])
        self.assertEqual(restored.slug, entry["slug"])
        self.assertEqual(
            set(restored.sources.values_list("pk", flat=True)), set(entry["moved_source_ids"])
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_UNDONE)

    def test_novel_undo_refused_when_the_slug_is_taken(self):
        alpha = make_novel("Alpha", "alpha")
        beta = make_novel("Beta", "beta")
        site_a = ExternalSource.objects.create(source_name="site-a")
        site_b = ExternalSource.objects.create(source_name="site-b")
        self.make_source(alpha, site_a, "A", "https://a.example/n", alpha.novel_path, "src-a")
        self.make_source(beta, site_b, "B", "https://b.example/n", beta.novel_path, "src-b")
        candidate = make_candidate(
            "novel_merge", [str(alpha.pk), str(beta.pk)], ["Alpha", "Beta"],
            status=Candidate.STATUS_REVIEW, verdict={"answer": "yes", "confidence": 0.97},
        )
        candidate_service.apply_candidate(candidate)
        candidate.refresh_from_db()
        make_novel("Squatter", candidate.undo[0]["slug"])

        with self.assertRaises(CandidateError):
            candidate_service.undo_candidate(candidate)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)


@override_settings(**llm_chain())
class DropTargetGoneTests(MergeTestCase):
    """Open candidates whose target is gone are deleted, never closed as system."""

    def setUp(self):
        super().setUp()
        self.chat = mock.patch.object(llm_service, "chat").start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(llm_service, "can_afford", return_value=True).start()
        self.chat.return_value = reply({"tags": [], "groups": [], "results": []})

    def test_gone_tag_is_deleted_and_the_rest_of_the_batch_is_judged(self):
        gone, alive = Tag.objects.create(name="Gone"), Tag.objects.create(name="Alive")
        gone_candidate = make_candidate("tag_r18", [gone.pk], [gone.name])
        alive_candidate = make_candidate("tag_r18", [alive.pk], [alive.name])
        gone.delete()

        llm_tasks.run_queue(task_names=["tag_r18"])

        self.assertFalse(Candidate.objects.filter(pk=gone_candidate.pk).exists())
        alive_candidate.refresh_from_db()
        self.assertEqual(alive_candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(self.chat.call_args.kwargs["candidate_ids"], [alive_candidate.pk])

    def test_tag_already_adult_is_deleted_without_a_call(self):
        tag = Tag.objects.create(name="Already", is_adult=True)
        candidate = make_candidate("tag_r18", [tag.pk], [tag.name])

        llm_tasks.run_queue(task_names=["tag_r18"])

        self.assertFalse(Candidate.objects.filter(pk=candidate.pk).exists())
        self.assertEqual(self.chat.call_count, 0)

    def test_a_novel_merge_that_outlives_its_claim_is_still_recorded(self):
        alpha, beta = make_novel("Alpha", "alpha"), make_novel("Beta", "beta")
        self.make_source(alpha, ExternalSource.objects.create(source_name="site-a"), "A",
                         "https://a.example/n", alpha.novel_path, "src-a")
        self.make_source(beta, ExternalSource.objects.create(source_name="site-b"), "B",
                         "https://b.example/n", beta.novel_path, "src-b")
        candidate = make_candidate("novel_merge", [str(alpha.pk), str(beta.pk)], ["Alpha", "Beta"])
        self.chat.return_value = reply({"same": True, "confidence": 0.99, "reason": "same work"})
        original = llm_tasks.NovelMergeTask.apply_change

        def slow_merge(task, cand, judgement):
            # A stuck reset takes the claim while the merge runs.
            Candidate.objects.filter(pk=cand.pk).update(claimed_at=None)
            return original(task, cand, judgement)

        with mock.patch.object(llm_tasks.NovelMergeTask, "apply_change", slow_merge):
            llm_tasks.run_queue(task_names=["novel_merge"])

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(candidate.undo[0]["type"], "novel_merge")

    def test_novel_pair_with_a_missing_novel_is_deleted(self):
        alpha, beta = make_novel("Alpha", "alpha"), make_novel("Beta", "beta")
        candidate = make_candidate(
            "novel_merge", [str(alpha.pk), str(beta.pk)], ["Alpha", "Beta"],
        )
        Novel.objects.filter(pk=beta.pk).delete()

        llm_tasks.run_queue(task_names=["novel_merge"])

        self.assertFalse(Candidate.objects.filter(pk=candidate.pk).exists())
        self.assertEqual(self.chat.call_count, 0)

    def test_tag_pair_with_one_live_tag_is_deleted(self):
        left, right = Tag.objects.create(name="Left"), Tag.objects.create(name="Right")
        candidate = make_candidate("tag_merge", [left.pk, right.pk], [left.name, right.name])
        right.delete()

        llm_tasks.run_queue(task_names=["tag_merge"])

        self.assertFalse(Candidate.objects.filter(pk=candidate.pk).exists())
        self.assertEqual(self.chat.call_count, 0)

    def test_author_pair_with_a_missing_author_is_deleted(self):
        left, right = Author.objects.create(name="Left Author"), Author.objects.create(name="Right Author")
        candidate = make_candidate(
            "author_merge", [left.pk, right.pk], [left.name, right.name],
        )
        right.delete()

        llm_tasks.run_queue(task_names=["author_merge"])

        self.assertFalse(Candidate.objects.filter(pk=candidate.pk).exists())
        self.assertEqual(self.chat.call_count, 0)

    def test_merge_authors_deletes_other_open_pairs_naming_the_source(self):
        a, b, c = (Author.objects.create(name=name) for name in ("Ann", "Bea", "Cat"))
        applying = make_candidate("author_merge", [a.pk, b.pk], ["Ann", "Bea"], status=Candidate.STATUS_REVIEW)
        open_pair = make_candidate("author_merge", [b.pk, c.pk], ["Bea", "Cat"], status=Candidate.STATUS_PENDING)
        applied_pair = make_candidate("author_merge", [a.pk, c.pk], ["Ann", "Cat"], status=Candidate.STATUS_APPLIED)

        merge_authors(b, a, candidate=applying)

        self.assertTrue(Candidate.objects.filter(pk=applying.pk).exists())
        self.assertFalse(Candidate.objects.filter(pk=open_pair.pk).exists())
        applied_pair.refresh_from_db()
        self.assertEqual(applied_pair.status, Candidate.STATUS_APPLIED)

    def test_merge_novels_deletes_open_pairs_naming_the_source(self):
        alpha, beta, gamma = make_novel("Alpha", "alpha"), make_novel("Beta", "beta"), make_novel("Gamma", "gamma")
        open_pair = make_candidate(
            "novel_merge", [str(beta.pk), str(gamma.pk)], ["Beta", "Gamma"], status=Candidate.STATUS_PENDING,
        )
        applied_pair = make_candidate(
            "novel_merge", [str(alpha.pk), str(beta.pk)], ["Alpha", "Beta"], status=Candidate.STATUS_APPLIED,
        )

        merge_novels(beta, alpha)

        self.assertFalse(Candidate.objects.filter(pk=open_pair.pk).exists())
        applied_pair.refresh_from_db()
        self.assertEqual(applied_pair.status, Candidate.STATUS_APPLIED)

    def test_fold_tag_deletes_open_tag_candidates_naming_the_source(self):
        one, two, three = (Tag.objects.create(name=name) for name in ("One", "Two", "Three"))
        open_merge = make_candidate("tag_merge", [one.pk, two.pk], ["One", "Two"], status=Candidate.STATUS_PENDING)
        open_r18 = make_candidate("tag_r18", [one.pk], ["One"], status=Candidate.STATUS_REVIEW)
        applied_merge = make_candidate("tag_merge", [two.pk, three.pk], ["Two", "Three"], status=Candidate.STATUS_APPLIED)

        fold_tag(one, two)

        self.assertFalse(Candidate.objects.filter(pk=open_merge.pk).exists())
        self.assertFalse(Candidate.objects.filter(pk=open_r18.pk).exists())
        applied_merge.refresh_from_db()
        self.assertEqual(applied_merge.status, Candidate.STATUS_APPLIED)


class ReviewFixTests(MergeTestCase):
    """Cases the review of the change found untested."""

    def _candidate(self, kind, target_ids, **extra):
        return Candidate.objects.create(
            kind=kind,
            target_ids=target_ids,
            target_names=[],
            signature=hashlib.sha1(json.dumps([kind, target_ids, extra.get("status", "")]).encode()).hexdigest(),
            **extra,
        )

    def test_copied_request_log_rows_do_not_count_against_the_budget(self):
        # Migration 0097 copies the old request log with no provider; the usage rows carry the budget.
        LLMCall = Candidate._meta.get_field("llm_call").related_model
        LLMCall.objects.create(kind="tag_merge", provider=llm_service.REQUEST_LOG_PROVIDER, tokens=0)
        LLMCall.objects.create(kind="tag_merge", provider="p", tokens=10)
        self.assertEqual(llm_service.requests_used_today(), 1)
        self.assertEqual(llm_service.tokens_used_today(), 10)

    def test_undo_after_a_second_apply_reverses_only_the_new_entry(self):
        tag = Tag.objects.create(name="Smut", is_adult=True)
        candidate = self._candidate(
            Candidate.KIND_TAG_R18, [tag.pk], status=Candidate.STATUS_APPLIED,
            undo=[{"type": "tag_r18", "tag_id": tag.pk}],
        )
        candidate_service.undo_candidate(candidate)
        candidate.refresh_from_db()
        self.assertTrue(candidate.undo[0]["undone_at"])

        # Applied again (here by hand): a second entry is appended to the same row.
        candidate.status = Candidate.STATUS_APPLIED
        candidate.undo = [*candidate.undo, {"type": "tag_r18", "tag_id": tag.pk}]
        candidate.save()
        with mock.patch.object(candidate_service, "_undo_entry", wraps=candidate_service._undo_entry) as undo_entry:
            candidate_service.undo_candidate(candidate)
        self.assertEqual(undo_entry.call_count, 1)

    def test_undo_refuses_a_change_with_nothing_recorded(self):
        # A novel merge copied from the old tables: it has no undo entries.
        candidate = self._candidate(
            Candidate.KIND_NOVEL_MERGE, ["a", "b"], status=Candidate.STATUS_APPLIED, undo=[],
        )
        with self.assertRaisesRegex(CandidateError, "Nothing was recorded"):
            candidate_service.undo_candidate(candidate)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)

    def test_redecide_refuses_a_verdict_without_an_answer(self):
        candidate = self._candidate(
            Candidate.KIND_TAG_R18, [1], status=Candidate.STATUS_REVIEW,
            decided_by=Candidate.DECIDED_LLM, verdict="garbage",
        )
        with self.assertRaisesRegex(CandidateError, "re-judge"):
            candidate_service.redecide_candidate(candidate)

    def test_a_novel_in_another_pair_under_review_is_a_chain(self):
        a, b, c = make_novel("A", "a"), make_novel("B", "b"), make_novel("C", "c")
        candidate = self._candidate(Candidate.KIND_NOVEL_MERGE, [str(a.pk), str(b.pk)])
        self._candidate(Candidate.KIND_NOVEL_MERGE, [str(b.pk), str(c.pk)], status=Candidate.STATUS_REVIEW)
        task = llm_tasks.REGISTRY[Candidate.KIND_NOVEL_MERGE]
        self.assertEqual(len(task.safeguards(candidate, {"answer": "yes"})), 1)


@override_settings(**llm_chain())
class RoundTwoFixTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.chat = mock.patch.object(llm_service, "chat").start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(llm_service, "can_afford", return_value=True).start()

    def test_a_crash_while_preparing_releases_the_batch(self):
        candidate = make_candidate("novel_merge", ["x", "y"], ["X", "Y"])
        with mock.patch.object(llm_tasks.NovelMergeTask, "prepare", side_effect=RuntimeError("bad row")):
            llm_tasks.run_queue(task_names=["novel_merge"])

        candidate.refresh_from_db()
        self.assertIsNone(candidate.claimed_at)
        self.assertEqual(candidate.attempts, 1)
        self.assertIn("bad row", candidate.reason)
        self.chat.assert_not_called()

    def test_a_novel_candidate_without_two_ids_is_dropped(self):
        candidate = make_candidate("novel_merge", [], [])
        llm_tasks.run_queue(task_names=["novel_merge"])
        self.assertFalse(Candidate.objects.filter(pk=candidate.pk).exists())
        self.chat.assert_not_called()

    def test_an_undone_merge_entry_is_not_followed(self):
        from ..services.candidate_blocks import blocked_pairs, pair_key

        make_candidate("author_merge", [1, 3], status=Candidate.STATUS_REJECTED)
        make_candidate(
            "author_merge", [1, 2], status=Candidate.STATUS_APPLIED,
            undo=[{"type": "author_merge", "source_id": 1, "target_id": 2, "undone_at": "2026-01-01T00:00:00"}],
        )
        self.assertEqual(blocked_pairs(Candidate.KIND_AUTHOR_MERGE), {pair_key(1, 3)})


class MigrationFallbackTests(SimpleTestCase):
    def test_a_novel_row_that_failed_to_convert_keeps_its_pair(self):
        import importlib
        from collections import Counter
        from types import SimpleNamespace

        migration = importlib.import_module("lncrawler_api.migrations.0097_candidate_data")
        row = SimpleNamespace(pk="old", novel_a_id="a-id", novel_b_id="b-id", status="pending")

        spec = migration._fallback(migration.KIND_NOVEL, row, Counter())

        self.assertEqual(spec["target_ids"], ["a-id", "b-id"])
        self.assertEqual(spec["status"], "pending")
        self.assertFalse(spec["signature"].startswith("legacy:"))


@override_settings(**llm_chain())
class DecidedRowTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.chat = mock.patch.object(llm_service, "chat").start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(llm_service, "can_afford", return_value=True).start()

    def test_a_decided_candidate_is_never_sent_or_changed_again(self):
        tag = Tag.objects.create(name="Smut")
        decided = make_candidate(
            "tag_r18", [tag.pk], [tag.name], status=Candidate.STATUS_REJECTED,
            decided_by=Candidate.DECIDED_LLM, verdict={"answer": "no"},
        )
        before = Candidate.objects.filter(pk=decided.pk).values().get()

        llm_tasks.run_queue(task_names=["tag_r18"])
        with self.assertRaises(CandidateError):
            candidate_service.apply_candidate(decided)

        self.chat.assert_not_called()
        self.assertEqual(Candidate.objects.filter(pk=decided.pk).values().get(), before)
        self.assertFalse(Tag.objects.get(pk=tag.pk).is_adult)

    def test_a_failed_conversion_keeps_a_human_rejection(self):
        import importlib
        from collections import Counter
        from types import SimpleNamespace

        migration = importlib.import_module("lncrawler_api.migrations.0097_candidate_data")
        row = SimpleNamespace(pk="old", novel_a_id="a-id", novel_b_id="b-id", status="rejected")

        spec = migration._fallback(migration.KIND_NOVEL, row, Counter())

        self.assertEqual((spec["status"], spec["decided_by"]), ("rejected", "human"))

    def test_a_failed_conversion_keeps_a_merge_as_history(self):
        import importlib
        from collections import Counter
        from types import SimpleNamespace

        migration = importlib.import_module("lncrawler_api.migrations.0097_candidate_data")
        row = SimpleNamespace(
            pk="old", novel_a_id=None, novel_a_id_snapshot="a-id", novel_b_id="b-id",
            status="merged", decision="auto", merged_at=None,
        )

        spec = migration._fallback(migration.KIND_NOVEL, row, Counter())

        self.assertEqual((spec["status"], spec["decided_by"]), ("applied", "llm"))
        self.assertFalse(spec.get("dropped"))
