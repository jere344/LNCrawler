"""Tests for author normalization, script runs, merging and the author finder."""

import json
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ..models import source_links
from ..models.source_links import AUTHOR_IMPORT_ATTEMPTS, AuthorImportError, _set_source_authors
from ..models import (
    Author,
    AuthorAlias,
    Candidate,
    ExternalSource,
    Novel,
    NovelFromSource,
)
from ..services.author_block_service import block_authors, unblock_authors
from ..services.author_merge_service import AuthorMergeRefused, merge_authors
from ..services.candidate_service import undo_candidate
from ..services.llm_service import LLMParseError
from ..services.llm_tasks import REGISTRY, settle
from ..services.merge_common import sorted_pk_signature
from ..services.merge_service import MergeError
from ..utils.author_names import is_bracketed_original, normalize_author, romanization_fits
from ..views.novels_views import _author_ids


def author_rows():
    """Every author_merge candidate row, as the finder writes them."""
    return Candidate.objects.filter(kind=Candidate.KIND_AUTHOR_MERGE)


def pair_candidate(first, second, rule="cross_source", **extra):
    """A pending author_merge candidate for two authors, in the finder's order and signature."""
    first, second = sorted([first, second], key=lambda author: author.pk)
    return Candidate.objects.create(
        kind=Candidate.KIND_AUTHOR_MERGE,
        signature=sorted_pk_signature([first.pk, second.pk]),
        target_ids=[first.pk, second.pk],
        target_names=[first.name, second.name],
        signals={"rule": rule},
        **extra,
    )


def judge_author(candidate, relation, names=None, confidence=0.99):
    """Settle ``candidate`` with one judge reply about it, as the runner does for one pair."""
    task = REGISTRY["author_merge"]
    names = names or " / ".join(candidate.target_names)
    content = json.dumps({"results": [{
        "id": candidate.pk, "names": names, "evidence": "", "relation": relation,
        "confidence": confidence,
    }]})
    judged = task.parse([candidate], None, content)
    settle(task, candidate, judged[candidate.pk])
    candidate.refresh_from_db()
    return candidate


def manual_merge(source, target):
    """Merge by hand, as the admin does. Returns the undo entry and the pair's applied candidate."""
    pks = [source.pk, target.pk]  # read before the merge: delete() clears the instance pk
    entry = merge_authors(source, target)
    return entry, author_rows().get(signature=sorted_pk_signature(pks))


class AuthorNameTests(SimpleTestCase):
    def test_normalize_folds_case_width_and_spaces(self):
        self.assertEqual(normalize_author("I Eat Tomatoes"), normalize_author("i eat  tomatoes"))
        self.assertEqual(normalize_author("  Ｔｏｍ   Ｂｏｗ! "), "tom bow")

    def test_normalize_keeps_cjk_and_brackets(self):
        self.assertEqual(normalize_author("爱潜水的乌贼"), "爱潜水的乌贼")
        self.assertEqual(normalize_author("Pen (Real)"), "pen (real)")

    def test_bracketed_original(self):
        self.assertTrue(is_bracketed_original("Lucky Old Cat", "Lucky Old Cat（天运老猫）"))
        self.assertTrue(is_bracketed_original("Lucky Old Cat【天运老猫】", "Lucky Old Cat"))
        self.assertFalse(is_bracketed_original("Lucky Old Cat", "Old Cat (天运老猫)"))
        self.assertFalse(is_bracketed_original("・", "(一缕)"))

    def test_romanization_fits(self):
        self.assertTrue(romanization_fits("Lu·Xun", "鲁迅"))
        self.assertFalse(romanization_fits("Li Xian", "李闲鱼"))
        self.assertTrue(romanization_fits("Bi-Rim", "비림"))
        # Latin spelling variants are left to the LLM.
        self.assertTrue(romanization_fits("Yuu Kamiya", "Yu Kamiya"))
        # Kana is not checked: romaji syllables do not map to characters.
        self.assertTrue(romanization_fits("Nanashi", "ななし"))


class AuthorResolveTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Tsukasa Kiryu")
        AuthorAlias.objects.create(name="Kiryu Tsukasa", author=self.author)

    def test_resolve_matches_normalized_name(self):
        self.assertEqual(Author.resolve("tsukasa  kiryu").pk, self.author.pk)
        self.assertEqual(Author.objects.count(), 1)

    def test_resolve_follows_alias(self):
        self.assertEqual(Author.resolve("kiryu tsukasa").pk, self.author.pk)
        self.assertEqual(Author.objects.count(), 1)

    def test_resolve_creates_unknown_and_ignores_empty(self):
        created = Author.resolve("Someone New")
        self.assertEqual(created.name, "Someone New")
        self.assertIsNone(Author.resolve("   "))


class AuthorMergeTests(TestCase):
    def setUp(self):
        self.external = ExternalSource.objects.create(source_name="s")
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.target = Author.objects.create(name="Main Name")
        self.source = Author.objects.create(name="Other Name")
        self.s1 = self._source("http://s/1", self.target)
        self.s2 = self._source("http://s/2", self.target, self.source)
        self.s3 = self._source("http://s/3", self.source)

    def _source(self, url, *authors):
        source = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )
        source.authors.add(*authors)
        return source

    def test_merge_moves_links_and_keeps_an_alias(self):
        entry, _ = manual_merge(self.source, self.target)

        self.assertFalse(Author.objects.filter(pk=self.source.pk).exists())
        self.assertEqual(
            set(self.target.novels.values_list("pk", flat=True)),
            {self.s1.pk, self.s2.pk, self.s3.pk},
        )
        self.assertEqual(entry["added_source_ids"], [self.s3.pk])
        self.assertTrue(AuthorAlias.objects.filter(name="Other Name", author=self.target).exists())

    def test_import_after_merge_reuses_the_target(self):
        merge_authors(self.source, self.target)

        self.assertEqual(Author.resolve("other name").pk, self.target.pk)
        self.assertEqual(Author.objects.filter(name="Other Name").count(), 0)

    def test_undo_restores_the_source_author(self):
        _, candidate = manual_merge(self.source, self.target)

        undo_candidate(candidate)

        restored = Author.objects.get(name="Other Name")
        self.assertEqual(set(restored.novels.values_list("pk", flat=True)), {self.s2.pk, self.s3.pk})
        self.assertEqual(set(self.target.novels.values_list("pk", flat=True)), {self.s1.pk, self.s2.pk})
        self.assertFalse(AuthorAlias.objects.filter(name="Other Name").exists())
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_UNDONE)
        self.assertIsNotNone(candidate.undone_at)

    def test_undo_restores_the_source_under_its_original_pk(self):
        source_pk = self.source.pk  # read before the merge: delete() clears the instance pk
        _, candidate = manual_merge(self.source, self.target)

        undo_candidate(candidate)

        self.assertEqual(Author.objects.get(pk=source_pk).name, "Other Name")

    def test_undo_deletes_the_alias_the_merge_created_even_after_a_rename(self):
        _, candidate = manual_merge(self.source, self.target)
        self.target.name = "other name"  # same key as the old name now
        self.target.save()

        undo_candidate(candidate)

        self.assertFalse(AuthorAlias.objects.filter(name="Other Name").exists())

    def test_undo_keeps_an_alias_the_merge_did_not_create(self):
        # The source's own alias for its name is moved to the target and already covers it,
        # so the merge creates no alias and undo must leave the moved one in place.
        AuthorAlias.objects.create(name="Other Name", author=self.source)
        source_pk = self.source.pk
        _, candidate = manual_merge(self.source, self.target)

        undo_candidate(candidate)

        restored = Author.objects.get(pk=source_pk)
        self.assertTrue(AuthorAlias.objects.filter(name="Other Name", author=restored).exists())

    def test_merge_drops_other_open_candidates_that_name_the_source(self):
        third = Author.objects.create(name="Third Name")
        other = pair_candidate(self.source, third)

        merge_authors(self.source, self.target)

        self.assertFalse(Candidate.objects.filter(pk=other.pk).exists())

    def test_alias_name_in_use_is_refused(self):
        third = Author.objects.create(name="Third Name")
        AuthorAlias.objects.create(name="Other Name", author=third)

        with self.assertRaisesMessage(MergeError, "alias name already in use"):
            merge_authors(self.source, self.target)
        self.assertTrue(Author.objects.filter(pk=self.source.pk).exists())


