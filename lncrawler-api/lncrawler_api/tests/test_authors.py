"""Tests for author normalization, script runs, merging and the author finder."""

from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ..models import source_links
from ..models.source_links import AUTHOR_IMPORT_ATTEMPTS, AuthorImportError, _set_source_authors
from ..models import (
    Author,
    AuthorAlias,
    AuthorMerge,
    AuthorMergeCandidate,
    ExternalSource,
    LLMRequest,
    Novel,
    NovelFromSource,
)
from ..services.author_block_service import block_authors, unblock_authors
from ..services.author_merge_service import AuthorMergeRefused, merge_authors, undo_author_merge
from ..services.llm_service import LLMParseError
from ..services.llm_tasks import REGISTRY
from ..services.merge_common import sorted_pk_signature
from ..services.merge_service import MergeError
from ..utils.author_names import is_bracketed_original, normalize_author, romanization_fits, script_runs
from ..views.novels_views import _author_ids


class AuthorNameTests(SimpleTestCase):
    def test_normalize_folds_case_width_and_spaces(self):
        self.assertEqual(normalize_author("I Eat Tomatoes"), normalize_author("i eat  tomatoes"))
        self.assertEqual(normalize_author("  Ｔｏｍ   Ｂｏｗ! "), "tom bow")

    def test_normalize_keeps_cjk_and_brackets(self):
        self.assertEqual(normalize_author("爱潜水的乌贼"), "爱潜水的乌贼")
        self.assertEqual(normalize_author("Pen (Real)"), "pen (real)")

    def test_script_runs_only_for_mixed_names_without_separator(self):
        runs = script_runs("Cuttlefish That Loves Diving 爱潜水的乌贼")
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0], "cuttlefish that loves diving")
        self.assertEqual(script_runs("Okina Baba and Tsukasa Kiryu"), [])
        self.assertEqual(script_runs("Okina Baba"), [])

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
        merge = merge_authors(self.source, self.target)

        self.assertFalse(Author.objects.filter(pk=self.source.pk).exists())
        self.assertEqual(
            set(self.target.novels.values_list("pk", flat=True)),
            {self.s1.pk, self.s2.pk, self.s3.pk},
        )
        self.assertEqual(merge.added_source_ids, [self.s3.pk])
        self.assertTrue(AuthorAlias.objects.filter(name="Other Name", author=self.target).exists())

    def test_import_after_merge_reuses_the_target(self):
        merge_authors(self.source, self.target)

        self.assertEqual(Author.resolve("other name").pk, self.target.pk)
        self.assertEqual(Author.objects.filter(name="Other Name").count(), 0)

    def test_undo_restores_the_source_author(self):
        merge = merge_authors(self.source, self.target)

        undo_author_merge(merge)

        restored = Author.objects.get(name="Other Name")
        self.assertEqual(set(restored.novels.values_list("pk", flat=True)), {self.s2.pk, self.s3.pk})
        self.assertEqual(set(self.target.novels.values_list("pk", flat=True)), {self.s1.pk, self.s2.pk})
        self.assertFalse(AuthorAlias.objects.filter(name="Other Name").exists())
        merge.refresh_from_db()
        self.assertIsNotNone(merge.undone_at)

    def test_undo_restores_the_source_under_its_original_pk(self):
        source_pk = self.source.pk  # read before the merge: delete() clears the instance pk
        merge = merge_authors(self.source, self.target)

        undo_author_merge(merge)

        self.assertEqual(Author.objects.get(pk=source_pk).name, "Other Name")

    def test_undo_deletes_the_alias_the_merge_created_even_after_a_rename(self):
        merge = merge_authors(self.source, self.target)
        self.target.name = "other name"  # same key as the old name now
        self.target.save()

        undo_author_merge(merge)

        self.assertFalse(AuthorAlias.objects.filter(name="Other Name").exists())

    def test_undo_keeps_an_alias_the_merge_did_not_create(self):
        # The source's own alias for its name is moved to the target and already covers it,
        # so the merge creates no alias and undo must leave the moved one in place.
        AuthorAlias.objects.create(name="Other Name", author=self.source)
        source_pk = self.source.pk
        merge = merge_authors(self.source, self.target)

        undo_author_merge(merge)

        restored = Author.objects.get(pk=source_pk)
        self.assertTrue(AuthorAlias.objects.filter(name="Other Name", author=restored).exists())

    def test_merge_marks_other_pending_candidates_as_error(self):
        third = Author.objects.create(name="Third Name")
        other = AuthorMergeCandidate.objects.create(
            signature=sorted_pk_signature([self.source.pk, third.pk]),
            author_ids=sorted([self.source.pk, third.pk]),
            author_names=["Other Name", "Third Name"],
            reason=AuthorMergeCandidate.REASON_CROSS_SOURCE,
        )

        merge_authors(self.source, self.target)

        other.refresh_from_db()
        self.assertEqual(other.status, AuthorMergeCandidate.STATUS_ERROR)
        self.assertEqual(other.reason, "author merged away")

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
        first = merge_authors(self.a, self.b)
        second = merge_authors(self.b, self.c)

        undo_author_merge(second)
        first.refresh_from_db()  # undo of the later merge repointed this one at the restored B
        undo_author_merge(first)

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

    def test_combined_name_pair_goes_to_the_llm(self):
        self._source("http://s/1", ["Okina Baba and Tsukasa Kiryu", "Tsukasa Kiryu"])
        self._source("http://s/2", ["Okina Baba", "Tsukasa Kiryu"])

        call_command("find_author_candidates")
        call_command("find_author_candidates")  # a re-run must not queue it twice

        candidate = AuthorMergeCandidate.objects.get()
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_PENDING)
        self.assertEqual(
            sorted(candidate.author_names), ["Okina Baba", "Okina Baba and Tsukasa Kiryu"]
        )
        self.assertEqual(Author.objects.count(), 3)

    def test_normalized_duplicates_are_merged(self):
        Author.objects.create(name="I Eat Tomatoes")
        Author.objects.create(name="i eat  tomatoes")

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 1)
        candidate = AuthorMergeCandidate.objects.get()
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_APPLIED)
        self.assertEqual(candidate.reason, AuthorMergeCandidate.REASON_NORMALIZED)
        self.assertEqual(AuthorMerge.objects.count(), 1)

    def test_mixed_script_name_merges_into_the_author_both_runs_resolve_to(self):
        cjk = Author.objects.create(name="爱潜水的乌贼")
        AuthorAlias.objects.create(name="Cuttlefish That Loves Diving", author=cjk)
        combined = Author.objects.create(name="Cuttlefish That Loves Diving 爱潜水的乌贼")

        call_command("find_author_candidates")

        self.assertFalse(Author.objects.filter(pk=combined.pk).exists())
        self.assertTrue(Author.objects.filter(pk=cjk.pk).exists())
        candidate = AuthorMergeCandidate.objects.get()
        self.assertEqual(candidate.reason, AuthorMergeCandidate.REASON_MIXED_SCRIPT)
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_APPLIED)

    def test_mixed_script_name_merges_into_its_latin_author_when_the_cjk_part_is_unknown(self):
        latin = Author.objects.create(name="A Wisp Of Netherworld Inferno")
        combined = Author.objects.create(name="A Wisp Of Netherworld Inferno (一缕冥火)")

        call_command("find_author_candidates")

        self.assertFalse(Author.objects.filter(pk=combined.pk).exists())
        self.assertTrue(Author.objects.filter(pk=latin.pk).exists())
        candidate = AuthorMergeCandidate.objects.get()
        self.assertEqual(candidate.reason, AuthorMergeCandidate.REASON_MIXED_SCRIPT)
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_APPLIED)

    def test_mixed_script_name_is_skipped_when_only_its_cjk_part_resolves(self):
        Author.objects.create(name="一缕冥火")
        combined = Author.objects.create(name="A Wisp Of Netherworld Inferno (一缕冥火)")

        call_command("find_author_candidates")

        self.assertTrue(Author.objects.filter(pk=combined.pk).exists())
        self.assertFalse(AuthorMergeCandidate.objects.exists())

    def test_cross_source_pair_is_queued_for_review(self):
        cjk = Author.objects.create(name="爱潜水的乌贼")
        latin = Author.objects.create(name="Cuttlefish That Loves Diving")
        shared = Author.objects.create(name="Shared Staff")
        self._source("http://s/1", []).authors.add(cjk, shared)
        self._source("http://s/2", []).authors.add(latin, shared)

        call_command("find_author_candidates")

        candidate = AuthorMergeCandidate.objects.get()
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_PENDING)
        self.assertEqual(candidate.reason, AuthorMergeCandidate.REASON_CROSS_SOURCE)
        self.assertEqual(candidate.signature, sorted_pk_signature([cjk.pk, latin.pk]))
        self.assertEqual(Author.objects.count(), 3)

    def test_normalized_pair_merges_despite_a_pending_candidate(self):
        first = Author.objects.create(name="I Eat Tomatoes")
        second = Author.objects.create(name="i eat  tomatoes")
        AuthorMergeCandidate.objects.create(
            signature=sorted_pk_signature([first.pk, second.pk]),
            author_ids=sorted([first.pk, second.pk]),
            author_names=[first.name, second.name],
            reason=AuthorMergeCandidate.REASON_CROSS_SOURCE,
        )

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 1)
        candidate = AuthorMergeCandidate.objects.get()
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_APPLIED)
        self.assertEqual(candidate.reason, AuthorMergeCandidate.REASON_NORMALIZED)

    def test_dry_run_writes_nothing(self):
        Author.objects.create(name="I Eat Tomatoes")
        Author.objects.create(name="i eat  tomatoes")

        call_command("find_author_candidates", "--dry-run")

        self.assertEqual(Author.objects.count(), 2)
        self.assertEqual(AuthorMergeCandidate.objects.count(), 0)

    def test_finder_rejects_a_pair_whose_alias_name_is_in_use(self):
        first = Author.objects.create(name="I Eat Tomatoes")
        second = Author.objects.create(name="i eat  tomatoes")
        third = Author.objects.create(name="Third Name")
        AuthorAlias.objects.create(name="i eat  tomatoes", author=third)

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 3)
        candidate = AuthorMergeCandidate.objects.get(
            signature=sorted_pk_signature([first.pk, second.pk])
        )
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
        self.assertEqual(candidate.signals["merge_error"], "alias name already in use")


