"""Tests for tag autocomplete, normalization, merging and the tag_merge / tag_r18 candidates."""

import json
import os
import re
import shutil
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Candidate,
    ExternalSource,
    LLMCall,
    Novel,
    NovelFromSource,
    Tag,
    TagAlias,
)
from django.conf import settings
from django.contrib import admin
from django.contrib import messages as django_messages
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
from ..admin.source_admin import TagAdmin, TagAdminForm
from ..models import sources_models
from ..models.source_links import TAG_IMPORT_ATTEMPTS, TagImportError
from ..models.sources_models import (
    _set_source_tags,
    adult_novel_ids,
    is_majority_adult,
    refresh_adult_for_tags,
)
from ..utils.query_helpers import exclude_adult, public_novels, public_sources
from ..services import MergeError, llm_service, merge_tags, rename_tag
from ..services import embedding_service, llm_tasks, merge_service
from ..services import tag_merge_service as tms
from ..services.candidate_blocks import blocked_pairs, pair_key
from ..services.candidate_service import (
    CandidateError,
    apply_candidate,
    reject_candidate,
    undo_candidate,
)
from ..services.merge_common import sorted_pk_signature
from ..utils.tag_utils import normalize_tag

from .llm_helpers import llm_chain


def tag_rows():
    """Every tag_merge candidate row."""
    return Candidate.objects.filter(kind=Candidate.KIND_TAG_MERGE)


def tag_candidate(*tags, **extra):
    """A candidate naming these tags, in the order the finder writes them."""
    ids = [tag.pk for tag in tags]
    return Candidate.objects.create(
        kind=Candidate.KIND_TAG_MERGE,
        signature=sorted_pk_signature(ids),
        target_ids=ids,
        target_names=[tag.name for tag in tags],
        **extra,
    )


def keep_everything(messages):
    """A verification reply that keeps every member of every set it is shown."""
    blocks = re.split(r"(?m)^Set (s\d+):", messages[-1]["content"])[1:]
    return {"sets": [
        {"set": set_id, "keep": re.findall(r"(?m)^(t\d+)\. ", body)}
        for set_id, body in zip(blocks[::2], blocks[1::2])
    ]}


def run_judge(reply, task="tag_merge", limit=None, verify=keep_everything, **caps):
    """Run ``run_llm`` for one task with ``reply`` as the model's answer.

    ``reply`` is an exception to raise, a str sent as-is, a dict sent as JSON, or a
    function of the messages returning one of those. ``verify`` answers the verification
    call the same way, and defaults to keeping every member. ``limit`` caps the batches of
    the run. ``caps`` are fields of the chain's provider (see ``llm_chain``).
    Returns the ``_post_chat`` mock, so a test can count the calls.
    """

    def post(messages, *args, **kwargs):
        handler = verify if messages[0]["content"] == tms.VERIFY_PROMPT else reply
        value = handler(messages) if callable(handler) else handler
        if isinstance(value, Exception):
            raise value
        content = value if isinstance(value, str) else json.dumps(value)
        return content, 10, None

    with override_settings(**llm_chain(**caps)), \
            mock.patch.object(llm_service, "_post_chat", side_effect=post) as mocked:
        call_command("run_llm", task, limit=limit)
    return mocked


def no_sets_for_each_group(messages):
    """A reply that rejects every group the prompt holds: no set proposed."""
    groups = messages[-1]["content"].count("Group ")
    return {"groups": [{"group": number, "sets": []} for number in range(1, groups + 1)]}


def make_tags(*names):
    return [Tag.objects.create(name=name) for name in names]


def answer(*sets):
    """A tag_merge reply with one group holding the given sets."""
    return {"groups": [{"group": 1, "sets": list(sets)}]}


class TagAutocompleteAliasTests(TestCase):
    """A merged-away tag name must still surface its canonical tag."""

    def setUp(self):
        self.novel = Novel.objects.create(title="Isekai Tale", slug="it", novel_path="it")
        self.canonical = Tag.objects.create(name="Isekai")
        source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="tag-site"),
            title="Isekai Tale",
            source_url="http://tag/1",
        )
        source.tags.add(self.canonical)
        TagAlias.objects.create(name="isekai", tag=self.canonical)

    def _suggest(self, query):
        response = self.client.get(
            reverse("autocomplete_suggestion"), {"type": "tag", "query": query}
        )
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_alias_query_returns_canonical_tag(self):
        suggestions = self._suggest("isekai")
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["name"], "Isekai")
        self.assertEqual(suggestions[0]["alias"], "isekai")
        self.assertEqual(suggestions[0]["count"], 1)

    def test_canonical_and_alias_merge_into_one_entry(self):
        # "Isekai" (canonical) and "isekai" (alias) both match case-insensitively.
        self.assertEqual(len(self._suggest("sekai")), 1)


class NormalizeTagTests(SimpleTestCase):
    def test_case_accents_plurals_and_punctuation_fold_together(self):
        self.assertEqual(normalize_tag("Isekai"), normalize_tag("isekai"))
        self.assertEqual(normalize_tag("Isekai"), normalize_tag("ISEKAI"))
        self.assertEqual(normalize_tag("Réincarnation"), normalize_tag("reincarnation"))
        self.assertEqual(normalize_tag("Action"), normalize_tag("actions"))
        self.assertEqual(normalize_tag("Sci-Fi"), normalize_tag("sci fi"))
        self.assertEqual(normalize_tag("Abilities"), normalize_tag("ability"))

    def test_distinct_concepts_stay_apart(self):
        self.assertNotEqual(normalize_tag("Male Lead"), normalize_tag("Female Lead"))
        self.assertNotEqual(normalize_tag("Manhua"), normalize_tag("Manhwa"))
        self.assertNotEqual(normalize_tag("Eastern"), normalize_tag("Western"))

    def test_punctuation_only_name_keeps_a_key(self):
        self.assertEqual(normalize_tag("!!!"), "!!!")

    def test_key_is_truncated_to_column_width(self):
        self.assertEqual(len(normalize_tag("x" * 250)), 100)


class TagResolveTests(TestCase):
    def test_save_sets_normalized_key(self):
        tag = Tag.objects.create(name="Réincarnation")
        self.assertEqual(tag.normalized, "reincarnation")

    def test_resolve_folds_case_and_plural_onto_existing_tag(self):
        action = Tag.objects.create(name="Action")
        self.assertEqual(Tag.resolve("action"), action)
        self.assertEqual(Tag.resolve("ACTIONS"), action)
        self.assertEqual(Tag.objects.count(), 1)

    def test_resolve_creates_each_tag_once(self):
        first = Tag.resolve("  New Tag  ")
        second = Tag.resolve("new tags")
        self.assertEqual(first, second)
        self.assertEqual(first.name, "New Tag")
        self.assertEqual(Tag.objects.count(), 1)

    def test_resolve_follows_alias(self):
        canonical = Tag.objects.create(name="Isekai")
        TagAlias.objects.create(name="Another World", tag=canonical)
        self.assertEqual(Tag.resolve("another world"), canonical)
        self.assertEqual(Tag.objects.count(), 1)

    def test_resolve_falls_back_to_alias_after_insert_race(self):
        canonical = Tag.objects.create(name="Isekai")
        with mock.patch.object(Tag, "find", side_effect=[None, canonical]), \
                mock.patch.object(type(Tag.objects), "get_or_create", side_effect=IntegrityError("race")):
            self.assertEqual(Tag.resolve("Another World"), canonical)

    def test_resolve_reraises_when_nothing_matches_after_race(self):
        with mock.patch.object(Tag, "find", side_effect=[None, None]), \
                mock.patch.object(type(Tag.objects), "get_or_create", side_effect=IntegrityError("race")):
            with self.assertRaises(IntegrityError):
                Tag.resolve("Nothing")

    def test_find_never_creates(self):
        self.assertIsNone(Tag.find("Nothing Here"))
        self.assertEqual(Tag.objects.count(), 0)

    def test_resolve_truncates_overlong_name(self):
        tag = Tag.resolve("x" * 250)

        self.assertEqual(len(tag.name), 100)
        self.assertTrue(Tag.objects.filter(name="x" * 100).exists())


class TagMergeUndoTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.external = ExternalSource.objects.create(source_name="s")
        self.s1 = self._source("http://s/1")
        self.s2 = self._source("http://s/2")
        self.s3 = self._source("http://s/3")
        self.target = Tag.objects.create(name="Isekai")
        self.source = Tag.objects.create(name="Another World")
        self.s1.tags.add(self.target)
        self.s2.tags.add(self.target, self.source)
        self.s3.tags.add(self.source)
        TagAlias.objects.create(name="Otherworld", tag=self.source)

    def _source(self, url):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )

    def test_merge_records_an_applied_candidate_with_its_undo_entry(self):
        merge_tags(self.source, self.target)

        candidate = tag_rows().get()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(candidate.decided_by, Candidate.DECIDED_HUMAN)
        [entry] = candidate.undo
        self.assertEqual(entry["type"], "tag_merge")
        self.assertEqual(entry["source_name"], "Another World")
        self.assertEqual(entry["target_id"], self.target.pk)
        self.assertEqual(sorted(entry["all_source_ids"]), sorted([self.s2.pk, self.s3.pk]))
        self.assertEqual(entry["added_source_ids"], [self.s3.pk])
        self.assertEqual(len(entry["moved_alias_ids"]), 1)
        self.assertEqual(set(self.target.novels.all()), {self.s1, self.s2, self.s3})

    def test_undo_restores_links_and_aliases(self):
        merge_tags(self.source, self.target)
        candidate = tag_rows().get()

        undo_candidate(candidate)

        restored = Tag.objects.get(name="Another World")
        self.assertEqual(set(restored.novels.all()), {self.s2, self.s3})
        self.assertEqual(set(self.target.novels.all()), {self.s1, self.s2})
        self.assertEqual(TagAlias.objects.get(name="Otherworld").tag, restored)
        self.assertFalse(TagAlias.objects.filter(name="Another World").exists())
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_UNDONE)
        self.assertIsNotNone(candidate.undone_at)
        with self.assertRaises(CandidateError):
            undo_candidate(candidate)

    def test_rename_is_undone_through_the_candidate_that_holds_it(self):
        # A rename the LLM proposed as a set's canonical name, held by that set's candidate.
        entry = merge_service.apply_rename(self.source, "Isekai World")
        self.assertEqual(TagAlias.objects.get(name="Another World").tag, self.source)
        candidate = tag_candidate(self.source, status=Candidate.STATUS_APPLIED, undo=[entry])

        undo_candidate(candidate)

        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "Another World")
        self.assertFalse(TagAlias.objects.filter(name="Another World").exists())

    def test_admin_rename_records_a_candidate_that_undoes_it(self):
        rename_tag(self.source, "Isekai World")

        candidate = tag_rows().get()
        self.assertEqual((candidate.status, candidate.decided_by), (Candidate.STATUS_APPLIED, Candidate.DECIDED_HUMAN))
        undo_candidate(candidate)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "Another World")

    def test_rename_to_the_same_name_records_nothing(self):
        rename_tag(self.source, "Another World")
        self.assertFalse(tag_rows().exists())

    def test_undo_refuses_an_entry_marked_not_undoable(self):
        candidate = tag_candidate(
            self.source, status=Candidate.STATUS_APPLIED,
            undo=[{"type": "tag_merge", "legacy_id": 1, "undoable": False}],
        )
        with self.assertRaisesRegex(CandidateError, "without the data needed"):
            undo_candidate(candidate)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)

    def test_rename_onto_existing_key_is_refused(self):
        with self.assertRaises(MergeError):
            rename_tag(self.source, "ISEKAI")


class TagAdultPropagationTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.external = ExternalSource.objects.create(source_name="s")

    def _source(self, url, **kwargs):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url, **kwargs
        )

    def test_import_with_r18_tag_flags_source(self):
        Tag.objects.create(name="Harem", is_adult=True)
        source = self._source("http://s/1")
        _set_source_tags(source, ["Harem"])
        source.refresh_from_db()
        self.assertTrue(source.is_adult)

    def test_source_detail_lists_its_r18_tags(self):
        from ..serializers import NovelSourceSerializer

        Tag.objects.create(name="Harem", is_adult=True)
        Tag.objects.create(name="Isekai")
        source = self._source("http://s/3")
        _set_source_tags(source, ["Harem", "Isekai"])
        data = NovelSourceSerializer(source, profile="detail").data
        self.assertEqual(data["adult_tags"], ["Harem"])

    def test_import_with_plain_tags_leaves_source_alone(self):
        Tag.objects.create(name="Isekai")
        source = self._source("http://s/2")
        _set_source_tags(source, ["Isekai"])
        source.refresh_from_db()
        self.assertFalse(source.is_adult)

    def test_unflagging_a_tag_clears_only_the_sources_it_made_adult(self):
        tag = Tag.objects.create(name="Adult", is_adult=True)
        other_r18 = Tag.objects.create(name="Smut", is_adult=True)
        only_tag = self._source("http://s/7")
        own_flag = self._source("http://s/8", adult_from_source=True)
        two_tags = self._source("http://s/9")
        for source in (only_tag, own_flag, two_tags):
            _set_source_tags(source, ["Adult"])
        two_tags.tags.add(other_r18)

        Tag.objects.filter(pk=tag.pk).update(is_adult=False)
        self.assertEqual(refresh_adult_for_tags([tag.pk]), (0, 1))

        for source in (only_tag, own_flag, two_tags):
            source.refresh_from_db()
        self.assertFalse(only_tag.is_adult)
        self.assertTrue(own_flag.is_adult)
        self.assertTrue(two_tags.is_adult)

    def test_merge_into_r18_tag_flags_moved_sources(self):
        target = Tag.objects.create(name="Harem", is_adult=True)
        other = Tag.objects.create(name="Reverse Harem")
        source = self._source("http://s/5")
        source.tags.add(other)
        merge_tags(other, target)
        source.refresh_from_db()
        self.assertTrue(source.is_adult)

    def test_undoing_a_merge_restores_r18_flags_and_sources(self):
        smut = Tag.objects.create(name="Smut", is_adult=True)
        erotica = Tag.objects.create(name="Erotica")
        moved = self._source("http://s/13")
        plain = self._source("http://s/14")
        _set_source_tags(moved, ["Smut"])
        _set_source_tags(plain, ["Erotica"])
        merge_tags(smut, erotica)
        plain.refresh_from_db()
        self.assertTrue(plain.is_adult)  # Erotica took Smut's R18 flag

        undo_candidate(tag_rows().get())
        erotica.refresh_from_db()
        moved.refresh_from_db()
        plain.refresh_from_db()
        self.assertFalse(erotica.is_adult)
        self.assertTrue(Tag.objects.get(name="Smut").is_adult)
        self.assertTrue(moved.is_adult)
        self.assertFalse(plain.is_adult)

    def test_merging_r18_tag_keeps_flag_on_target(self):
        target = Tag.objects.create(name="Romance")
        adult = Tag.objects.create(name="Adult Content", is_adult=True)
        merge_tags(adult, target)
        target.refresh_from_db()
        self.assertTrue(target.is_adult)


class NovelMajorityAdultTests(TestCase):
    """A novel is adult when strictly more than half of its sources are."""

    def _novel(self, slug, adult_flags):
        novel = Novel.objects.create(title=slug, slug=slug, novel_path=slug)
        for index, is_adult in enumerate(adult_flags):
            NovelFromSource.objects.create(
                novel=novel,
                external_source=ExternalSource.objects.create(source_name=f"{slug}-{index}"),
                title=slug,
                source_url=f"http://{slug}/{index}",
                is_adult=is_adult,
            )
        return novel

    def setUp(self):
        self.one_of_one = self._novel("one-of-one", [True])
        self.one_of_two = self._novel("one-of-two", [True, False])
        self.two_of_three = self._novel("two-of-three", [True, True, False])
        self.clean = self._novel("clean", [False])

    def _adult_ids(self):
        return set(adult_novel_ids().values_list("novel_id", flat=True))

    def _visible_ids(self, viewer=None):
        public = public_novels(Novel.objects.all())
        visible = exclude_adult(Novel.objects.all(), viewer)
        self.assertEqual(set(public.values_list("pk", flat=True)),
                         set(visible.values_list("pk", flat=True)))
        return set(public.values_list("pk", flat=True))

    def test_one_of_one_is_adult(self):
        self.assertIn(self.one_of_one.pk, self._adult_ids())
        self.assertTrue(is_majority_adult(self.one_of_one.sources.all()))
        self.assertNotIn(self.one_of_one.pk, self._visible_ids())

    def test_one_of_two_is_not_adult(self):
        self.assertNotIn(self.one_of_two.pk, self._adult_ids())
        self.assertFalse(is_majority_adult(self.one_of_two.sources.all()))
        self.assertIn(self.one_of_two.pk, self._visible_ids())

    def test_two_of_three_is_adult(self):
        self.assertIn(self.two_of_three.pk, self._adult_ids())
        self.assertTrue(is_majority_adult(self.two_of_three.sources.all()))
        self.assertNotIn(self.two_of_three.pk, self._visible_ids())

    def test_public_sources_follow_the_novel_rule(self):
        visible = public_sources(NovelFromSource.objects.all())
        novel_ids = set(visible.values_list("novel_id", flat=True))
        self.assertEqual(novel_ids, {self.one_of_two.pk, self.clean.pk})

    def test_novel_serializer_reports_the_same_rule(self):
        from ..serializers import NovelSerializer

        flags = {
            novel.pk: NovelSerializer(novel, context={"request": None}).data["is_adult"]
            for novel in (self.one_of_one, self.one_of_two, self.two_of_three, self.clean)
        }
        self.assertEqual(flags, {
            self.one_of_one.pk: True,
            self.one_of_two.pk: False,
            self.two_of_three.pk: True,
            self.clean.pk: False,
        })