class AuthorMergeChainTests(TestCase):
    def setUp(self):
        self.external = ExternalSource.objects.create(source_name="s")
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.a = Author.objects.create(name="Author A")
        self.b = Author.objects.create(name="Author B")
        self.c = Author.objects.create(name="Author C")
        self.sa = self._source("http://s/a", self.a)
        self.sb = self._source("http://s/b", self.b)
        self.sc = self._source("http://s/c", self.c)

    def _source(self, url, author):
        source = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )
        source.authors.add(author)
        return source

    def test_chained_merges_undone_in_reverse_restore_every_author(self):
        _, first = manual_merge(self.a, self.b)
        _, second = manual_merge(self.b, self.c)

        undo_candidate(second)
        undo_candidate(first)

        self.assertEqual(set(Author.objects.get(name="Author A").novels.values_list("pk", flat=True)), {self.sa.pk})
        self.assertEqual(set(Author.objects.get(name="Author B").novels.values_list("pk", flat=True)), {self.sb.pk})
        self.assertEqual(set(Author.objects.get(name="Author C").novels.values_list("pk", flat=True)), {self.sc.pk})
        self.assertFalse(AuthorAlias.objects.exists())


class AuthorFinderTests(TestCase):
    def setUp(self):
        self.external = ExternalSource.objects.create(source_name="s")
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")

    def _source(self, url, names):
        source = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )
        source.authors.add(*[Author.objects.get_or_create(name=name)[0] for name in names])
        return source

    def test_combined_name_pair_is_queued_once_for_the_llm(self):
        self._source("http://s/1", ["Okina Baba and Tsukasa Kiryu", "Tsukasa Kiryu"])
        self._source("http://s/2", ["Okina Baba", "Tsukasa Kiryu"])

        call_command("find_author_candidates")
        call_command("find_author_candidates")  # a re-run must not queue it twice

        candidate = author_rows().get()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.signals["rule"], "cross_source")
        self.assertEqual(
            sorted(candidate.target_names), ["Okina Baba", "Okina Baba and Tsukasa Kiryu"]
        )
        self.assertEqual(Author.objects.count(), 3)

    def test_normalized_duplicates_are_queued_and_merged_on_a_yes(self):
        Author.objects.create(name="I Eat Tomatoes")
        Author.objects.create(name="i eat  tomatoes")

        call_command("find_author_candidates")

        # The finder only proposes: the pair waits for the judge.
        self.assertEqual(Author.objects.count(), 2)
        candidate = author_rows().get()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.signals["rule"], "normalized")

        judge_author(candidate, "same_name")

        self.assertEqual(Author.objects.count(), 1)
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(candidate.decided_by, Candidate.DECIDED_LLM)

    def test_mixed_script_name_is_queued_with_the_author_both_runs_resolve_to(self):
        cjk = Author.objects.create(name="爱潜水的乌贼")
        AuthorAlias.objects.create(name="Cuttlefish That Loves Diving", author=cjk)
        combined = Author.objects.create(name="Cuttlefish That Loves Diving 爱潜水的乌贼")

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 2)
        candidate = author_rows().get()
        self.assertEqual(candidate.signals["rule"], "mixed_script")
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(sorted(candidate.target_ids), sorted([cjk.pk, combined.pk]))

    def test_mixed_script_name_is_queued_with_its_latin_author_when_the_cjk_part_is_unknown(self):
        latin = Author.objects.create(name="A Wisp Of Netherworld Inferno")
        combined = Author.objects.create(name="A Wisp Of Netherworld Inferno (一缕冥火)")

        call_command("find_author_candidates")

        candidate = author_rows().get()
        self.assertEqual(candidate.signals["rule"], "mixed_script")
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(sorted(candidate.target_ids), sorted([latin.pk, combined.pk]))

    def test_mixed_script_name_is_skipped_when_only_its_cjk_part_resolves(self):
        Author.objects.create(name="一缕冥火")
        combined = Author.objects.create(name="A Wisp Of Netherworld Inferno (一缕冥火)")

        call_command("find_author_candidates")

        self.assertTrue(Author.objects.filter(pk=combined.pk).exists())
        self.assertFalse(author_rows().exists())

    def test_cross_source_pair_is_queued(self):
        cjk = Author.objects.create(name="爱潜水的乌贼")
        latin = Author.objects.create(name="Cuttlefish That Loves Diving")
        shared = Author.objects.create(name="Shared Staff")
        self._source("http://s/1", []).authors.add(cjk, shared)
        self._source("http://s/2", []).authors.add(latin, shared)

        call_command("find_author_candidates")

        candidate = author_rows().get()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.signals["rule"], "cross_source")
        self.assertEqual(candidate.signature, sorted_pk_signature([cjk.pk, latin.pk]))
        self.assertEqual(Author.objects.count(), 3)

    def test_pending_pair_gets_the_normalized_rule_on_a_rerun(self):
        first = Author.objects.create(name="I Eat Tomatoes")
        second = Author.objects.create(name="i eat  tomatoes")
        pair_candidate(first, second)

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 2)
        candidate = author_rows().get()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.signals["rule"], "normalized")

    def test_refused_merge_goes_back_to_review_with_the_alias_reason(self):
        first = Author.objects.create(name="I Eat Tomatoes")
        second = Author.objects.create(name="i eat  tomatoes")
        third = Author.objects.create(name="Third Name")
        AuthorAlias.objects.create(name="i eat  tomatoes", author=third)

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 3)
        candidate = author_rows().get(signature=sorted_pk_signature([first.pk, second.pk]))
        judge_author(candidate, "same_name")
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(candidate.reason, "alias name already in use")
        self.assertEqual(Author.objects.count(), 3)