class AuthorUndoFinderTests(TestCase):
    def setUp(self):
        # Same key, so a rule A pair. With no novels the tie keeps the lower pk: second is merged away.
        self.first = Author.objects.create(name="I Eat Tomatoes")
        self.second = Author.objects.create(name="i eat  tomatoes")

    def test_undone_normalized_merge_keeps_its_pk_and_is_not_merged_again(self):
        call_command("find_author_candidates")
        merge = AuthorMerge.objects.get()

        undo_author_merge(merge)
        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 2)
        self.assertTrue(Author.objects.filter(pk=self.second.pk, name="i eat  tomatoes").exists())
        self.assertEqual(AuthorMerge.objects.count(), 1)
        self.assertEqual(AuthorMergeCandidate.objects.get().status, AuthorMergeCandidate.STATUS_UNDONE)

    def test_undone_admin_merge_keeps_its_pk_and_is_not_merged_again(self):
        second_pk = self.second.pk  # read before the merge: delete() clears the instance pk
        merge = merge_authors(self.second, self.first)  # no candidate row
        undo_author_merge(merge)

        call_command("find_author_candidates")

        self.assertEqual(Author.objects.count(), 2)
        self.assertTrue(Author.objects.filter(pk=second_pk).exists())
        candidate = AuthorMergeCandidate.objects.get()
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_UNDONE)
        self.assertEqual(candidate.reason, "manual")


