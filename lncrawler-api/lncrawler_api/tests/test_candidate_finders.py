"""Tests for the finders, the blocks they read, the manual merge records and the author block.

Covers ``candidate_blocks``, ``find_author_candidates``, ``find_merge_candidates``,
``find_r18_candidates`` (``tag_r18_service``), ``manual_merge`` and ``author_block_service``.
"""

import hashlib
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from ..models import Author, Candidate, ExternalSource, NovelFromSource, Tag
from ..services.author_block_service import block_authors
from ..services.author_merge_service import merge_authors
from ..services.candidate_blocks import blocked_pairs, pair_key
from ..services.merge_common import sorted_pk_signature
from ..services.merge_service import merge_novels, merge_tags
from .helpers import MergeTestCase, make_novel


def row(kind, target_ids, status=Candidate.STATUS_PENDING, **extra):
    """A candidate naming ``target_ids``, with a signature no other row has."""
    return Candidate.objects.create(
        kind=kind,
        target_ids=[str(pk) if isinstance(pk, uuid.UUID) else pk for pk in target_ids],
        target_names=[],
        signature=hashlib.sha1(uuid.uuid4().bytes).hexdigest(),
        status=status,
        **extra,
    )


def pair_row(kind, pks, status=Candidate.STATUS_PENDING, **extra):
    """A candidate for the pair ``pks`` under the finder's own signature."""
    return Candidate.objects.create(
        kind=kind,
        target_ids=list(pks),
        target_names=[],
        signature=sorted_pk_signature(pks),
        status=status,
        **extra,
    )


def source_on(novel, url, site):
    return NovelFromSource.objects.create(
        novel=novel,
        external_source=ExternalSource.objects.create(source_name=site),
        title=novel.title,
        source_url=url,
        language="en",
    )


class BlockedPairsTests(TestCase):
    def test_rejected_pair_is_blocked(self):
        row(Candidate.KIND_AUTHOR_MERGE, [1, 2], Candidate.STATUS_REJECTED)
        self.assertEqual(blocked_pairs(Candidate.KIND_AUTHOR_MERGE), {pair_key(1, 2)})

    def test_undone_pair_is_blocked(self):
        row(Candidate.KIND_AUTHOR_MERGE, [1, 2], Candidate.STATUS_UNDONE)
        self.assertEqual(blocked_pairs(Candidate.KIND_AUTHOR_MERGE), {pair_key(1, 2)})

    def test_pending_pair_is_not_blocked(self):
        row(Candidate.KIND_AUTHOR_MERGE, [1, 2], Candidate.STATUS_PENDING)
        self.assertEqual(blocked_pairs(Candidate.KIND_AUTHOR_MERGE), set())

    def test_other_kinds_are_not_counted(self):
        row(Candidate.KIND_TAG_MERGE, [1, 2], Candidate.STATUS_REJECTED)
        self.assertEqual(blocked_pairs(Candidate.KIND_AUTHOR_MERGE), set())

    def test_merge_moves_the_blocked_member(self):
        # Author 1 was refused against 3. Then 1 was merged into 2: the block now stands on 2.
        row(Candidate.KIND_AUTHOR_MERGE, [1, 3], Candidate.STATUS_REJECTED)
        row(
            Candidate.KIND_AUTHOR_MERGE, [1, 2], Candidate.STATUS_APPLIED,
            undo=[{"type": "author_merge", "source_id": 1, "target_id": 2}],
        )
        self.assertEqual(blocked_pairs(Candidate.KIND_AUTHOR_MERGE), {pair_key(2, 3)})

    def test_chain_of_merges_is_followed(self):
        # 1 -> 2 and then 2 -> 4: the block on 1 now stands on 4.
        row(Candidate.KIND_AUTHOR_MERGE, [1, 3], Candidate.STATUS_REJECTED)
        row(
            Candidate.KIND_AUTHOR_MERGE, [1, 2], Candidate.STATUS_APPLIED,
            undo=[{"type": "author_merge", "source_id": 1, "target_id": 2}],
        )
        row(
            Candidate.KIND_AUTHOR_MERGE, [2, 4], Candidate.STATUS_APPLIED,
            undo=[{"type": "author_merge", "source_id": 2, "target_id": 4}],
        )
        self.assertEqual(blocked_pairs(Candidate.KIND_AUTHOR_MERGE), {pair_key(3, 4)})

    def test_rejected_tag_cluster_blocks_only_its_proposed_sets(self):
        # The reviewer saw {1, 2} proposed; 3 and 4 were in the cluster but never put together.
        row(
            Candidate.KIND_TAG_MERGE, [1, 2, 3, 4], Candidate.STATUS_REJECTED,
            verdict={"answer": "yes", "sets": [{"members": [1, 2], "canonical": "a", "confidence": 0.99}]},
        )
        self.assertEqual(blocked_pairs(Candidate.KIND_TAG_MERGE), {pair_key(1, 2)})

    def test_tag_cluster_with_no_set_blocks_nothing(self):
        row(
            Candidate.KIND_TAG_MERGE, [1, 2, 3], Candidate.STATUS_REJECTED,
            verdict={"answer": "no", "sets": []},
        )
        self.assertEqual(blocked_pairs(Candidate.KIND_TAG_MERGE), set())