class AuthorUndoFinderTests(TestCase):
    def setUp(self):
        # Same key, so a rule A pair. With no novels the tie keeps the lower pk: second is merged away.
        self.first = Author.objects.create(name="I Eat Tomatoes")
        self.second = Author.objects.create(name="i eat  tomatoes")

    def test_undone_normalized_merge_keeps_its_pk_and_is_not_merged_again(self):
        call_command("find_author_candidates")
        candidate = author_rows().get()
        judge_author(candidate, "same_name")

        undo_candidate(candidate)
        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 2)
        self.assertTrue(Author.objects.filter(pk=self.second.pk, name="i eat  tomatoes").exists())
        self.assertEqual(author_rows().count(), 1)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_UNDONE)

    def test_undone_admin_merge_keeps_its_pk_and_is_not_merged_again(self):
        second_pk = self.second.pk  # read before the merge: delete() clears the instance pk
        _, candidate = manual_merge(self.second, self.first)
        undo_candidate(candidate)

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 2)
        self.assertTrue(Author.objects.filter(pk=second_pk).exists())
        self.assertEqual(author_rows().count(), 1)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_UNDONE)


class AuthorMergeTaskTests(TestCase):
    def setUp(self):
        self.task = REGISTRY["author_merge"]
        self.pen = Author.objects.create(name="Pen Name")
        self.real = Author.objects.create(name="Real Name")
        self.candidate = pair_candidate(self.pen, self.real)

    def _pair(self, first, second):
        """A pending candidate for two new authors."""
        authors = [Author.objects.create(name=name) for name in (first, second)]
        return pair_candidate(*authors)

    def test_translation_with_matching_names_merges(self):
        judge_author(self.candidate, "translation")

        self.assertEqual(self.candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 1)

    def test_different_and_other_party_are_rejected(self):
        for relation in ("different", "other_party"):
            with self.subTest(relation=relation):
                Candidate.objects.filter(pk=self.candidate.pk).update(
                    status=Candidate.STATUS_PENDING, verdict=None, decided_by="", decided_at=None,
                )
                judge_author(self.candidate, relation)

                self.assertEqual(self.candidate.status, Candidate.STATUS_REJECTED)
                self.assertEqual(Author.objects.count(), 2)

    def test_unsure_is_sent_to_review(self):
        judge_author(self.candidate, "unsure")

        self.assertEqual(self.candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(self.candidate.reason, "unsure")
        self.assertEqual(Author.objects.count(), 2)

    def test_names_of_another_pair_are_not_judged(self):
        content = json.dumps({"results": [{
            "id": self.candidate.pk, "names": "Okina Baba / Tsukasa Kiryu",
            "evidence": "", "relation": "translation", "confidence": 0.99,
        }]})

        self.assertEqual(self.task.parse([self.candidate], None, content), {})
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(Author.objects.count(), 2)

    def test_romanization_with_a_wrong_character_count_goes_to_review(self):
        candidate = self._pair("Li Xian", "李闲鱼")

        judge_author(candidate, "romanization")

        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(candidate.reason, "romanization does not match the character count")
        self.assertEqual(Author.objects.count(), 4)

    def test_same_name_merges(self):
        candidate = self._pair("Cuttlefish", "Author : Cuttlefish")

        judge_author(candidate, "same_name")

        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 3)

    def test_same_name_with_a_wrong_character_count_goes_to_review(self):
        candidate = self._pair("Li Xian", "李闲鱼")

        judge_author(candidate, "same_name")

        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(Author.objects.count(), 4)

    def test_romanization_with_matching_character_count_merges(self):
        candidate = self._pair("Er Gen", "耳根")

        judge_author(candidate, "romanization")

        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 3)

    def test_bracketed_original_merges(self):
        candidate = self._pair("A Wisp Of Netherworld Inferno", "A Wisp Of Netherworld Inferno (一缕冥火)")

        judge_author(candidate, "bracketed_original")

        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 3)

    def test_bracketed_original_on_unrelated_names_goes_to_review(self):
        candidate = self._pair("Okina Baba", "Tsukasa Kiryu")

        judge_author(candidate, "bracketed_original")

        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(candidate.reason, "not a bracketed original")
        self.assertEqual(Author.objects.count(), 4)

    def test_different_rejects_a_combined_name_pair_and_keeps_both_authors(self):
        combined = Author.objects.create(name="Okina Baba and Tsukasa Kiryu")
        okina = Author.objects.create(name="Okina Baba")
        candidate = pair_candidate(combined, okina)

        judge_author(candidate, "different")

        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertTrue(Author.objects.filter(pk=combined.pk).exists())
        self.assertTrue(Author.objects.filter(pk=okina.pk).exists())

    def test_prepare_drops_a_candidate_whose_author_is_gone(self):
        self.pen.delete()

        kept, _ = self.task.prepare([self.candidate])

        self.assertEqual(kept, [])
        self.assertFalse(author_rows().filter(pk=self.candidate.pk).exists())

    def test_candidate_left_out_of_the_reply_is_not_judged(self):
        third = Author.objects.create(name="Third Name")
        left_out = pair_candidate(self.pen, third)
        content = json.dumps({"results": [{
            "id": self.candidate.pk, "names": "Pen Name / Real Name",
            "evidence": "", "relation": "different", "confidence": 0.99,
        }]})

        judged = self.task.parse([self.candidate, left_out], None, content)

        self.assertEqual(set(judged), {self.candidate.pk})
        left_out.refresh_from_db()
        self.assertEqual(left_out.status, Candidate.STATUS_PENDING)

    def test_parse_drops_invalid_entries_and_rejects_empty_replies(self):
        content = (
            '{"results": [{"id": %d, "names": "Pen Name / Real Name", "relation": "translation"},'
            ' {"id": %d, "names": "Pen Name / Real Name", "relation": "same"},'
            ' {"id": 999, "names": "Pen Name / Real Name", "relation": "translation"}]}'
            % (self.candidate.pk, self.candidate.pk)
        )
        judged = self.task.parse([self.candidate], None, content)
        self.assertEqual(list(judged), [self.candidate.pk])
        self.assertEqual(judged[self.candidate.pk]["answer"], "yes")
        self.assertEqual(judged[self.candidate.pk]["relation"], "translation")
        with self.assertRaises(LLMParseError):
            self.task.parse([self.candidate], None, '{"results": [{"id": 999, "relation": "translation"}]}')