class AuthorMergeTaskTests(TestCase):
    def setUp(self):
        self.task = REGISTRY["author_merge"]
        self.pen = Author.objects.create(name="Pen Name")
        self.real = Author.objects.create(name="Real Name")
        self.candidate = AuthorMergeCandidate.objects.create(
            signature=sorted_pk_signature([self.pen.pk, self.real.pk]),
            author_ids=sorted([self.pen.pk, self.real.pk]),
            author_names=["Pen Name", "Real Name"],
            reason=AuthorMergeCandidate.REASON_CROSS_SOURCE,
        )
        self.request = LLMRequest.objects.create(
            task="author_merge",
            target_type="author_merge_candidate",
            target_ids=[self.candidate.pk],
            prompt_version=self.task.prompt_version,
        )

    def _apply(self, relation, candidate=None, names=None):
        candidate = candidate or self.candidate
        names = names or " / ".join(candidate.author_names)
        result = {"results": [{"id": candidate.pk, "names": names, "relation": relation}]}
        self.task.apply(self.request, result)
        candidate.refresh_from_db()
        return candidate

    def _pair(self, first, second):
        """A pending candidate for two new authors, with a request that covers only it."""
        authors = [Author.objects.create(name=name) for name in (first, second)]
        candidate = AuthorMergeCandidate.objects.create(
            signature=sorted_pk_signature([author.pk for author in authors]),
            author_ids=sorted(author.pk for author in authors),
            author_names=[first, second],
            reason=AuthorMergeCandidate.REASON_CROSS_SOURCE,
        )
        self.request.target_ids = [candidate.pk]
        self.request.save(update_fields=["target_ids"])
        return candidate

    def test_translation_with_matching_names_merges(self):
        self._apply("translation")

        self.assertEqual(self.candidate.status, AuthorMergeCandidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 1)

    def test_unsure_different_and_other_party_are_rejected(self):
        for relation in ("unsure", "different", "other_party"):
            with self.subTest(relation=relation):
                AuthorMergeCandidate.objects.filter(pk=self.candidate.pk).update(
                    status=AuthorMergeCandidate.STATUS_PENDING, llm_response=None,
                )
                self._apply(relation)

                self.assertEqual(self.candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
                self.assertEqual(Author.objects.count(), 2)

    def test_names_of_another_candidate_are_rejected(self):
        self._apply("translation", names="Okina Baba / Tsukasa Kiryu")

        self.assertEqual(self.candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
        self.assertEqual(self.candidate.llm_response["refused"], "names do not match the candidate")
        self.assertEqual(Author.objects.count(), 2)

    def test_romanization_with_a_wrong_character_count_is_rejected(self):
        candidate = self._pair("Li Xian", "李闲鱼")

        self._apply("romanization", candidate=candidate)

        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
        self.assertEqual(candidate.llm_response["refused"], "romanization does not match the character count")
        self.assertEqual(Author.objects.count(), 4)

    def test_same_name_merges(self):
        candidate = self._pair("Cuttlefish", "Author : Cuttlefish")

        self._apply("same_name", candidate=candidate)

        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 3)

    def test_same_name_with_a_wrong_character_count_is_rejected(self):
        candidate = self._pair("Li Xian", "李闲鱼")

        self._apply("same_name", candidate=candidate)

        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
        self.assertEqual(Author.objects.count(), 4)

    def test_romanization_with_matching_character_count_merges(self):
        candidate = self._pair("Er Gen", "耳根")

        self._apply("romanization", candidate=candidate)

        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 3)

    def test_bracketed_original_merges(self):
        candidate = self._pair("A Wisp Of Netherworld Inferno", "A Wisp Of Netherworld Inferno (一缕冥火)")

        self._apply("bracketed_original", candidate=candidate)

        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_APPLIED)
        self.assertEqual(Author.objects.count(), 3)

    def test_bracketed_original_on_unrelated_names_is_rejected(self):
        candidate = self._pair("Okina Baba", "Tsukasa Kiryu")

        self._apply("bracketed_original", candidate=candidate)

        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
        self.assertEqual(candidate.llm_response["refused"], "not a bracketed original")
        self.assertEqual(Author.objects.count(), 4)

    def test_different_rejects_a_combined_name_pair_and_keeps_both_authors(self):
        combined = Author.objects.create(name="Okina Baba and Tsukasa Kiryu")
        okina = Author.objects.create(name="Okina Baba")
        candidate = AuthorMergeCandidate.objects.create(
            signature=sorted_pk_signature([combined.pk, okina.pk]),
            author_ids=sorted([combined.pk, okina.pk]),
            author_names=["Okina Baba and Tsukasa Kiryu", "Okina Baba"],
            reason=AuthorMergeCandidate.REASON_CROSS_SOURCE,
        )
        self.request.target_ids = [candidate.pk]
        self.request.save(update_fields=["target_ids"])

        self._apply("different", candidate=candidate)

        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
        self.assertTrue(Author.objects.filter(pk=combined.pk).exists())
        self.assertTrue(Author.objects.filter(pk=okina.pk).exists())

    def test_failed_request_is_not_reenqueued(self):
        LLMRequest.objects.filter(pk=self.request.pk).update(status=LLMRequest.STATUS_FAILED)

        self.assertEqual(self.task.enqueue(10), 0)

    def test_build_messages_marks_stale_candidate_as_error(self):
        self.pen.delete()

        self.assertIsNone(self.task.build_messages(self.request))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, AuthorMergeCandidate.STATUS_ERROR)
        self.assertEqual(self.candidate.reason, "author merged away")

    def test_candidate_left_out_of_the_reply_is_flagged(self):
        third = Author.objects.create(name="Third Name")
        left_out = AuthorMergeCandidate.objects.create(
            signature=sorted_pk_signature([self.pen.pk, third.pk]),
            author_ids=sorted([self.pen.pk, third.pk]),
            author_names=["Pen Name", "Third Name"],
            reason=AuthorMergeCandidate.REASON_CROSS_SOURCE,
        )
        self.request.target_ids = [self.candidate.pk, left_out.pk]
        self.request.save(update_fields=["target_ids"])

        self._apply("different")  # the reply covers only self.candidate

        left_out.refresh_from_db()
        self.assertEqual(left_out.status, AuthorMergeCandidate.STATUS_ERROR)
        self.assertEqual(left_out.reason, "no llm answer")

    def test_parse_drops_invalid_entries_and_rejects_empty_replies(self):
        content = (
            '{"results": [{"id": %d, "names": "Pen Name / Real Name", "relation": "translation"},'
            ' {"id": %d, "names": "Pen Name / Real Name", "relation": "same"},'
            ' {"id": 999, "names": "Pen Name / Real Name", "relation": "translation"}]}'
            % (self.candidate.pk, self.candidate.pk)
        )
        result = self.task.parse(self.request, content)
        self.assertEqual(result["results"], [
            {"id": self.candidate.pk, "names": "Pen Name / Real Name", "evidence": "", "relation": "translation"},
        ])
        with self.assertRaises(LLMParseError):
            self.task.parse(self.request, '{"results": [{"id": 999, "relation": "translation"}]}')


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
        candidate = AuthorMergeCandidate.objects.create(
            signature=sorted_pk_signature([self.blocked.pk, third.pk]),
            author_ids=sorted([self.blocked.pk, third.pk]),
            author_names=["Blocked Name", "Third Name"],
            reason=AuthorMergeCandidate.REASON_CROSS_SOURCE,
        )

        block_authors([self.blocked.pk])

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, AuthorMergeCandidate.STATUS_REJECTED)
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
        merge = merge_authors(third, self.blocked)
        self._block()

        with self.assertRaisesMessage(MergeError, "blocked"):
            undo_author_merge(merge)
        self.assertFalse(Author.all_objects.filter(name="Third Name").exists())

    def test_admin_lists_blocked_authors_and_cannot_delete(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        self._block()
        model_admin = site._registry[Author]
        request = RequestFactory().get("/")

        self.assertIn(self.blocked, model_admin.get_queryset(request))
        self.assertFalse(model_admin.has_delete_permission(request))
