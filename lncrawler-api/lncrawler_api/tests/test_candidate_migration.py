"""The 0097 data migration copies the old merge, LLM and undo tables into Candidate and LLMCall."""

import hashlib
import importlib
from datetime import timedelta

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from ..models import Candidate, LLMCall

migration = importlib.import_module("lncrawler_api.migrations.0097_candidate_data")

MIGRATE_FROM = [("lncrawler_api", "0095_mergecandidate_merged_at")]


def signature(*pks):
    return hashlib.sha1(",".join(str(pk) for pk in sorted(pks)).encode()).hexdigest()


class CandidateDataMigrationTests(TransactionTestCase):

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_FROM)
        self.old = executor.loader.project_state(MIGRATE_FROM).apps
        self.addCleanup(self._migrate_to_leaf)

    @staticmethod
    def _migrate_to_leaf():
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _set_created_at(self, model_name, pk, when):
        # auto_now_add fields cannot be set on create, so the test sets them afterwards.
        self.old.get_model("lncrawler_api", model_name).objects.filter(pk=pk).update(created_at=when)

    def _create_old_rows(self):
        Novel = self.old.get_model("lncrawler_api", "Novel")
        MergeCandidate = self.old.get_model("lncrawler_api", "MergeCandidate")
        Author = self.old.get_model("lncrawler_api", "Author")
        AuthorMergeCandidate = self.old.get_model("lncrawler_api", "AuthorMergeCandidate")
        AuthorMerge = self.old.get_model("lncrawler_api", "AuthorMerge")
        Tag = self.old.get_model("lncrawler_api", "Tag")
        TagCluster = self.old.get_model("lncrawler_api", "TagCluster")
        TagMerge = self.old.get_model("lncrawler_api", "TagMerge")
        TagNoMerge = self.old.get_model("lncrawler_api", "TagNoMerge")
        LLMUsage = self.old.get_model("lncrawler_api", "LLMUsage")
        LLMRequest = self.old.get_model("lncrawler_api", "LLMRequest")

        novels = [Novel.objects.create(title=f"Novel {i}", slug=f"novel-{i}") for i in range(1, 11)]
        n1, n2, n3, n4, n5, n6, n7, n8, n9, n10 = novels
        same = {"same": True, "confidence": 0.97}

        # Novel merges.
        mc_pending = MergeCandidate.objects.create(
            novel_a=n1, novel_b=n2, title_a="Novel 1", title_b="Novel 2", certainty=0.5,
            status="pending",
        )
        mc_merged = MergeCandidate.objects.create(
            novel_a=n3, novel_b=n4, status="merged", decision="auto",
            llm_verdict=same, llm_checked_at=timezone.now(), merged_at=timezone.now(),
        )
        mc_unknown = MergeCandidate.objects.create(novel_a=n5, novel_b=n6, status="approved")
        # Target deleted: the old FK is null, the snapshot still names the pair.
        mc_gone = MergeCandidate.objects.create(
            novel_a=None, novel_a_id_snapshot=n9.id, novel_b=n10, status="pending",
        )
        # Same pair as the next two rows: the applied one must win the signature.
        mc_dup_pending = MergeCandidate.objects.create(novel_a=n7, novel_b=n8, status="pending")
        mc_dup_applied = MergeCandidate.objects.create(
            novel_a=None, novel_a_id_snapshot=n7.id, novel_b=n8, status="merged",
            decision="auto", llm_verdict=same, merged_at=timezone.now(),
        )
        # Judged with an unusable verdict: back to pending, to be judged again.
        mc_broken = MergeCandidate.objects.create(
            novel_a=n1, novel_b=n10, status="pending", llm_verdict="garbage",
            llm_checked_at=timezone.now(),
        )
        mc_judged = MergeCandidate.objects.create(
            novel_a=n2, novel_b=n3, status="pending", llm_verdict={"same": True, "confidence": 0.9},
            llm_checked_at=timezone.now(),
        )

        # Author merges.
        author_1 = Author.objects.create(name="Author One")
        author_2 = Author.objects.create(name="Author Two")
        ac_applied = AuthorMergeCandidate.objects.create(
            signature="auth-applied", author_ids=[author_1.pk, author_2.pk],
            author_names=["Author One", "Author Two"], status="applied",
            llm_response=same, decided_at=timezone.now(),
        )
        AuthorMergeCandidate.objects.create(
            signature="auth-gone", author_ids=[author_1.pk, 999999],
            author_names=["Author One", "Gone"], status="pending",
        )
        AuthorMergeCandidate.objects.create(
            signature="auth-unknown", author_ids=[author_1.pk, author_2.pk], status="weird",
        )
        AuthorMergeCandidate.objects.create(
            signature="auth-broken", author_ids=[author_1.pk, author_2.pk], status="review",
            llm_response="{not json",
        )
        author_journal = AuthorMerge.objects.create(
            candidate=ac_applied, source_name="Author Two", source_id=author_2.pk,
            target=author_1, target_name="Author One", source_ids=[author_2.pk],
        )
        # Manual merge, no candidate: keeps its own applied/human candidate, not undoable.
        AuthorMerge.objects.create(
            candidate=None, source_name="Ghost", source_id=None, target=author_1,
            target_name="Author One", source_ids=[],
        )

        # Tag merges.
        tag_1 = Tag.objects.create(name="tag one", normalized="tag one")
        tag_2 = Tag.objects.create(name="tag two", normalized="tag two")
        tag_3 = Tag.objects.create(name="tag three", normalized="tag three")
        cluster_applied = TagCluster.objects.create(
            signature="tag-applied", tag_ids=[tag_1.pk, tag_2.pk], tag_names=["tag one", "tag two"],
            status="applied", judged_at=timezone.now(),
            llm_response={"sets": [{"members": ["tag one", "tag two"], "canonical": "tag one",
                                    "confidence": 0.96}]},
        )
        TagCluster.objects.create(
            signature="tag-nomerge", tag_ids=[tag_2.pk, tag_3.pk], tag_names=["tag two", "tag three"],
            status="no_merge", judged_at=timezone.now(), llm_response={"sets": []},
        )
        TagCluster.objects.create(
            signature="tag-gone", tag_ids=[tag_1.pk, 999999], tag_names=["tag one", "Gone"],
            status="review",
        )
        # NULL adult flags: the merge predates them, so undo must refuse it.
        TagMerge.objects.create(
            cluster=cluster_applied, kind="merge", source_name="tag two", target=tag_1,
            target_name="tag one", all_source_ids=[tag_2.pk], source_was_adult=None,
            target_was_adult=None,
        )
        # Manual admin merge with a flag set: its own applied/human candidate.
        TagMerge.objects.create(
            cluster=None, kind="merge", source_name="tag three", target=tag_1,
            target_name="tag one", all_source_ids=[tag_3.pk], source_was_adult=False,
            target_was_adult=False,
        )
        # Pair inside the refused tag-nomerge cluster: still copied (the cluster had no set).
        TagNoMerge.objects.create(tag_a=tag_2, tag_b=tag_3)
        # Pair outside any cluster: copied too.
        TagNoMerge.objects.create(tag_a=tag_1, tag_b=tag_3)

        # LLM history.
        usage_when = timezone.now().replace(microsecond=0) - timedelta(days=3)
        usage = LLMUsage.objects.create(purpose="novel_merge", provider="groq", tokens=120)
        self._set_created_at("LLMUsage", usage.pk, usage_when)

        tag_when = timezone.now().replace(microsecond=0) - timedelta(days=2)
        tag_request = LLMRequest.objects.create(
            task="tag_merge", target_type="tag_cluster", target_ids=[cluster_applied.pk],
            status="done", model="m", prompt_version="v1", raw_response="raw-tag",
            finished_at=tag_when,
        )
        self._set_created_at("LLMRequest", tag_request.pk, tag_when)

        pending_request = LLMRequest.objects.create(
            task="novel_merge", target_type="merge_candidate", target_ids=[str(mc_pending.pk)],
            status="pending", model="m", prompt_version="v1", raw_response="pending-raw",
        )
        failed_when = timezone.now().replace(microsecond=0) - timedelta(days=1)
        failed_request = LLMRequest.objects.create(
            task="novel_merge", target_type="merge_candidate", target_ids=[str(mc_pending.pk)],
            status="failed", model="m", prompt_version="v1", raw_response="raw-novel",
            error="boom", finished_at=failed_when,
        )

        self.rows = {
            "mc_pending": mc_pending, "mc_merged": mc_merged, "mc_unknown": mc_unknown,
            "mc_gone": mc_gone, "mc_dup_applied": mc_dup_applied, "mc_dup_pending": mc_dup_pending,
            "mc_broken": mc_broken, "mc_judged": mc_judged,
            "author_1": author_1, "author_2": author_2, "author_journal": author_journal,
            "tag_1": tag_1, "tag_2": tag_2, "tag_3": tag_3, "cluster_applied": cluster_applied,
            "usage_when": usage_when, "tag_when": tag_when, "failed_when": failed_when,
            "pending_request": pending_request, "failed_request": failed_request,
            "tag_request": tag_request, **{f"n{i}": novel for i, novel in enumerate(novels, 1)},
        }

    def test_old_rows_are_copied_with_the_mapping_and_fallbacks(self):
        self._create_old_rows()
        r = self.rows
        self._migrate_to_leaf()

        def get(kind, sig):
            return Candidate.objects.get(kind=kind, signature=sig)

        # Novel merges.
        pending = get("novel_merge", signature(r["n1"].pk, r["n2"].pk))
        self.assertEqual(pending.status, "pending")
        self.assertEqual(pending.certainty, 0.5)
        self.assertIsNone(pending.confidence)

        applied = get("novel_merge", signature(r["n3"].pk, r["n4"].pk))
        self.assertEqual((applied.status, applied.decided_by), ("applied", "llm"))
        self.assertEqual(applied.confidence, 0.97)

        unknown = get("novel_merge", signature(r["n5"].pk, r["n6"].pk))
        self.assertEqual(unknown.status, "pending")

        # Open row whose target is gone: not copied.
        self.assertFalse(Candidate.objects.filter(
            kind="novel_merge", signature=signature(r["n9"].pk, r["n10"].pk),
        ).exists())

        # Same signature twice: the applied one is kept, the pending one dropped.
        duplicated = Candidate.objects.filter(kind="novel_merge", signature=signature(r["n7"].pk, r["n8"].pk))
        self.assertEqual(duplicated.count(), 1)
        self.assertEqual(duplicated.get().status, "applied")

        broken = Candidate.objects.get(kind="novel_merge", verdict="garbage")
        self.assertEqual((broken.status, broken.confidence), ("pending", 0.0))

        judged = get("novel_merge", signature(r["n2"].pk, r["n3"].pk))
        self.assertEqual(judged.status, "review")
        self.assertEqual(judged.confidence, 0.9)
        # The answer key the runner and re-decide read is derived from the old verdict.
        self.assertEqual(judged.verdict["answer"], "yes")

        # Author merges.
        author = get("author_merge", "auth-applied")
        self.assertEqual((author.status, author.decided_by, author.confidence), ("applied", "llm", 0.97))
        self.assertFalse(Candidate.objects.filter(kind="author_merge", signature="auth-gone").exists())
        self.assertEqual(get("author_merge", "auth-unknown").status, "pending")
        broken_author = get("author_merge", "auth-broken")
        self.assertEqual((broken_author.status, broken_author.confidence), ("review", 0.0))

        # Tag merges.
        tag = get("tag_merge", "tag-applied")
        self.assertEqual((tag.status, tag.decided_by), ("applied", "llm"))
        self.assertEqual(tag.confidence, 0.96)
        self.assertEqual(get("tag_merge", "tag-nomerge").status, "rejected")
        self.assertEqual(get("tag_merge", "tag-nomerge").decided_by, "llm")
        self.assertEqual(tag.verdict["answer"], "yes")
        self.assertEqual(get("tag_merge", "tag-nomerge").verdict["answer"], "no")
        self.assertFalse(Candidate.objects.filter(kind="tag_merge", signature="tag-gone").exists())
        # Nothing is closed as system any more (only finder-rule merges keep it, as history).
        self.assertFalse(Candidate.objects.filter(decided_by="system").exclude(status="applied").exists())

        # Journals: folded into the candidate's undo list, with undoable flags.
        self.assertEqual(len(author.undo), 1)
        self.assertEqual(author.undo[0]["type"], "author_merge")
        self.assertEqual(author.undo[0]["legacy_id"], r["author_journal"].pk)
        self.assertNotEqual(author.undo[0].get("undoable"), False)
        manual_author = Candidate.objects.get(kind="author_merge", signature__startswith="manual:author:")
        self.assertEqual((manual_author.status, manual_author.decided_by), ("applied", "human"))
        self.assertIs(manual_author.undo[0]["undoable"], False)

        # Recorded before the R18 flags: still undoable, its flags left as they are.
        self.assertNotEqual(tag.undo[0].get("undoable"), False)
        self.assertIs(tag.undo[0]["adult_flags_unknown"], True)
        manual_tag = Candidate.objects.get(kind="tag_merge", signature__startswith="manual:tag:")
        self.assertEqual((manual_tag.status, manual_tag.decided_by), ("applied", "human"))
        self.assertNotIn("undoable", manual_tag.undo[0])

        # TagNoMerge: every pair becomes a rejected/human candidate of two tags.
        inside = sorted((r["tag_2"].pk, r["tag_3"].pk))
        self.assertEqual(get("tag_merge", f"nomerge:{inside[0]}:{inside[1]}").status, "rejected")
        free = sorted((r["tag_1"].pk, r["tag_3"].pk))
        nomerge = get("tag_merge", f"nomerge:{free[0]}:{free[1]}")
        self.assertEqual((nomerge.status, nomerge.decided_by), ("rejected", "human"))

        # LLM history: usage row keeps its date, the failed request is linked to its candidate.
        usage_call = LLMCall.objects.get(kind="novel_merge", tokens=120)
        self.assertEqual(usage_call.provider, "groq")
        self.assertEqual(usage_call.created_at, r["usage_when"])

        tag_call = LLMCall.objects.get(raw_response="raw-tag")
        self.assertEqual(tag_call.tokens, 0)
        self.assertEqual(tag_call.candidate_ids, [tag.pk])
        self.assertEqual(tag_call.created_at, r["tag_when"])
        self.assertEqual(Candidate.objects.get(pk=tag.pk).llm_call_id, tag_call.pk)

        failed_call = LLMCall.objects.get(error="boom")
        self.assertEqual(failed_call.created_at, r["failed_when"])
        self.assertEqual(failed_call.candidate_ids, [pending.pk])
        self.assertEqual(Candidate.objects.get(pk=pending.pk).llm_call_id, failed_call.pk)

        self.assertFalse(LLMCall.objects.filter(raw_response="pending-raw").exists())

    def test_rerunning_the_copy_adds_nothing(self):
        self._create_old_rows()
        self._migrate_to_leaf()

        candidates_before = Candidate.objects.count()
        calls_before = LLMCall.objects.count()
        undo_before = {c.pk: len(c.undo) for c in Candidate.objects.all()}

        migration.copy_candidates(apps, None)

        self.assertEqual(Candidate.objects.count(), candidates_before)
        self.assertEqual(LLMCall.objects.count(), calls_before)
        self.assertEqual({c.pk: len(c.undo) for c in Candidate.objects.all()}, undo_before)