class ImportAuthorLockingTests(TestCase):
    def setUp(self):
        novel = Novel.objects.create(title="N", slug="imp-a", novel_path="imp-a")
        external = ExternalSource.objects.create(source_name="imp-a")
        self.source = NovelFromSource.objects.create(
            novel=novel, external_source=external, title="N", source_url="http://imp-a/1"
        )
        self.cuttlefish = Author.objects.create(name="Cuttlefish That Loves Diving")
        self.okina = Author.objects.create(name="Okina Baba")
        AuthorAlias.objects.create(name="爱潜水的乌贼", author=self.cuttlefish)

    def test_names_resolve_to_distinct_authors(self):
        _set_source_authors(
            self.source, ["Cuttlefish That Loves Diving", "爱潜水的乌贼", "okina baba", ""]
        )
        self.assertEqual(set(self.source.authors.all()), {self.cuttlefish, self.okina})

    def test_merged_away_author_is_retried_with_one_lock_per_attempt(self):
        # The first lock reports Okina as gone (merged away between resolve and lock).
        real_lock = source_links.lock_pks
        seen = []

        def racing_lock(model, pks):
            seen.append(sorted(pks))
            result = real_lock(model, pks)
            if len(seen) == 1:
                result = result - {self.okina.pk}
            return result

        with mock.patch.object(source_links, "lock_pks", side_effect=racing_lock):
            _set_source_authors(self.source, ["Cuttlefish That Loves Diving", "Okina Baba"])

        self.assertEqual(len(seen), 2)
        self.assertEqual(set(self.source.authors.all()), {self.cuttlefish, self.okina})

    def test_gives_up_after_the_attempt_limit_and_keeps_old_links(self):
        self.source.authors.add(self.okina)
        with mock.patch.object(source_links, "lock_pks", return_value=set()) as lock:
            with self.assertRaises(AuthorImportError):
                _set_source_authors(self.source, ["Cuttlefish That Loves Diving"])
        self.assertEqual(lock.call_count, AUTHOR_IMPORT_ATTEMPTS)
        self.assertEqual(list(self.source.authors.all()), [self.okina])