class BuildClustersTests(SimpleTestCase):
    def test_respects_max_size(self):
        edges = {
            (1, 2): {"embed": 0.9},
            (2, 3): {"embed": 0.9},
            (3, 4): {"embed": 0.9},
        }
        clusters = tms.build_clusters(edges, max_size=2)
        self.assertEqual([ids for ids, _ in clusters], [[1, 2], [3, 4]])

    def test_drops_blocked_pairs_before_clustering(self):
        edges = {(1, 2): {"embed": 0.95}, (2, 3): {"trgm": 0.7}}
        clusters = tms.build_clusters(edges, max_size=12, blocked=[pair_key(2, 1)])
        self.assertEqual(clusters, [([2, 3], {"2-3": {"trgm": 0.7}})])

    def test_no_edges_no_clusters(self):
        self.assertEqual(tms.build_clusters({}, max_size=12), [])


class EdgeSignalTests(SimpleTestCase):
    def test_embedding_neighbours_above_floor(self):
        matrix = np.array([[1.0, 0.0], [0.99, 0.1], [0.0, 1.0]], dtype=np.float32)
        edges = tms.embedding_edges([1, 2, 3], matrix, top_k=2, min_cos=0.9)
        self.assertEqual(set(edges), {(1, 2)})
        self.assertGreater(edges[(1, 2)], 0.9)

    def test_cooccurrence_needs_different_sources_of_the_same_novels(self):
        rows = [
            # Tags 10 and 11 sit on different sources of the same two novels.
            (1, 10, 100), (2, 11, 100),
            (3, 10, 101), (4, 11, 101),
            # Tags 20 and 21 always share one source: synonyms, never an edge.
            (5, 20, 102), (5, 21, 102),
            (6, 20, 103), (6, 21, 103),
        ]
        edges = tms.cooccurrence_edges(rows, min_novels=2, min_ratio=0.3, top_k=5)
        self.assertIn((10, 11), edges)
        self.assertNotIn((20, 21), edges)


class JudgeTagMergeTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.external = ExternalSource.objects.create(source_name="s")
        self.isekai = Tag.objects.create(name="Isekai")
        self.another = Tag.objects.create(name="Another World")
        self.s1 = self._source("http://s/1")
        self.s2 = self._source("http://s/2")
        self.s1.tags.add(self.isekai)
        self.s2.tags.add(self.isekai, self.another)

    def _source(self, url):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )

    def test_valid_answer_merges_into_existing_canonical_tag(self):
        candidate = tag_candidate(self.isekai, self.another)
        chat = run_judge(answer(
            {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95}
        ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(candidate.decided_by, Candidate.DECIDED_LLM)
        self.assertFalse(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertEqual([entry["type"] for entry in candidate.undo], ["tag_merge"])
        self.assertEqual(TagAlias.objects.get(name="Another World").tag, self.isekai)
        self.assertEqual(chat.call_count, 2)
        self.assertIn("(2 novels)", chat.call_args_list[0][0][0][-1]["content"])

    def test_canonical_name_renames_most_used_member(self):
        otherworld = Tag.objects.create(name="Otherworld")
        tale = Tag.objects.create(name="Other World Tale")
        self._source("http://s/3").tags.add(otherworld)
        self._source("http://s/4").tags.add(otherworld)
        self._source("http://s/5").tags.add(tale)
        candidate = tag_candidate(tale, otherworld)

        run_judge(answer(
            {"members": ["t1", "t2"], "canonical": "Other Realm", "confidence": 0.95}
        ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        survivor = Tag.objects.get(name="Other Realm")
        self.assertEqual(survivor.pk, otherworld.pk)
        self.assertFalse(Tag.objects.filter(pk=tale.pk).exists())
        self.assertEqual(TagAlias.objects.get(name="Otherworld").tag, survivor)
        self.assertEqual({entry["type"] for entry in candidate.undo}, {"tag_merge", "tag_rename"})

    def test_low_confidence_goes_to_review_without_changes(self):
        candidate = tag_candidate(self.isekai, self.another)
        run_judge(answer(
            {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.7}
        ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertIn("low confidence", candidate.reason)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertEqual(candidate.undo, [])

    def test_sets_below_the_confidence_floor_are_rejected_without_retry(self):
        candidate = tag_candidate(self.isekai, self.another)
        chat = run_judge(answer(
            {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.4}
        ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(candidate.verdict["answer"], "no")
        self.assertEqual(candidate.attempts, 0)
        self.assertEqual(chat.call_count, 1)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_set_exactly_at_the_confidence_floor_is_kept(self):
        candidate = tag_candidate(self.isekai, self.another)
        with override_settings(TAG_MERGE_MIN_CONFIDENCE=0.5):
            run_judge(answer(
                {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.5}
            ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertIn("low confidence", candidate.reason)
        self.assertEqual(len(candidate.verdict["sets"]), 1)

    def test_set_just_below_the_confidence_floor_is_dropped(self):
        candidate = tag_candidate(self.isekai, self.another)
        with override_settings(TAG_MERGE_MIN_CONFIDENCE=0.5):
            run_judge(answer(
                {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.49}
            ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(candidate.verdict["answer"], "no")
        self.assertEqual(candidate.attempts, 0)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_set_without_a_confidence_is_retried_not_rejected(self):
        candidate = tag_candidate(self.isekai, self.another)
        chat = run_judge(answer({"members": ["t1", "t2"], "canonical": "Isekai"}))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 1)
        self.assertEqual(chat.call_count, 1)
        self.assertIn("no usable confidence", candidate.reason)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_verdict_keeps_the_glosses_of_the_reply(self):
        candidate = tag_candidate(self.isekai, self.another)
        run_judge({"groups": [{
            "group": 1,
            "glosses": "t2=reincarnation",
            "sets": [{"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95}],
        }]})

        candidate.refresh_from_db()
        self.assertEqual(candidate.verdict["glosses"], "t2=reincarnation")

    def test_verifier_removes_a_member_and_the_rest_of_the_set_applies(self):
        third = Tag.objects.create(name="Third Tag")
        candidate = tag_candidate(self.isekai, self.another, third)
        chat = run_judge(
            answer({"members": ["t1", "t2", "t3"], "canonical": "Isekai", "confidence": 0.95}),
            verify={"sets": [{"set": "s1", "keep": ["t1", "t2"]}]},
        )

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(chat.call_count, 2)
        self.assertFalse(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertTrue(Tag.objects.filter(pk=third.pk).exists())
        self.assertEqual(candidate.verdict["sets"][0]["members"], [self.isekai.pk, self.another.pk])

    def test_verifier_drops_a_set_below_two_members_and_applies_the_rest(self):
        third, fourth = make_tags("Third Tag", "Fourth Tag")
        candidate = tag_candidate(self.isekai, self.another, third, fourth)
        run_judge(
            answer(
                {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95},
                {"members": ["t3", "t4"], "canonical": "Third Tag", "confidence": 0.95},
            ),
            verify={"sets": [{"set": "s1", "keep": ["t1", "t2"]}, {"set": "s2", "keep": ["t3"]}]},
        )

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(len(candidate.verdict["sets"]), 1)
        self.assertTrue(Tag.objects.filter(pk=third.pk).exists())
        self.assertTrue(Tag.objects.filter(pk=fourth.pk).exists())
        self.assertFalse(Tag.objects.filter(pk=self.another.pk).exists())

    def test_verifier_removing_every_set_rejects_the_candidate(self):
        candidate = tag_candidate(self.isekai, self.another)
        chat = run_judge(
            answer({"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95}),
            verify={"sets": [{"set": "s1", "keep": ["t1"]}]},
        )

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertIn("verification removed every set", candidate.reason)
        self.assertEqual(chat.call_count, 2)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_unparseable_verification_is_retried_not_settled(self):
        candidate = tag_candidate(self.isekai, self.another)
        run_judge(
            answer({"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95}),
            verify="no json",
        )

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 1)
        self.assertIn("no JSON object", candidate.reason)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_verification_maps_sets_across_the_chunk_boundary(self):
        # 41 proposed sets with verify_sets=40: set s41 is checked by the second call.
        tags = make_tags(*(f"Concept Tag {number}" for number in range(1, 84)))
        candidate = tag_candidate(*tags)
        sets = [
            {
                "members": [f"t{2 * number - 1}", f"t{2 * number}"],
                "canonical": f"Concept {number}",
                "confidence": 0.95,
            }
            for number in range(1, 41)
        ]
        sets.append({"members": ["t81", "t82", "t83"], "canonical": "Concept 41", "confidence": 0.95})

        def drop_t83_from_s41(messages):
            reply = keep_everything(messages)
            for item in reply["sets"]:
                if item["set"] == "s41":
                    item["keep"].remove("t83")
            return reply

        chat = run_judge(answer(*sets), verify=drop_t83_from_s41)

        candidate.refresh_from_db()
        self.assertEqual(chat.call_count, 3)
        self.assertIn("Set s41:", chat.call_args_list[2][0][0][-1]["content"])
        self.assertEqual(len(candidate.verdict["sets"]), 41)
        self.assertEqual(candidate.verdict["sets"][0]["members"], [tags[0].pk, tags[1].pk])
        self.assertEqual(candidate.verdict["sets"][40]["members"], [tags[80].pk, tags[81].pk])

    def test_prompts_carry_the_stricter_rules(self):
        self.assertEqual(llm_tasks.REGISTRY["tag_merge"].prompt_version, "3")
        for phrase in (
            "Police / Detectives", "Danmei (BL genre) / Romance", "Completed", "One set holds one concept",
        ):
            self.assertIn(phrase, tms.SYSTEM_PROMPT)
        self.assertIn("You may only remove members", tms.VERIFY_PROMPT)

    def test_widely_used_tags_go_to_review(self):
        candidate = tag_candidate(self.isekai, self.another)
        self._source("http://s/3").tags.add(self.another)
        with override_settings(TAG_BIG_TAG_USAGE=1):
            run_judge(answer(
                {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.99}
            ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertIn("widely used", candidate.reason)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_pair_marked_not_mergeable_goes_to_review(self):
        # A rejected pair blocks that pair inside any larger candidate that holds it.
        third = Tag.objects.create(name="Third Tag")
        tag_candidate(self.isekai, self.another, status=Candidate.STATUS_REJECTED)
        candidate = tag_candidate(self.isekai, self.another, third)

        run_judge(answer(
            {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.99}
        ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertIn("not mergeable", candidate.reason)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_garbage_labels_are_dropped(self):
        candidate = tag_candidate(self.isekai, self.another)
        run_judge(answer(
            {"members": ["t1", "t9", "t2", 5], "canonical": "Isekai", "confidence": 0.95},
            {"members": ["t1", "t7"], "canonical": "Other", "confidence": 0.99},
        ))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(sum(entry["type"] == "tag_merge" for entry in candidate.undo), 1)
        self.assertEqual(candidate.verdict["sets"][0]["members"], [self.isekai.pk, self.another.pk])

    def test_sets_with_only_unknown_labels_are_retried_not_rejected(self):
        # "T1" is not a label the prompt sent: the answer is unusable, not a "no".
        candidate = tag_candidate(self.isekai, self.another)
        run_judge(answer({"members": ["T1", "T2"], "canonical": "Isekai", "confidence": 0.99}))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 1)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_unparseable_answer_is_retried_with_backoff(self):
        candidate = tag_candidate(self.isekai, self.another)
        run_judge("no json")

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 1)
        self.assertIsNotNone(candidate.not_before)
        self.assertIn("no JSON object", candidate.reason)

    def test_reviewer_applies_a_review_candidate(self):
        candidate = tag_candidate(self.isekai, self.another, status=Candidate.STATUS_REVIEW, verdict={
            "answer": "yes", "confidence": 0.2, "reason": "", "sets": [{
                "members": [self.isekai.pk, self.another.pk],
                "canonical": "Isekai",
                "confidence": 0.2,
            }],
        })

        apply_candidate(candidate)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_APPLIED)
        self.assertFalse(Tag.objects.filter(pk=self.another.pk).exists())


class FindTagMergeCandidatesTests(TestCase):
    def test_cooccurring_tags_become_one_pending_candidate_once(self):
        novel_a = Novel.objects.create(title="A", slug="a", novel_path="a")
        novel_b = Novel.objects.create(title="B", slug="b", novel_path="b")
        external = ExternalSource.objects.create(source_name="s")
        isekai = Tag.objects.create(name="Isekai")
        another = Tag.objects.create(name="Another World")
        for novel, url in [(novel_a, "http://s/a"), (novel_b, "http://s/b")]:
            first = NovelFromSource.objects.create(
                novel=novel, external_source=external, title="x", source_url=url + "1"
            )
            second = NovelFromSource.objects.create(
                novel=novel, external_source=external, title="x", source_url=url + "2"
            )
            first.tags.add(isekai)
            second.tags.add(another)

        call_command("find_tag_merge_candidates", "--skip-embed")
        call_command("find_tag_merge_candidates", "--skip-embed")

        candidate = tag_rows().get()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(sorted(candidate.target_ids), sorted([isekai.pk, another.pk]))


class EmbeddingRequestTests(SimpleTestCase):
    class _Session:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            count = len(kwargs["json"]["input"])
            return _FakeResponse({"data": [
                {"index": i, "embedding": [1.0, 0.0]} for i in range(count)
            ]})

    def test_default_provider_is_jina_with_text_matching_task(self):
        self.assertEqual(settings.EMBED_PROVIDER, "jina")
        self.assertEqual(settings.EMBED_MODEL, "jina-embeddings-v5-omni-small")
        session = self._Session()
        with override_settings(EMBED_API_KEY="k"):
            vectors = embedding_service.embed(["isekai"], session=session)
        self.assertEqual(vectors.shape, (1, 2))
        url, kwargs = session.calls[0]
        self.assertEqual(url, embedding_service.PROVIDER_URLS["jina"])
        self.assertEqual(kwargs["json"]["task"], "text-matching")

    def test_other_providers_send_no_task_field(self):
        session = self._Session()
        with override_settings(EMBED_API_KEY="k", EMBED_PROVIDER="voyage"):
            embedding_service.embed(["isekai"], session=session)
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://api.voyageai.com/v1/embeddings")
        self.assertNotIn("task", kwargs["json"])


class _FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class SafeguardSurvivorTests(TestCase):
    """A set whose canonical name resolves outside the group is held for a human."""

    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="sg", novel_path="sg")
        self.external = ExternalSource.objects.create(source_name="sg")
        self.isekai = Tag.objects.create(name="Isekai")
        self.another = Tag.objects.create(name="Another World")
        self.outside = Tag.objects.create(name="Shared Name")
        self._source("http://sg/1").tags.add(self.isekai)
        self._source("http://sg/2").tags.add(self.another)
        self.candidate = tag_candidate(self.isekai, self.another)
        self.judgement = {"answer": "yes", "confidence": 0.99, "reason": "", "sets": [{
            "members": [self.isekai.pk, self.another.pk],
            "canonical": "Shared Name",
            "confidence": 0.99,
        }]}

    def _source(self, url):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )

    def test_merge_into_outside_tag_goes_to_review(self):
        status = llm_tasks.settle(llm_tasks.REGISTRY["tag_merge"], self.candidate, self.judgement)

        self.assertEqual(status, Candidate.STATUS_REVIEW)
        self.candidate.refresh_from_db()
        self.assertIn("outside the group", self.candidate.reason)
        self.assertTrue(Tag.objects.filter(pk=self.isekai.pk).exists())

    def test_reviewer_applies_a_merge_into_outside_tag(self):
        # The reviewer is the safeguard: their apply does not run the safeguards again.
        llm_tasks.settle(llm_tasks.REGISTRY["tag_merge"], self.candidate, self.judgement)
        self.candidate.refresh_from_db()

        apply_candidate(self.candidate)

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(self.candidate.decided_by, Candidate.DECIDED_HUMAN)
        self.assertFalse(Tag.objects.filter(pk__in=[self.isekai.pk, self.another.pk]).exists())
        self.assertTrue(Tag.objects.filter(pk=self.outside.pk).exists())

    def test_llm_apply_still_runs_the_safeguards(self):
        self.candidate.verdict = self.judgement
        with self.assertRaises(tms.NeedsReview):
            llm_tasks.REGISTRY["tag_merge"].apply_change(self.candidate, self.judgement)
        self.assertTrue(Tag.objects.filter(pk=self.isekai.pk).exists())


class RenameAliasClashTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="rc", novel_path="rc")
        self.external = ExternalSource.objects.create(source_name="rc")
        self.isekai = Tag.objects.create(name="Isekai")
        self.other = Tag.objects.create(name="Other Tag")
        TagAlias.objects.create(name="Realm", tag=self.isekai)

    def test_rename_onto_alias_of_another_tag_is_refused(self):
        with self.assertRaises(MergeError):
            rename_tag(self.other, "realm")
        self.other.refresh_from_db()
        self.assertEqual(self.other.name, "Other Tag")


class ChainedUndoTests(TestCase):
    """A merge whose target was later merged away is undone only after the later merge."""

    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="ch", novel_path="ch")
        self.external = ExternalSource.objects.create(source_name="ch")
        self.s1 = self._source("http://ch/1")
        self.s2 = self._source("http://ch/2")
        self.alpha = Tag.objects.create(name="Alpha")
        self.beta = Tag.objects.create(name="Beta")
        self.gamma = Tag.objects.create(name="Gamma")
        self.s1.tags.add(self.alpha)
        self.s2.tags.add(self.beta)
        alpha_pk, beta_pk = self.alpha.pk, self.beta.pk  # read before delete() clears them
        merge_tags(self.alpha, self.beta)
        merge_tags(self.beta, self.gamma)
        self.first = tag_rows().get(signature=sorted_pk_signature([alpha_pk, beta_pk]))
        self.second = tag_rows().exclude(pk=self.first.pk).get()

    def _source(self, url):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )

    def test_older_merge_is_refused_while_the_later_one_stands(self):
        with self.assertRaisesRegex(MergeError, "merged away"):
            undo_candidate(self.first)

    def test_undoing_the_chain_newest_first_restores_every_tag(self):
        undo_candidate(self.second)
        undo_candidate(self.first)

        alpha = Tag.objects.get(name="Alpha")
        beta = Tag.objects.get(name="Beta")
        self.assertEqual(set(alpha.novels.all()), {self.s1})
        self.assertEqual(set(beta.novels.all()), {self.s2})
        self.assertEqual(set(self.gamma.novels.all()), set())
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.status, Candidate.STATUS_UNDONE)
        self.assertEqual(self.second.status, Candidate.STATUS_UNDONE)

    def test_undone_chain_blocks_its_pairs(self):
        undo_candidate(self.second)
        undo_candidate(self.first)

        alpha = Tag.objects.get(name="Alpha")
        beta = Tag.objects.get(name="Beta")
        self.assertEqual(
            blocked_pairs(Candidate.KIND_TAG_MERGE),
            {pair_key(alpha.pk, beta.pk), pair_key(beta.pk, self.gamma.pk)},
        )


class TagAdminRenameTests(TestCase):
    def setUp(self):
        self.tag = Tag.objects.create(name="Isekai")
        Tag.objects.create(name="Romance")
        TagAlias.objects.create(name="Another World", tag=self.tag)

    def test_form_rejects_name_of_another_tag(self):
        form = TagAdminForm(data={"name": "romances"}, instance=self.tag)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_form_rejects_name_of_an_alias(self):
        other = Tag.objects.create(name="Something")
        form = TagAdminForm(data={"name": "another world"}, instance=other)
        self.assertFalse(form.is_valid())
        self.assertIn("alias", str(form.errors))

    def test_saving_a_new_name_keeps_the_old_name_as_an_alias(self):
        form = TagAdminForm(data={"name": "Isekai Life"}, instance=self.tag)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        TagAdmin(Tag, admin.site).save_model(None, obj, form, change=True)

        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, "Isekai Life")
        self.assertEqual(TagAlias.objects.get(name="Isekai").tag, self.tag)


class ImportTagLockingTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="imp", novel_path="imp")
        self.external = ExternalSource.objects.create(source_name="imp")
        self.source = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url="http://imp/1"
        )
        self.isekai = Tag.objects.create(name="Isekai")
        self.action = Tag.objects.create(name="Action")
        TagAlias.objects.create(name="Another World", tag=self.isekai)

    def test_names_resolve_to_distinct_tags(self):
        _set_source_tags(self.source, ["Isekai", "isekai", "Action", ""])
        self.assertEqual(set(self.source.tags.all()), {self.isekai, self.action})

    def test_alias_name_links_the_survivor(self):
        _set_source_tags(self.source, ["Another World"])
        self.assertEqual(list(self.source.tags.all()), [self.isekai])

    def test_merged_away_tag_is_retried_with_one_lock_per_attempt(self):
        # The first lock reports Action as gone (merged away between resolve and
        # lock). The retry resolves the names again and locks once more.
        real_lock = sources_models.lock_pks
        seen = []

        def racing_lock(model, pks):
            seen.append(sorted(pks))
            result = real_lock(model, pks)
            if len(seen) == 1:
                result = result - {self.action.pk}
            return result

        with mock.patch.object(sources_models, "lock_pks", side_effect=racing_lock):
            _set_source_tags(self.source, ["Isekai", "Action"])

        self.assertEqual(len(seen), 2)
        self.assertIn(self.isekai, set(self.source.tags.all()))

    def test_gives_up_after_the_attempt_limit(self):
        with mock.patch.object(sources_models, "lock_pks", return_value=set()) as lock:
            with self.assertRaises(TagImportError):
                _set_source_tags(self.source, ["Isekai"])
        self.assertEqual(lock.call_count, TAG_IMPORT_ATTEMPTS)
        self.assertFalse(self.source.tags.exists())

    def test_source_tags_are_replaced_on_import_path(self):
        self.source.tags.add(self.action)
        _set_source_tags(self.source, ["Isekai"])
        self.assertEqual(list(self.source.tags.all()), [self.isekai])


class NoMergePairMoveTests(TestCase):
    def setUp(self):
        self.source = Tag.objects.create(name="Source Tag")
        self.target = Tag.objects.create(name="Target Tag")
        self.other = Tag.objects.create(name="Other")
        self.novel = Novel.objects.create(title="N", slug="nm", novel_path="nm")
        self.external = ExternalSource.objects.create(source_name="nm")

    def test_rejected_pairs_follow_the_target_and_duplicates_collapse(self):
        tag_candidate(self.source, self.other, status=Candidate.STATUS_REJECTED)
        tag_candidate(self.source, self.target, status=Candidate.STATUS_REJECTED)
        tag_candidate(self.target, self.other, status=Candidate.STATUS_REJECTED)

        merge_tags(self.source, self.target)

        self.assertEqual(
            blocked_pairs(Candidate.KIND_TAG_MERGE),
            {pair_key(self.target.pk, self.other.pk)},
        )


class EmbeddingResetTests(TestCase):
    def test_rename_clears_stored_vector(self):
        tag = Tag.objects.create(name="Isekai", embedding=b"\x00\x00\x80\x3f", embedding_model="m")
        rename_tag(tag, "Isekai Life")
        tag.refresh_from_db()
        self.assertIsNone(tag.embedding)
        self.assertEqual(tag.embedding_model, "")

    def test_undo_rename_clears_stored_vector(self):
        tag = Tag.objects.create(name="Isekai")
        entry = merge_service.apply_rename(tag, "Isekai Life")
        candidate = tag_candidate(tag, status=Candidate.STATUS_APPLIED, undo=[entry])
        Tag.objects.filter(pk=tag.pk).update(embedding=b"\x00\x00\x80\x3f", embedding_model="m")
        undo_candidate(candidate)
        tag.refresh_from_db()
        self.assertIsNone(tag.embedding)
        self.assertEqual(tag.embedding_model, "")


class BigTagSettingTests(SimpleTestCase):
    def test_big_tag_usage_threshold(self):
        self.assertEqual(settings.TAG_BIG_TAG_USAGE, 200)


class CooccurrenceSharedSourceTests(SimpleTestCase):
    def test_pair_sharing_a_source_is_dropped_even_with_other_co_occurrence(self):
        rows = [
            # Tags 10 and 20 share source 1 on novel 100 ...
            (1, 10, 100), (1, 20, 100),
            # ... and also co-occur on novel 101 through different sources.
            (2, 10, 101), (3, 20, 101),
        ]
        edges = tms.cooccurrence_edges(rows, min_novels=2, min_ratio=0.3, top_k=5)
        self.assertNotIn((10, 20), edges)

    def test_pair_without_shared_source_is_kept(self):
        rows = [(1, 10, 100), (2, 20, 100), (3, 10, 101), (4, 20, 101)]
        edges = tms.cooccurrence_edges(rows, min_novels=2, min_ratio=0.3, top_k=5)
        self.assertIn((10, 20), edges)


class EmbedChunkingTests(SimpleTestCase):
    def test_chunked_neighbours_match_unchunked(self):
        rng = np.random.default_rng(0)
        matrix = rng.random((5, 4)).astype(np.float32)
        matrix[1] = matrix[0] * 1.01  # a near-duplicate across chunk boundaries
        ids = [10, 11, 12, 13, 14]
        full = tms.embedding_edges(ids, matrix, top_k=3, min_cos=0.0)
        with mock.patch.object(tms, "EMBED_CHUNK", 2):
            chunked = tms.embedding_edges(ids, matrix, top_k=3, min_cos=0.0)
        self.assertEqual(set(full), set(chunked))
        self.assertEqual(tms.EMBED_CHUNK, 256)


class ClusterAtomicityTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="at", novel_path="at")
        self.external = ExternalSource.objects.create(source_name="at")
        self.tags = {name: Tag.objects.create(name=name) for name in
                     ["Isekai", "Another World", "Foo Bar", "Foo Baz"]}
        for i, tag in enumerate(self.tags.values()):
            NovelFromSource.objects.create(
                novel=self.novel, external_source=self.external, title="N",
                source_url=f"http://at/{i}",
            ).tags.add(tag)
        self.ids = [self.tags[n].pk for n in ["Isekai", "Another World", "Foo Bar", "Foo Baz"]]
        self.candidate = tag_candidate(*self.tags.values())
        self.judgement = {"answer": "yes", "confidence": 0.95, "reason": "", "sets": [
            {"members": self.ids[:2], "canonical": "Isekai", "confidence": 0.95},
            {"members": self.ids[2:], "canonical": "Foo Bar", "confidence": 0.95},
        ]}

    def test_failure_in_second_set_rolls_back_the_first(self):
        real_fold = tms.fold_tag
        calls = []

        def flaky_fold(source, target, candidate=None):
            calls.append(source.name)
            if len(calls) == 2:
                raise MergeError("boom")
            return real_fold(source, target, candidate=candidate)

        with mock.patch.object(tms, "fold_tag", side_effect=flaky_fold):
            status = llm_tasks.settle(llm_tasks.REGISTRY["tag_merge"], self.candidate, self.judgement)

        self.assertEqual(status, Candidate.STATUS_REVIEW)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.reason, "boom")
        self.assertEqual(self.candidate.undo, [])
        self.assertTrue(Tag.objects.filter(name="Another World").exists())


class JudgePromptTests(SimpleTestCase):
    def test_names_are_whitespace_collapsed_and_truncated(self):
        messages = tms.build_judge_messages([[
            ("t1", "  Other \n  Name  ", 3),
            ("t2", "x" * 150, 1),
        ]])
        user = messages[-1]["content"]
        self.assertIn("t1. Other Name (3 novels)", user)
        self.assertIn("t2. " + "x" * 100 + " (1 novels)", user)
        self.assertNotIn("x" * 101, user)


class VerifyParseTests(SimpleTestCase):
    def test_empty_glosses_map_to_nothing(self):
        self.assertEqual(tms.parse_glosses(""), {})

    def test_gloss_keeps_text_after_its_first_equals_sign(self):
        self.assertEqual(tms.parse_glosses("t2=a=b; t5=ninja"), {"t2": "a=b", "t5": "ninja"})

    def test_reply_item_without_a_set_id_is_unparseable(self):
        content = json.dumps({"sets": [{"keep": ["t1"]}]})
        with self.assertRaises(llm_service.LLMParseError):
            tms.parse_verify_response(content, ["s1"])

    def test_non_dict_reply_item_is_unparseable(self):
        with self.assertRaises(llm_service.LLMParseError):
            tms.parse_verify_response(json.dumps({"sets": ["s1"]}), ["s1"])


class TagAdminMergeErrorTests(TestCase):
    def setUp(self):
        self.tag = Tag.objects.create(name="Isekai")
        user = get_user_model().objects.create_superuser(
            username="tag-admin-test", email="tag-admin@example.test", password="pw-test-123"
        )
        self.client.force_login(user)
        self.url = reverse("admin:lncrawler_api_tag_change", args=[self.tag.pk])

    def test_merge_error_is_reported_and_the_change_is_rolled_back(self):
        def half_rename_then_fail(tag, name):
            # Write the change first, then fail: the admin transaction must undo it.
            Tag.objects.filter(pk=tag.pk).update(name=name)
            raise MergeError("clash here")

        with mock.patch("lncrawler_api.admin.source_admin.rename_tag",
                        side_effect=half_rename_then_fail):
            response = self.client.post(self.url, {"name": "Renamed"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.url)
        msgs = [(m.level, str(m)) for m in get_messages(response.wsgi_request)]
        self.assertIn((django_messages.ERROR, "clash here"), msgs)
        self.assertFalse(any(level == django_messages.SUCCESS for level, _ in msgs))
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, "Isekai")


class ImportContinuesTests(TestCase):
    """A tag failure must never stop the chapters and alternative titles of an import."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-tags-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        override = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        override.enable()
        self.addCleanup(override.disable)
        Tag.objects.create(name="Isekai")

    def _write_meta(self):
        directory = os.path.join(self.tmp, "tagnovel", "src")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "meta.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"novel": {
                "title": "Tag Novel",
                "url": "http://tags/1",
                "novel_tags": ["Isekai"],
                "alternative_titles": ["Alt Title"],
                "chapters": [],
            }}, handle)
        return path

    def test_exhausted_tag_retries_keep_the_import_going(self):
        path = self._write_meta()
        with mock.patch.object(sources_models, "lock_pks", return_value=set()):
            with self.assertLogs("lncrawler_api", level="WARNING") as logs:
                source = NovelFromSource.from_meta_json(path)

        self.assertIn("Skipped tags for source", "\n".join(logs.output))
        self.assertEqual(source.alternative_titles.get().name, "Alt Title")
        self.assertFalse(source.tags.exists())

    def test_tag_error_is_caught_at_the_call_site(self):
        path = self._write_meta()
        with mock.patch.object(sources_models, "_set_source_tags",
                               side_effect=TagImportError("boom")):
            with self.assertLogs("lncrawler_api", level="WARNING"):
                source = NovelFromSource.from_meta_json(path)
        self.assertEqual(source.alternative_titles.get().name, "Alt Title")


class UndoSameKeyTagTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="sk", novel_path="sk")
        self.external = ExternalSource.objects.create(source_name="sk")
        self.source = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url="http://sk/1"
        )
        self.alpha = Tag.objects.create(name="Alpha")
        self.beta = Tag.objects.create(name="Beta")
        self.source.tags.add(self.alpha)
        merge_tags(self.alpha, self.beta)

    def test_undo_reuses_a_tag_already_carrying_the_key(self):
        # Someone recreated the same-key tag after the merge; undo must reuse it.
        again = Tag.objects.create(name="ALPHA")
        undo_candidate(tag_rows().get())

        self.assertEqual(Tag.objects.filter(normalized="alpha").count(), 1)
        self.assertEqual(Tag.objects.get(normalized="alpha").pk, again.pk)
        self.assertEqual(set(again.novels.all()), {self.source})


class RenameIntegrityTests(TestCase):
    def test_integrity_error_on_save_becomes_merge_error(self):
        tag = Tag.objects.create(name="Isekai")
        with mock.patch.object(Tag, "save", side_effect=IntegrityError("race")):
            with self.assertRaises(MergeError):
                rename_tag(tag, "Isekai Life")
        tag.refresh_from_db()
        self.assertEqual(tag.name, "Isekai")
        self.assertFalse(tag_rows().exists())


class TagR18ThresholdTests(TestCase):
    """An explicit rating on a tag that many novels use waits for a human, whatever the confidence."""

    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="r18", novel_path="r18")
        self.external = ExternalSource.objects.create(source_name="r18")
        self.tag = Tag.objects.create(name="Smut")
        for i in range(2):
            NovelFromSource.objects.create(
                novel=self.novel, external_source=self.external, title="N",
                source_url=f"http://r18/{i}",
            ).tags.add(self.tag)
        self.candidate = Candidate.objects.create(
            kind=Candidate.KIND_TAG_R18,
            signature=sorted_pk_signature([self.tag.pk]),
            target_ids=[self.tag.pk],
            target_names=[self.tag.name],
        )

    def _run(self):
        return run_judge({"tags": [{"id": self.tag.pk, "rating": "explicit", "confidence": 0.99}]},
                         task="tag_r18")

    def test_explicit_tag_on_too_many_novels_goes_to_review(self):
        with override_settings(TAG_R18_REVIEW_NOVELS=2):
            self._run()

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(self.candidate.reason, "tag on 2 novels")
        self.tag.refresh_from_db()
        self.assertFalse(self.tag.is_adult)

    def test_explicit_tag_below_the_threshold_is_flagged(self):
        with override_settings(TAG_R18_REVIEW_NOVELS=3):
            self._run()

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_APPLIED)
        self.tag.refresh_from_db()
        self.assertTrue(self.tag.is_adult)




TWO_SETS = answer(
    {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95},
    {"members": ["t3", "t4"], "canonical": "Foo Bar", "confidence": 0.95},
)


def tag_judgement(*sets):
    """A judgement as ``settle`` takes it: every proposed set confident enough to apply."""
    return {"answer": "yes", "confidence": 0.95, "reason": "", "sets": [
        {"members": [tag.pk for tag in members], "canonical": canonical, "confidence": 0.95}
        for members, canonical in sets
    ]}


class PlanChangedRetryTests(TestCase):
    """A plan that changed between its first look and the lock is retried, never applied."""

    def setUp(self):
        self.isekai, self.another, self.foo_bar, self.foo_baz = make_tags(
            "Isekai", "Another World", "Foo Bar", "Foo Baz",
        )
        self.candidate = tag_candidate(self.isekai, self.another, self.foo_bar, self.foo_baz)

    def assertRetriedNothingMerged(self):
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(self.candidate.attempts, 1)
        self.assertIsNotNone(self.candidate.not_before)
        self.assertIsNone(self.candidate.claimed_at)
        self.assertEqual(self.candidate.undo, [])
        self.assertEqual(self.candidate.reason, "tags changed while the answer was pending")
        self.assertEqual(Tag.objects.count(), 4)
        self.assertFalse(TagAlias.objects.exists())

    def test_lock_that_reports_a_tag_gone_counts_an_attempt_and_merges_nothing(self):
        # The lock returns fewer tags than the plan holds: the answer is stale.
        with mock.patch.object(tms, "lock_pks", return_value=set()):
            run_judge(TWO_SETS)
        self.assertRetriedNothingMerged()

    def test_fresh_plan_with_another_signature_counts_an_attempt_and_merges_nothing(self):
        with mock.patch.object(tms, "_plan_signature", side_effect=["before", "after"]):
            run_judge(TWO_SETS)
        self.assertRetriedNothingMerged()

    def test_retry_is_judged_alone_and_applied_on_the_next_run(self):
        with mock.patch.object(tms, "lock_pks", return_value=set()):
            run_judge(TWO_SETS)
        Candidate.objects.update(not_before=None)

        mocked = run_judge(TWO_SETS, limit=1)

        self.assertEqual(mocked.call_count, 2)
        self.assertNotIn("Group 2:", mocked.call_args_list[0][0][0][-1]["content"])
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(self.candidate.attempts, 1)
        self.assertFalse(Tag.objects.filter(name="Another World").exists())
        self.assertFalse(Tag.objects.filter(name="Foo Baz").exists())

    def test_max_attempts_closes_the_candidate_as_error(self):
        max_attempts = llm_tasks.REGISTRY["tag_merge"].max_attempts
        with mock.patch.object(tms, "lock_pks", return_value=set()):
            for _ in range(max_attempts):
                Candidate.objects.update(not_before=None)
                self.assertEqual(run_judge(TWO_SETS).call_count, 2)

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_ERROR)
        self.assertEqual(self.candidate.attempts, max_attempts)
        self.assertIsNone(self.candidate.not_before)
        self.assertEqual(self.candidate.reason, "tags changed while the answer was pending")
        self.assertEqual(Tag.objects.count(), 4)
        # An errored candidate is out of the queue: the next run makes no call.
        self.assertEqual(run_judge(TWO_SETS).call_count, 0)


class RollbackTests(TestCase):
    """A failure in a later set rolls back the earlier ones of the same candidate."""

    def setUp(self):
        self.isekai, self.another, self.foo_bar, self.foo_baz = make_tags(
            "Isekai", "Another World", "Foo Bar", "Foo Baz",
        )
        self.candidate = tag_candidate(self.isekai, self.another, self.foo_bar, self.foo_baz)
        self.judgement = tag_judgement(
            ([self.isekai, self.another], "Isekai"),
            ([self.foo_bar, self.foo_baz], "Foo Bar"),
        )

    def test_later_set_failure_leaves_no_tag_deleted_and_no_alias(self):
        real_fold = tms.fold_tag
        calls = []

        def flaky_fold(source, target, candidate=None):
            calls.append(source.name)
            if len(calls) == 2:
                raise MergeError("boom")
            return real_fold(source, target, candidate=candidate)

        with mock.patch.object(tms, "fold_tag", side_effect=flaky_fold):
            status = llm_tasks.settle(llm_tasks.REGISTRY["tag_merge"], self.candidate, self.judgement)

        self.assertEqual(status, Candidate.STATUS_REVIEW)
        self.assertEqual(len(calls), 2)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(self.candidate.reason, "boom")
        self.assertEqual(self.candidate.undo, [])
        self.assertEqual(
            set(Tag.objects.values_list("name", flat=True)),
            {"Isekai", "Another World", "Foo Bar", "Foo Baz"},
        )
        self.assertFalse(TagAlias.objects.exists())


class ReviewUnderLockTests(TestCase):
    def test_safeguard_tripping_under_the_lock_sends_the_candidate_to_review(self):
        isekai, another = make_tags("Isekai", "Another World")
        candidate = tag_candidate(isekai, another)
        judgement = tag_judgement(([isekai, another], "Isekai"))

        # The first look (judge) is clean; the read under the lock is not.
        with mock.patch.object(
            tms, "review_reasons",
            side_effect=[[], ["'Isekai' joins several widely used tags"]],
        ):
            status = llm_tasks.settle(llm_tasks.REGISTRY["tag_merge"], candidate, judgement)

        self.assertEqual(status, Candidate.STATUS_REVIEW)
        candidate.refresh_from_db()
        self.assertIn("widely used", candidate.reason)
        self.assertEqual(candidate.undo, [])
        self.assertTrue(Tag.objects.filter(name="Another World").exists())


class TagMergeIntegrityTests(TestCase):
    def test_integrity_error_while_applying_is_a_failed_attempt(self):
        isekai, another = make_tags("Isekai", "Another World")
        candidate = tag_candidate(isekai, another)
        with mock.patch.object(tms, "_apply_set", side_effect=IntegrityError("dup key")):
            run_judge(answer({"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95}))

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 1)
        self.assertIn("dup key", candidate.reason)
        self.assertTrue(Tag.objects.filter(name="Another World").exists())


class TagMergePackTests(SimpleTestCase):
    def test_a_batch_closes_once_its_tags_reach_batch_size(self):
        task = llm_tasks.TagMergeTask()
        task.batch_size = 4
        candidates = [
            SimpleNamespace(target_ids=[1, 2, 3]),
            SimpleNamespace(target_ids=[4, 5, 6]),
            SimpleNamespace(target_ids=[7, 8, 9]),
        ]
        batches = task.pack(candidates)
        self.assertEqual([[c.target_ids[0] for c in batch] for batch in batches], [[1, 4], [7]])

    def test_no_candidates_no_batches(self):
        self.assertEqual(llm_tasks.TagMergeTask().pack([]), [])


class TagMergeQueueOrderTests(TestCase):
    """Oldest first, packed to ``batch_size``; a retried candidate goes alone."""

    def setUp(self):
        self.old = tag_candidate(*make_tags("Tango", "Mango"))
        self.middle = tag_candidate(*make_tags("Samba", "Rumba"))
        self.new = tag_candidate(*make_tags("Polka", "Salsa"))

    def test_oldest_candidates_are_packed_to_batch_size_then_the_rest_follows(self):
        with mock.patch.object(llm_tasks.TagMergeTask, "batch_size", 4):
            first = run_judge(no_sets_for_each_group, limit=1)
            content = first.call_args[0][0][-1]["content"]
            self.assertIn("Tango", content)
            self.assertIn("Samba", content)
            self.assertNotIn("Polka", content)
            self.assertEqual(Candidate.objects.get(pk=self.new.pk).status, Candidate.STATUS_PENDING)

            second = run_judge(no_sets_for_each_group, limit=1)
            content = second.call_args[0][0][-1]["content"]
            self.assertIn("Polka", content)
            self.assertNotIn("Tango", content)

        for candidate in (self.old, self.middle, self.new):
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)

    def test_a_run_without_limit_makes_one_call_per_batch(self):
        with mock.patch.object(llm_tasks.TagMergeTask, "batch_size", 4):
            mocked = run_judge(no_sets_for_each_group)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(tag_rows().filter(status=Candidate.STATUS_REJECTED).count(), 3)

    def test_retried_candidate_is_sent_alone_and_fresh_ones_are_packed(self):
        Candidate.objects.filter(pk=self.old.pk).update(attempts=1)
        with mock.patch.object(llm_tasks.TagMergeTask, "batch_size", 4):
            first = run_judge(no_sets_for_each_group, limit=1)
            content = first.call_args[0][0][-1]["content"]
            self.assertIn("Samba", content)
            self.assertIn("Polka", content)
            self.assertNotIn("Tango", content)

            second = run_judge(no_sets_for_each_group, limit=1)
            content = second.call_args[0][0][-1]["content"]
            self.assertIn("Tango", content)
            self.assertNotIn("Group 2:", content)


class ClaimedCandidateTests(TestCase):
    """A candidate in flight is not claimed again, and a human cannot decide it meanwhile."""

    def test_claimed_candidate_is_not_sent_again(self):
        candidate = tag_candidate(*make_tags("Tango", "Mango"), claimed_at=timezone.now())
        mocked = run_judge(no_sets_for_each_group)
        self.assertEqual(mocked.call_count, 0)
        candidate.refresh_from_db()
        self.assertIsNotNone(candidate.claimed_at)
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)

    def test_stuck_claim_is_taken_back_after_the_window(self):
        candidate = tag_candidate(
            *make_tags("Tango", "Mango"), claimed_at=timezone.now() - timedelta(minutes=31),
        )
        mocked = run_judge(no_sets_for_each_group)
        self.assertEqual(mocked.call_count, 1)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertIsNone(candidate.claimed_at)

    def test_answer_is_dropped_when_a_human_decided_the_candidate_in_flight(self):
        candidate = tag_candidate(*make_tags("Tango", "Mango"))

        def decide_meanwhile(messages):
            Candidate.objects.filter(pk=candidate.pk).update(
                status=Candidate.STATUS_REJECTED, claimed_at=None,
            )
            return no_sets_for_each_group(messages)

        run_judge(decide_meanwhile)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REJECTED)
        self.assertIsNone(candidate.verdict)
        self.assertEqual(candidate.attempts, 0)

    def test_human_reject_and_apply_are_refused_while_claimed(self):
        candidate = tag_candidate(*make_tags("Tango", "Mango"), status=Candidate.STATUS_REVIEW,
                                  claimed_at=timezone.now())
        with self.assertRaises(CandidateError):
            reject_candidate(candidate)
        with self.assertRaises(CandidateError):
            apply_candidate(candidate)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(Tag.objects.count(), 2)


class UndoTargetGoneTests(TestCase):
    def setUp(self):
        self.isekai, self.another = make_tags("Isekai", "Another World")
        self.candidate = tag_candidate(self.isekai, self.another)
        llm_tasks.settle(
            llm_tasks.REGISTRY["tag_merge"], self.candidate,
            tag_judgement(([self.isekai, self.another], "Isekai")),
        )
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_APPLIED)

    def test_undo_restores_the_folded_tag_while_the_target_exists(self):
        undo_candidate(self.candidate)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_UNDONE)
        self.assertTrue(Tag.objects.filter(name="Another World").exists())

    def test_undo_with_the_target_gone_raises_and_keeps_the_candidate_applied(self):
        Tag.objects.filter(pk=self.isekai.pk).delete()
        with self.assertRaises(MergeError):
            undo_candidate(self.candidate)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_APPLIED)
        self.assertIsNone(self.candidate.undone_at)
        self.assertTrue(all(not entry.get("undone_at") for entry in self.candidate.undo))


class TagMergeBudgetTests(TestCase):
    """The provider's budget counts every reply it sent, usable or not."""

    def setUp(self):
        self.candidate = tag_candidate(*make_tags("Tango", "Mango"))

    def test_unusable_paid_call_still_counts_against_the_daily_budget(self):
        def paid_but_unusable(messages):
            # _post_chat logs the LLMCall of every reply before the answer is checked.
            LLMCall.objects.create(kind="tag_merge", provider="groq", tokens=10)
            return "no json"

        run_judge(paid_but_unusable, daily_requests=1)
        self.assertEqual(LLMCall.objects.filter(kind="tag_merge").count(), 1)

        Candidate.objects.update(not_before=None)
        mocked = run_judge(no_sets_for_each_group, daily_requests=1)
        self.assertEqual(mocked.call_count, 0)

    def test_rate_limited_call_leaves_the_candidate_untouched(self):
        run_judge(llm_service.RateLimited(retry_after=None))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(self.candidate.attempts, 0)
        self.assertIsNotNone(self.candidate.not_before)

    def test_rate_limited_verification_leaves_the_candidate_untouched(self):
        chat = run_judge(
            answer({"members": ["t1", "t2"], "canonical": "Tango", "confidence": 0.97}),
            verify=llm_service.RateLimited(retry_after=None),
        )
        self.candidate.refresh_from_db()
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(self.candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(self.candidate.attempts, 0)
        self.assertIsNotNone(self.candidate.not_before)

    def test_http_error_is_a_failed_attempt_with_its_reason(self):
        run_judge(llm_service.LLMError("HTTP 500"))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(self.candidate.attempts, 1)
        self.assertIn("HTTP 500", self.candidate.reason)

    def test_failed_batch_fails_every_candidate_in_it(self):
        other = tag_candidate(*make_tags("Samba", "Rumba"))
        with mock.patch.object(llm_tasks.TagMergeTask, "batch_size", 4):
            run_judge("no json")
        for candidate in (self.candidate, other):
            candidate.refresh_from_db()
            self.assertEqual(candidate.attempts, 1)
            self.assertIsNotNone(candidate.not_before)

    def test_failed_candidate_is_not_retried_within_the_same_run(self):
        other = tag_candidate(*make_tags("Samba", "Rumba"))
        with mock.patch.object(llm_tasks.TagMergeTask, "batch_size", 2):
            mocked = run_judge("no json", limit=3)
        self.assertEqual(mocked.call_count, 2)
        for candidate in (self.candidate, other):
            candidate.refresh_from_db()
            self.assertEqual(candidate.attempts, 1)
            self.assertEqual(candidate.status, Candidate.STATUS_PENDING)

    def test_no_call_when_the_token_budget_is_below_one_call(self):
        mocked = run_judge(no_sets_for_each_group, daily_tokens=100)
        self.assertEqual(mocked.call_count, 0)

    def test_budget_is_checked_before_every_call(self):
        other = tag_candidate(*make_tags("Samba", "Rumba"))
        third = tag_candidate(*make_tags("Polka", "Salsa"))

        def spend(messages):
            # One paid call of 7000 tokens: the next call (CALL_TOKENS) no longer fits.
            LLMCall.objects.create(kind="tag_merge", provider="groq", tokens=7000)
            return no_sets_for_each_group(messages)

        with mock.patch.object(llm_tasks.TagMergeTask, "batch_size", 2):
            mocked = run_judge(spend, daily_tokens=8000, tokens_per_minute=100000)
        self.assertEqual(mocked.call_count, 1)
        for candidate in (other, third):
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
            self.assertEqual(candidate.attempts, 0)