class AuthorFinderTests(TestCase):
    def test_normalized_twins_are_queued_and_not_merged(self):
        first = Author.objects.create(name="Tomato Eater")
        second = Author.objects.create(name="tomato  eater")

        call_command("find_author_candidates", stdout=StringIO())

        self.assertEqual(Author.objects.count(), 2)
        queued = Candidate.objects.get(kind=Candidate.KIND_AUTHOR_MERGE)
        self.assertEqual(queued.status, Candidate.STATUS_PENDING)
        self.assertEqual(queued.signals["rule"], "normalized")
        self.assertEqual(sorted(queued.target_ids), sorted([first.pk, second.pk]))

    def test_rejected_pair_is_not_queued_again(self):
        first = Author.objects.create(name="Tomato Eater")
        second = Author.objects.create(name="tomato  eater")
        pair_row(
            Candidate.KIND_AUTHOR_MERGE, [first.pk, second.pk], Candidate.STATUS_REJECTED,
        )

        call_command("find_author_candidates", stdout=StringIO())

        self.assertEqual(Candidate.objects.filter(kind=Candidate.KIND_AUTHOR_MERGE).count(), 1)
        self.assertEqual(
            Candidate.objects.get(kind=Candidate.KIND_AUTHOR_MERGE).status,
            Candidate.STATUS_REJECTED,
        )


class NovelFinderTests(MergeTestCase):
    def test_pair_sharing_a_source_url_is_queued(self):
        first = make_novel("First Work", "first-work")
        second = make_novel("Second Work", "second-work")
        source_on(first, "http://shared/1", "site-a")
        source_on(second, "http://shared/1", "site-b")

        call_command("find_merge_candidates", stdout=StringIO())

        queued = Candidate.objects.get(kind=Candidate.KIND_NOVEL_MERGE)
        self.assertEqual(queued.status, Candidate.STATUS_PENDING)
        self.assertEqual(queued.signature, sorted_pk_signature([str(first.pk), str(second.pk)]))

    def test_pair_a_human_rejected_is_not_proposed_again(self):
        first = make_novel("First Work", "first-work")
        second = make_novel("Second Work", "second-work")
        source_on(first, "http://shared/1", "site-a")
        source_on(second, "http://shared/1", "site-b")
        pair_row(
            Candidate.KIND_NOVEL_MERGE, [str(first.pk), str(second.pk)],
            Candidate.STATUS_REJECTED,
        )

        call_command("find_merge_candidates", stdout=StringIO())

        self.assertEqual(Candidate.objects.filter(kind=Candidate.KIND_NOVEL_MERGE).count(), 1)

    def test_undecided_pending_row_below_the_line_is_removed(self):
        first = make_novel("Alpha Tale", "alpha-tale")
        second = make_novel("Zeta Story", "zeta-story")
        stale = pair_row(
            Candidate.KIND_NOVEL_MERGE, [str(first.pk), str(second.pk)],
        )

        out = StringIO()
        call_command("find_merge_candidates", stdout=out)

        self.assertFalse(Candidate.objects.filter(pk=stale.pk).exists())
        self.assertIn("1 stale removed", out.getvalue())

    def test_claimed_row_is_left_to_the_runner(self):
        from django.utils import timezone

        first = make_novel("Alpha Tale", "alpha-tale")
        second = make_novel("Zeta Story", "zeta-story")
        claimed = pair_row(
            Candidate.KIND_NOVEL_MERGE, [str(first.pk), str(second.pk)],
            claimed_at=timezone.now(),
        )

        call_command("find_merge_candidates", stdout=StringIO())

        self.assertTrue(Candidate.objects.filter(pk=claimed.pk).exists())

    def test_open_row_naming_a_missing_novel_is_removed(self):
        first = make_novel("Alpha Tale", "alpha-tale")
        gone = str(uuid.uuid4())
        orphan = row(Candidate.KIND_NOVEL_MERGE, [str(first.pk), gone])

        out = StringIO()
        call_command("find_merge_candidates", stdout=out)

        self.assertFalse(Candidate.objects.filter(pk=orphan.pk).exists())
        self.assertIn("1 open row(s) of missing novels removed", out.getvalue())