class BlockedAuthorTests(TestCase):
    def setUp(self):
        self.external = ExternalSource.objects.create(source_name="s")
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.blocked = Author.objects.create(name="Blocked Name")
        self.other = Author.objects.create(name="Other")
        self.s1 = self._source("http://s/1", self.blocked, self.other)
        self.s2 = self._source("http://s/2", self.blocked)

    def _source(self, url, *authors):
        source = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )
        source.authors.add(*authors)
        return source

    def _block(self):
        block_authors([self.blocked.pk])
        self.blocked.refresh_from_db()  # merge_authors reads the flag from the instance

    def test_block_unlinks_the_author_and_keeps_the_sources(self):
        self.assertEqual(block_authors([self.blocked.pk]), 1)

        self.assertEqual(list(self.s1.authors.all()), [self.other])
        self.assertEqual(list(self.s2.authors.all()), [])
        self.assertTrue(NovelFromSource.objects.filter(pk=self.s2.pk).exists())
        self.assertFalse(Author.objects.filter(pk=self.blocked.pk).exists())
        self.assertTrue(Author.all_objects.filter(pk=self.blocked.pk, is_blocked=True).exists())

    def test_import_skips_a_blocked_name_and_creates_no_author(self):
        self._block()
        source = self._source("http://s/3")
        count = Author.all_objects.count()

        _set_source_authors(source, ["Blocked Name", "Other"])

        self.assertEqual(list(source.authors.all()), [self.other])
        self.assertEqual(Author.all_objects.count(), count)

    def test_import_skips_a_normalized_variant_of_a_blocked_name(self):
        self._block()
        source = self._source("http://s/3")
        count = Author.all_objects.count()

        _set_source_authors(source, ["  blocked  NAME ", "Other"])

        self.assertEqual(list(source.authors.all()), [self.other])
        self.assertEqual(Author.all_objects.count(), count)

    def test_import_skips_an_alias_of_a_blocked_author(self):
        AuthorAlias.objects.create(name="Old Blocked Alias", author=self.blocked)
        self._block()
        source = self._source("http://s/3")
        count = Author.all_objects.count()

        _set_source_authors(source, ["Old Blocked Alias", "Other"])

        self.assertEqual(list(source.authors.all()), [self.other])
        self.assertEqual(Author.all_objects.count(), count)

    def test_find_returns_none_for_a_blocked_name(self):
        self._block()

        self.assertIsNone(Author.find("Blocked Name"))
        self.assertIsNone(Author.resolve("blocked name"))

    def test_merge_is_refused_when_either_side_is_blocked(self):
        self._block()

        with self.assertRaisesMessage(AuthorMergeRefused, "blocked author"):
            merge_authors(self.other, self.blocked)
        with self.assertRaisesMessage(AuthorMergeRefused, "blocked author"):
            merge_authors(self.blocked, self.other)
        self.assertTrue(Author.all_objects.filter(pk=self.blocked.pk).exists())

    def test_block_rejects_open_candidates_that_contain_the_author(self):
        third = Author.objects.create(name="Third Name")
        candidate = pair_candidate(self.blocked, third)

        block_authors([self.blocked.pk])

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(candidate.reason, "author blocked")

    def test_filter_and_autocomplete_hide_the_blocked_author_and_its_aliases(self):
        AuthorAlias.objects.create(name="Old Blocked Alias", author=self.blocked)
        self._block()

        self.assertEqual(_author_ids(["Blocked Name", "Old Blocked Alias"]), set())
        self.assertEqual(_author_ids(["Other"]), {self.other.pk})
        for query in ["blocked", "old blocked"]:
            response = self.client.get(
                reverse("autocomplete_suggestion"), {"type": "author", "query": query}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, [])
        response = self.client.get(
            reverse("autocomplete_suggestion"), {"type": "author", "query": "other"}
        )
        self.assertEqual([entry["name"] for entry in response.data], ["Other"])

    def test_unblock_restores_visibility_and_a_reimport_links_it_again(self):
        self._block()

        self.assertEqual(unblock_authors([self.blocked.pk]), 1)

        self.assertTrue(Author.objects.filter(pk=self.blocked.pk).exists())
        source = self._source("http://s/3")
        _set_source_authors(source, ["Blocked Name"])
        self.assertEqual(list(source.authors.all()), [self.blocked])
        self.assertEqual(list(self.s2.authors.all()), [])  # old links are not restored
        self.assertEqual(Author.all_objects.count(), 2)

    def test_a_blocked_duplicate_does_not_shadow_a_visible_one(self):
        self._block()
        visible = Author.objects.create(name="blocked name")  # same key, higher pk
        source = self._source("http://s/3")

        _set_source_authors(source, ["Blocked Name"])

        self.assertEqual(list(source.authors.all()), [visible])
        self.assertEqual(Author.find("BLOCKED NAME"), visible)

    def test_undo_is_refused_when_the_target_is_blocked(self):
        third = Author.objects.create(name="Third Name")
        _, candidate = manual_merge(third, self.blocked)
        self._block()

        with self.assertRaisesMessage(MergeError, "The target author no longer exists."):
            undo_candidate(candidate)
        self.assertFalse(Author.all_objects.filter(name="Third Name").exists())
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)

    def test_admin_lists_blocked_authors_and_cannot_delete(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        self._block()
        model_admin = site._registry[Author]
        request = RequestFactory().get("/")

        self.assertIn(self.blocked, model_admin.get_queryset(request))
        self.assertFalse(model_admin.has_delete_permission(request))