class R18FinderTests(TestCase):
    def test_queues_non_adult_tags_up_to_the_limit_once(self):
        for name in ("Alpha", "Beta", "Gamma"):
            Tag.objects.create(name=name)
        Tag.objects.create(name="Already Adult", is_adult=True)

        call_command("find_r18_candidates", "--limit", "2", stdout=StringIO())
        self.assertEqual(Candidate.objects.filter(kind=Candidate.KIND_TAG_R18).count(), 2)

        call_command("find_r18_candidates", "--limit", "2", stdout=StringIO())
        queued = Candidate.objects.filter(kind=Candidate.KIND_TAG_R18)
        self.assertEqual(queued.count(), 3)
        self.assertEqual(sorted(c.target_names[0] for c in queued), ["Alpha", "Beta", "Gamma"])

    def test_a_tag_with_a_rejected_candidate_is_not_queued_again(self):
        tag = Tag.objects.create(name="Alpha")
        pair_row(Candidate.KIND_TAG_R18, [tag.pk], Candidate.STATUS_REJECTED)

        call_command("find_r18_candidates", stdout=StringIO())

        self.assertEqual(Candidate.objects.filter(kind=Candidate.KIND_TAG_R18).count(), 1)


class ManualMergeTests(MergeTestCase):
    def test_manual_novel_merge_marks_the_pending_pair_applied(self):
        source = make_novel("Old Name", "old-name")
        target = make_novel("New Name", "new-name")
        pending = pair_row(
            Candidate.KIND_NOVEL_MERGE, [str(source.pk), str(target.pk)],
            verdict={"answer": "yes"}, confidence=0.9,
        )

        source_pk = str(source.pk)

        merge_novels(source, target)

        pending.refresh_from_db()
        self.assertEqual(pending.status, Candidate.STATUS_APPLIED)
        self.assertEqual(pending.decided_by, Candidate.DECIDED_HUMAN)
        self.assertEqual(pending.verdict, {"answer": "yes"})
        self.assertEqual(len(pending.undo), 1)
        self.assertEqual(pending.undo[0]["type"], "novel_merge")
        self.assertEqual(pending.undo[0]["source_id"], source_pk)
        self.assertEqual(pending.undo[0]["slug"], "old-name")
        self.assertEqual(Candidate.objects.filter(kind=Candidate.KIND_NOVEL_MERGE).count(), 1)

    def test_manual_author_merge_reopens_a_rejected_pair_as_applied(self):
        source = Author.objects.create(name="Tomato Eater")
        target = Author.objects.create(name="Eater Tomato")
        rejected = pair_row(
            Candidate.KIND_AUTHOR_MERGE, [source.pk, target.pk], Candidate.STATUS_REJECTED,
        )

        source_pk = source.pk

        merge_authors(source, target)

        rejected.refresh_from_db()
        self.assertEqual(rejected.status, Candidate.STATUS_APPLIED)
        self.assertEqual(rejected.decided_by, Candidate.DECIDED_HUMAN)
        self.assertEqual(rejected.undo[-1]["type"], "author_merge")
        self.assertEqual(rejected.undo[-1]["source_id"], source_pk)

    def test_manual_author_merge_without_a_candidate_creates_one(self):
        source = Author.objects.create(name="Tomato Eater")
        target = Author.objects.create(name="Eater Tomato")

        merge_authors(source, target)

        created = Candidate.objects.get(kind=Candidate.KIND_AUTHOR_MERGE)
        self.assertEqual(created.status, Candidate.STATUS_APPLIED)
        self.assertEqual(created.decided_by, Candidate.DECIDED_HUMAN)
        self.assertEqual(len(created.undo), 1)

    def test_manual_tag_merge_marks_the_pending_pair_applied(self):
        source = Tag.objects.create(name="Old Tag")
        target = Tag.objects.create(name="New Tag")
        pending = pair_row(Candidate.KIND_TAG_MERGE, [source.pk, target.pk])

        merge_tags(source, target)

        pending.refresh_from_db()
        self.assertEqual(pending.status, Candidate.STATUS_APPLIED)
        self.assertEqual(pending.undo[0]["type"], "tag_merge")


class AuthorBlockTests(TestCase):
    def test_blocking_rejects_the_open_author_candidates(self):
        keep = Author.objects.create(name="Keep Me")
        blocked = Author.objects.create(name="Block Me")
        pending = row(Candidate.KIND_AUTHOR_MERGE, [keep.pk, blocked.pk])
        review = row(
            Candidate.KIND_AUTHOR_MERGE, [blocked.pk, keep.pk], Candidate.STATUS_REVIEW,
        )

        self.assertEqual(block_authors([blocked.pk]), 1)

        for candidate in (pending, review):
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
            self.assertEqual(candidate.decided_by, Candidate.DECIDED_HUMAN)
            self.assertEqual(candidate.reason, "author blocked")

    def test_blocking_releases_a_claim_in_flight(self):
        keep = Author.objects.create(name="Keep Me")
        blocked = Author.objects.create(name="Block Me")
        claimed = row(Candidate.KIND_AUTHOR_MERGE, [keep.pk, blocked.pk], claimed_at=timezone.now())

        block_authors([blocked.pk])

        claimed.refresh_from_db()
        self.assertEqual(claimed.status, Candidate.STATUS_REJECTED)
        self.assertIsNone(claimed.claimed_at)
