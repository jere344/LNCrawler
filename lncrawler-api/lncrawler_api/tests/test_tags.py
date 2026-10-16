"""Tests for tag autocomplete, normalization, merging and automatic clustering."""

import json
import os
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import (
    ExternalSource,
    Novel,
    NovelFromSource,
    Tag,
    TagAlias,
    TagCluster,
    LLMUsage,
    TagLLMCall,
    TagMerge,
    TagNoMerge,
)
from django.conf import settings
from django.contrib import admin
from django.contrib import messages as django_messages
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
from ..admin.source_admin import TagAdmin, TagAdminForm
from ..models import sources_models
from ..models.sources_models import (
    TAG_IMPORT_ATTEMPTS,
    TagImportError,
    TagImportRetry,
    _set_source_tags,
)
from ..services import MergeError, llm_service, merge_tags, rename_tag, undo_tag_cluster, undo_tag_merge
from ..services import embedding_service, merge_service
from ..services import tag_merge_service as tms
from ..utils.tag_utils import normalize_tag


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

    def test_merge_records_a_tagmerge(self):
        merge_tags(self.source, self.target)

        merge = TagMerge.objects.get()
        self.assertEqual(merge.kind, TagMerge.KIND_MERGE)
        self.assertEqual(merge.source_name, "Another World")
        self.assertEqual(merge.target, self.target)
        self.assertEqual(sorted(merge.all_source_ids), sorted([self.s2.pk, self.s3.pk]))
        self.assertEqual(merge.added_source_ids, [self.s3.pk])
        self.assertEqual(len(merge.moved_alias_ids), 1)
        self.assertEqual(set(self.target.novels.all()), {self.s1, self.s2, self.s3})

    def test_undo_restores_links_and_aliases(self):
        merge_tags(self.source, self.target)
        merge = TagMerge.objects.get()

        undo_tag_merge(merge)

        restored = Tag.objects.get(name="Another World")
        self.assertEqual(set(restored.novels.all()), {self.s2, self.s3})
        self.assertEqual(set(self.target.novels.all()), {self.s1, self.s2})
        self.assertEqual(TagAlias.objects.get(name="Otherworld").tag, restored)
        self.assertFalse(TagAlias.objects.filter(name="Another World").exists())
        merge.refresh_from_db()
        self.assertIsNotNone(merge.undone_at)
        with self.assertRaises(MergeError):
            undo_tag_merge(merge)

    def test_rename_keeps_old_name_as_alias_and_undoes(self):
        renamed = rename_tag(self.source, "Isekai World")

        self.assertEqual(renamed.name, "Isekai World")
        self.assertEqual(TagAlias.objects.get(name="Another World").tag, self.source)

        undo_tag_merge(TagMerge.objects.get(kind=TagMerge.KIND_RENAME))
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "Another World")
        self.assertFalse(TagAlias.objects.filter(name="Another World").exists())

    def test_rename_onto_existing_key_is_refused(self):
        with self.assertRaises(MergeError):
            rename_tag(self.source, "ISEKAI")


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
        clusters = tms.build_clusters(edges, max_size=12, blocked=[(2, 1)])
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


class JudgeTagClustersTests(TestCase):
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

    def _cluster(self, *tags):
        ids = [tag.pk for tag in tags]
        return TagCluster.objects.create(
            signature=tms.cluster_signature(ids),
            tag_ids=ids,
            tag_names=[tag.name for tag in tags],
        )

    def _judge(self, response=None, side_effect=None):
        patcher = mock.patch.object(
            llm_service, "chat_json", return_value=response, side_effect=side_effect
        )
        with override_settings(MERGE_LLM_API_KEY="test-key"), patcher as chat:
            call_command("judge_tag_clusters")
        return chat

    @staticmethod
    def _answer(*sets):
        return {"groups": [{"group": 1, "sets": list(sets)}]}

    def test_valid_answer_merges_into_existing_canonical_tag(self):
        cluster = self._cluster(self.isekai, self.another)
        chat = self._judge(self._answer(
            {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.95}
        ))

        cluster.refresh_from_db()
        self.assertEqual(cluster.status, TagCluster.STATUS_APPLIED)
        self.assertFalse(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertEqual(TagMerge.objects.get().cluster, cluster)
        self.assertEqual(TagAlias.objects.get(name="Another World").tag, self.isekai)
        self.assertEqual(chat.call_count, 1)
        self.assertIn("(2 novels)", chat.call_args[0][0][-1]["content"])

    def test_canonical_name_renames_most_used_member(self):
        otherworld = Tag.objects.create(name="Otherworld")
        tale = Tag.objects.create(name="Other World Tale")
        self._source("http://s/3").tags.add(otherworld)
        self._source("http://s/4").tags.add(otherworld)
        self._source("http://s/5").tags.add(tale)
        cluster = self._cluster(tale, otherworld)

        self._judge(self._answer(
            {"members": ["t1", "t2"], "canonical": "Other Realm", "confidence": 0.95}
        ))

        cluster.refresh_from_db()
        self.assertEqual(cluster.status, TagCluster.STATUS_APPLIED)
        survivor = Tag.objects.get(name="Other Realm")
        self.assertEqual(survivor.pk, otherworld.pk)
        self.assertFalse(Tag.objects.filter(pk=tale.pk).exists())
        self.assertEqual(TagAlias.objects.get(name="Otherworld").tag, survivor)

    def test_low_confidence_goes_to_review_without_changes(self):
        cluster = self._cluster(self.isekai, self.another)
        self._judge(self._answer(
            {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.5}
        ))

        cluster.refresh_from_db()
        self.assertEqual(cluster.status, TagCluster.STATUS_REVIEW)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertFalse(TagMerge.objects.exists())

    def test_widely_used_tags_go_to_review(self):
        cluster = self._cluster(self.isekai, self.another)
        self._source("http://s/3").tags.add(self.another)
        with override_settings(TAG_BIG_TAG_USAGE=1):
            self._judge(self._answer(
                {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.99}
            ))

        cluster.refresh_from_db()
        self.assertEqual(cluster.status, TagCluster.STATUS_REVIEW)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())

    def test_blocked_pair_goes_to_review(self):
        cluster = self._cluster(self.isekai, self.another)
        TagNoMerge.objects.create(tag_a=self.isekai, tag_b=self.another)
        self._judge(self._answer(
            {"members": ["t1", "t2"], "canonical": "Isekai", "confidence": 0.99}
        ))

        cluster.refresh_from_db()
        self.assertEqual(cluster.status, TagCluster.STATUS_REVIEW)

    def test_garbage_labels_are_dropped(self):
        cluster = self._cluster(self.isekai, self.another)
        self._judge(self._answer(
            {"members": ["t1", "t9", "t2", 5], "canonical": "Isekai", "confidence": 0.95},
            {"members": ["t1", "t7"], "canonical": "Other", "confidence": 0.99},
        ))

        cluster.refresh_from_db()
        self.assertEqual(cluster.status, TagCluster.STATUS_APPLIED)
        self.assertEqual(TagMerge.objects.count(), 1)
        self.assertEqual(cluster.llm_response["sets"][0]["members"], [self.isekai.pk, self.another.pk])

    def test_unparseable_answer_requeues_cluster(self):
        cluster = self._cluster(self.isekai, self.another)
        # One call per tick: a persistent failure would otherwise reach MAX_REQUEUES in one run.
        with override_settings(TAG_LLM_CALLS_PER_TICK=1):
            self._judge(side_effect=llm_service.LLMParseError("no json"))

        cluster.refresh_from_db()
        self.assertEqual(cluster.status, TagCluster.STATUS_PENDING)
        self.assertEqual(cluster.requeue_count, 1)
        self.assertIn("no json", cluster.error)
        self.assertIsNone(cluster.llm_batch)

    def test_force_applies_review_cluster(self):
        cluster = self._cluster(self.isekai, self.another)
        cluster.llm_response = {"sets": [{
            "members": [self.isekai.pk, self.another.pk],
            "canonical": "Isekai",
            "confidence": 0.2,
        }]}
        cluster.status = TagCluster.STATUS_REVIEW
        cluster.save()

        self.assertEqual(tms.apply_cluster(cluster, force=True), TagCluster.STATUS_APPLIED)
        self.assertFalse(Tag.objects.filter(pk=self.another.pk).exists())


class FindTagMergeCandidatesTests(TestCase):
    def test_cooccurring_tags_become_one_pending_cluster_once(self):
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

        cluster = TagCluster.objects.get()
        self.assertEqual(cluster.status, TagCluster.STATUS_PENDING)
        self.assertEqual(sorted(cluster.tag_ids), sorted([isekai.pk, another.pk]))


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
        self.assertEqual(settings.TAG_EMBED_PROVIDER, "jina")
        self.assertEqual(settings.TAG_EMBED_MODEL, "jina-embeddings-v5-omni-small")
        session = self._Session()
        with override_settings(TAG_EMBED_API_KEY="k"):
            vectors = embedding_service.embed(["isekai"], session=session)
        self.assertEqual(vectors.shape, (1, 2))
        url, kwargs = session.calls[0]
        self.assertEqual(url, embedding_service.PROVIDER_URLS["jina"])
        self.assertEqual(kwargs["json"]["task"], "text-matching")

    def test_other_providers_send_no_task_field(self):
        session = self._Session()
        with override_settings(TAG_EMBED_API_KEY="k", TAG_EMBED_PROVIDER="voyage"):
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
    """A set whose canonical name resolves outside the group is held or applied explicitly."""

    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="sg", novel_path="sg")
        self.external = ExternalSource.objects.create(source_name="sg")
        self.isekai = Tag.objects.create(name="Isekai")
        self.another = Tag.objects.create(name="Another World")
        self.outside = Tag.objects.create(name="Shared Name")
        self._source("http://sg/1").tags.add(self.isekai)
        self._source("http://sg/2").tags.add(self.another)
        self.cluster = TagCluster.objects.create(
            signature="sg-1",
            tag_ids=[self.isekai.pk, self.another.pk],
            tag_names=["Isekai", "Another World"],
            llm_response={"sets": [{
                "members": [self.isekai.pk, self.another.pk],
                "canonical": "Shared Name",
                "confidence": 0.99,
            }]},
        )

    def _source(self, url):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )

    def test_merge_into_outside_tag_goes_to_review(self):
        self.assertEqual(tms.apply_cluster(self.cluster), TagCluster.STATUS_REVIEW)
        self.assertIn("outside the group", self.cluster.error)
        self.assertTrue(Tag.objects.filter(pk=self.isekai.pk).exists())

    def test_force_merges_into_outside_tag(self):
        self.assertEqual(tms.apply_cluster(self.cluster, force=True), TagCluster.STATUS_APPLIED)
        self.assertFalse(Tag.objects.filter(pk=self.isekai.pk).exists())
        self.assertFalse(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertEqual(TagMerge.objects.filter(target=self.outside).count(), 2)


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
        self.cluster = TagCluster.objects.create(signature="ch-1", tag_ids=[], tag_names=[])
        merge_tags(self.alpha, self.beta, self.cluster)
        merge_tags(self.beta, self.gamma, self.cluster)

    def _source(self, url):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="N", source_url=url
        )

    def test_older_merge_names_the_later_one(self):
        first = TagMerge.objects.get(source_name="Alpha")
        with self.assertRaisesRegex(MergeError, "Undo the later merge of 'Beta' into 'Gamma'"):
            undo_tag_merge(first)

    def test_cluster_undo_blocks_pairs_across_the_chain(self):
        undo_tag_cluster(self.cluster)

        alpha = Tag.objects.get(name="Alpha")
        beta = Tag.objects.get(name="Beta")
        blocked = {
            tuple(sorted(pair))
            for pair in TagNoMerge.objects.values_list("tag_a_id", "tag_b_id")
        }
        self.assertIn(tuple(sorted((alpha.pk, beta.pk))), blocked)
        self.assertIn(tuple(sorted((beta.pk, self.gamma.pk))), blocked)

    def test_cluster_undo_handles_the_chain_newest_first(self):
        undo_tag_cluster(self.cluster)

        alpha = Tag.objects.get(name="Alpha")
        beta = Tag.objects.get(name="Beta")
        self.assertEqual(set(alpha.novels.all()), {self.s1})
        self.assertEqual(set(beta.novels.all()), {self.s2})
        self.assertEqual(set(self.gamma.novels.all()), set())
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, TagCluster.STATUS_UNDONE)
        self.assertTrue(TagMerge.objects.filter(undone_at__isnull=False).count() == 2)


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

    def test_saving_a_new_name_records_a_rename(self):
        form = TagAdminForm(data={"name": "Isekai Life"}, instance=self.tag)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        TagAdmin(Tag, admin.site).save_model(None, obj, form, change=True)

        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, "Isekai Life")
        self.assertEqual(TagAlias.objects.get(name="Isekai").tag, self.tag)
        self.assertTrue(TagMerge.objects.filter(kind=TagMerge.KIND_RENAME).exists())


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
        real_lock = sources_models._lock_tag_pks
        seen = []

        def racing_lock(pks):
            seen.append(sorted(pks))
            result = real_lock(pks)
            if len(seen) == 1:
                result = result - {self.action.pk}
            return result

        with mock.patch.object(sources_models, "_lock_tag_pks", side_effect=racing_lock):
            _set_source_tags(self.source, ["Isekai", "Action"])

        self.assertEqual(len(seen), 2)
        self.assertIn(self.isekai, set(self.source.tags.all()))

    def test_gives_up_after_the_attempt_limit(self):
        with mock.patch.object(sources_models, "_lock_tag_pks", return_value=set()) as lock:
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

    def test_pairs_follow_the_target_and_duplicates_are_dropped(self):
        TagNoMerge.objects.create(tag_a=self.source, tag_b=self.other)
        TagNoMerge.objects.create(tag_a=self.source, tag_b=self.target)
        TagNoMerge.objects.create(tag_a=self.target, tag_b=self.other)

        merge_tags(self.source, self.target)

        pairs = {tuple(sorted(p)) for p in TagNoMerge.objects.values_list("tag_a_id", "tag_b_id")}
        self.assertEqual(pairs, {tuple(sorted((self.target.pk, self.other.pk)))})


class EmbeddingResetTests(TestCase):
    def test_rename_clears_stored_vector(self):
        tag = Tag.objects.create(name="Isekai", embedding=b"\x00\x00\x80\x3f", embedding_model="m")
        rename_tag(tag, "Isekai Life")
        tag.refresh_from_db()
        self.assertIsNone(tag.embedding)
        self.assertEqual(tag.embedding_model, "")

    def test_undo_rename_clears_stored_vector(self):
        tag = Tag.objects.create(name="Isekai")
        rename_tag(tag, "Isekai Life")
        Tag.objects.filter(pk=tag.pk).update(embedding=b"\x00\x00\x80\x3f", embedding_model="m")
        undo_tag_merge(TagMerge.objects.get(kind=TagMerge.KIND_RENAME))
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
        ids = [self.tags[n].pk for n in ["Isekai", "Another World", "Foo Bar", "Foo Baz"]]
        self.cluster = TagCluster.objects.create(
            signature="at-1",
            tag_ids=ids,
            tag_names=list(self.tags),
            llm_response={"sets": [
                {"members": ids[:2], "canonical": "Isekai", "confidence": 0.95},
                {"members": ids[2:], "canonical": "Foo Bar", "confidence": 0.95},
            ]},
        )

    def test_failure_in_second_set_rolls_back_the_first(self):
        real_merge = tms.merge_tags
        calls = []

        def flaky_merge(source, target, cluster=None):
            calls.append(source.name)
            if len(calls) == 2:
                raise MergeError("boom")
            return real_merge(source, target, cluster)

        with mock.patch.object(tms, "merge_tags", side_effect=flaky_merge):
            status = tms.apply_cluster(self.cluster, force=True)

        self.assertEqual(status, TagCluster.STATUS_ERROR)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.error, "boom")
        self.assertTrue(Tag.objects.filter(name="Another World").exists())
        self.assertFalse(TagMerge.objects.exists())


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
        with mock.patch.object(sources_models, "_lock_tag_pks", return_value=set()):
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
        undo_tag_merge(TagMerge.objects.get())

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
        self.assertFalse(TagMerge.objects.exists())


class ClusterReplanTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="rp", novel_path="rp")
        self.external = ExternalSource.objects.create(source_name="rp")
        self.isekai = Tag.objects.create(name="Isekai")
        self.another = Tag.objects.create(name="Another World")
        for i, tag in enumerate([self.isekai, self.another]):
            NovelFromSource.objects.create(
                novel=self.novel, external_source=self.external, title="N",
                source_url=f"http://rp/{i}",
            ).tags.add(tag)
        self.cluster = TagCluster.objects.create(
            signature="rp-1",
            tag_ids=[self.isekai.pk, self.another.pk],
            tag_names=["Isekai", "Another World"],
            llm_response={"sets": [{
                "members": [self.isekai.pk, self.another.pk],
                "canonical": "Isekai",
                "confidence": 0.95,
            }]},
        )

    def test_plan_that_changed_under_the_lock_is_requeued(self):
        real_plan = tms.plan_sets
        calls = []

        def shifting_plan(sets):
            calls.append(1)
            # The second planning (under the lock) sees nothing left to merge.
            return real_plan(sets if len(calls) == 1 else [])

        with mock.patch.object(tms, "plan_sets", side_effect=shifting_plan):
            status = tms.apply_cluster(self.cluster)

        self.assertEqual(len(calls), 2)
        self.assertEqual(status, TagCluster.STATUS_PENDING)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.error, tms.REQUEUE_MESSAGE)
        self.assertIsNone(self.cluster.llm_response)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertFalse(TagMerge.objects.exists())

    def test_integrity_error_while_applying_sets_error(self):
        with mock.patch.object(tms, "_apply_set", side_effect=IntegrityError("dup key")):
            status = tms.apply_cluster(self.cluster)
        self.assertEqual(status, TagCluster.STATUS_ERROR)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, TagCluster.STATUS_ERROR)
        self.assertIn("dup key", self.cluster.error)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())


class _JudgeFixture(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="jf", novel_path="jf")
        self.external = ExternalSource.objects.create(source_name="jf")
        self.tags = [Tag.objects.create(name=n) for n in ["Isekai", "Another World", "Foo", "Bar"]]
        for i, tag in enumerate(self.tags):
            NovelFromSource.objects.create(
                novel=self.novel, external_source=self.external, title="N",
                source_url=f"http://jf/{i}",
            ).tags.add(tag)
        self.cluster_a = self._cluster(self.tags[0:2], "jf-a", created_offset=0)
        self.cluster_b = self._cluster(self.tags[2:4], "jf-b", created_offset=1)

    def _cluster(self, tags, signature, created_offset=0):
        cluster = TagCluster.objects.create(
            signature=signature,
            tag_ids=[t.pk for t in tags],
            tag_names=[t.name for t in tags],
        )
        TagCluster.objects.filter(pk=cluster.pk).update(
            created_at=timezone.now() - timedelta(days=10 - created_offset)
        )
        return cluster

    def _run_judge(self, chat, **overrides):
        settings_overrides = {"MERGE_LLM_API_KEY": "k", "TAG_LLM_TAGS_PER_CALL": 2,
                              "TAG_LLM_CALLS_PER_TICK": 1, **overrides}
        with override_settings(**settings_overrides), \
                mock.patch.object(llm_service, "chat_json", side_effect=chat) as mocked:
            call_command("judge_tag_clusters")
        return mocked


class TagJudgeBudgetTests(_JudgeFixture):
    def test_requeued_cluster_does_not_refund_the_call(self):
        self._run_judge(llm_service.LLMParseError("bad"), TAG_LLM_DAILY_LIMIT=1)
        self.assertEqual(TagLLMCall.objects.count(), 1)

        # Admin-style requeue: clear the answer and put the cluster back to pending.
        TagCluster.objects.filter(pk=self.cluster_a.pk).update(
            status=TagCluster.STATUS_PENDING, llm_response=None, llm_batch=None, judged_at=None
        )
        mocked = self._run_judge(lambda *a, **k: {"groups": []}, TAG_LLM_DAILY_LIMIT=1)
        self.assertEqual(mocked.call_count, 0)
        self.assertEqual(TagLLMCall.objects.count(), 1)

    def test_rate_limited_call_is_not_charged(self):
        self._run_judge(llm_service.RateLimited(retry_after=None), TAG_LLM_DAILY_LIMIT=5)
        self.assertEqual(TagLLMCall.objects.count(), 0)

    def test_parse_error_call_is_charged(self):
        self._run_judge(llm_service.LLMParseError("bad"))
        self.assertEqual(TagLLMCall.objects.count(), 1)
        self.cluster_a.refresh_from_db()
        self.assertEqual(self.cluster_a.status, TagCluster.STATUS_PENDING)
        self.assertEqual(self.cluster_a.requeue_count, 1)


class TagJudgeOrderTests(_JudgeFixture):
    def test_requeued_clusters_are_judged_after_fresh_ones(self):
        # cluster_b is older but has been requeued once, so it must wait behind cluster_a.
        TagCluster.objects.filter(pk=self.cluster_b.pk).update(requeue_count=1)
        mocked = self._run_judge(llm_service.LLMParseError("bad"))
        self.assertEqual(mocked.call_count, 1)
        self.cluster_a.refresh_from_db()
        self.cluster_b.refresh_from_db()
        self.assertEqual(self.cluster_a.status, TagCluster.STATUS_PENDING)
        self.assertEqual(self.cluster_a.requeue_count, 1)
        self.assertEqual(self.cluster_b.status, TagCluster.STATUS_PENDING)
        self.assertEqual(self.cluster_b.requeue_count, 1)


class TagJudgeFailureTests(_JudgeFixture):
    def test_parse_failure_requeues_every_cluster_in_the_batch(self):
        # Both clusters fit one call (4 tags), so one bad reply hits both.
        mocked = self._run_judge(llm_service.LLMTruncated("cut off"), TAG_LLM_TAGS_PER_CALL=4)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(TagLLMCall.objects.count(), 1)
        for cluster in (self.cluster_a, self.cluster_b):
            cluster.refresh_from_db()
            self.assertEqual(cluster.status, TagCluster.STATUS_PENDING)
            self.assertEqual(cluster.requeue_count, 1)
            self.assertIn("cut off", cluster.error)
            self.assertIsNone(cluster.llm_batch)

    def test_requeued_cluster_is_judged_alone(self):
        TagCluster.objects.filter(pk=self.cluster_b.pk).update(requeue_count=1)
        # Both clusters would fit one call; the requeued one must get its own.
        mocked = self._run_judge(lambda *a, **k: {"groups": []},
                                 TAG_LLM_TAGS_PER_CALL=10, TAG_LLM_CALLS_PER_TICK=2)
        self.assertEqual(mocked.call_count, 2)
        first, second = (call.args[0][-1]["content"] for call in mocked.call_args_list)
        self.assertIn("Isekai", first)
        self.assertNotIn("Foo", first)
        self.assertIn("Foo", second)
        self.assertNotIn("Isekai", second)


    def test_failed_cluster_is_not_retried_within_the_same_run(self):
        # Three calls allowed, two clusters: each is tried once, then the run stops.
        mocked = self._run_judge(llm_service.LLMParseError("bad"),
                                 TAG_LLM_CALLS_PER_TICK=3, TAG_LLM_TAGS_PER_CALL=2)
        self.assertEqual(mocked.call_count, 2)
        self.cluster_a.refresh_from_db()
        self.cluster_b.refresh_from_db()
        self.assertEqual(self.cluster_a.requeue_count, 1)
        self.assertEqual(self.cluster_b.requeue_count, 1)
        self.assertEqual(self.cluster_a.status, TagCluster.STATUS_PENDING)
        self.assertEqual(self.cluster_b.status, TagCluster.STATUS_PENDING)


class TagJudgeTokenBudgetTests(_JudgeFixture):
    def test_stops_before_any_call_when_budget_below_reserve(self):
        mocked = self._run_judge(lambda *a, **k: {"groups": []}, MERGE_LLM_DAILY_TOKENS=100)
        self.assertEqual(mocked.call_count, 0)
        self.assertEqual(TagLLMCall.objects.count(), 0)

    def test_budget_checked_before_every_call(self):
        def spend(*args, **kwargs):
            LLMUsage.objects.create(purpose=LLMUsage.PURPOSE_TAG, tokens=7000)
            return {"groups": []}

        # Reserve is TAG_LLM_MAX_TOKENS (4096) + 3000: the first call fits, the second does not.
        mocked = self._run_judge(spend, MERGE_LLM_DAILY_TOKENS=8000,
                                 TAG_LLM_CALLS_PER_TICK=3, TAG_LLM_TAGS_PER_CALL=2)
        self.assertEqual(mocked.call_count, 1)


class ReplanUnderLockTests(TestCase):
    setUp = ClusterReplanTests.setUp

    def test_consistent_plan_with_new_review_reason_goes_to_review(self):
        with mock.patch.object(tms, "review_reasons",
                               side_effect=[[], ["'Isekai' joins several widely used tags"]]):
            status = tms.apply_cluster(self.cluster)

        self.assertEqual(status, TagCluster.STATUS_REVIEW)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, TagCluster.STATUS_REVIEW)
        self.assertEqual(self.cluster.requeue_count, 0)
        self.assertIn("widely used", self.cluster.error)
        self.assertTrue(Tag.objects.filter(pk=self.another.pk).exists())
        self.assertFalse(TagMerge.objects.exists())

    def test_requeue_cap_moves_cluster_to_error(self):
        TagCluster.objects.filter(pk=self.cluster.pk).update(requeue_count=tms.MAX_REQUEUES - 1)
        self.cluster.refresh_from_db()
        real_plan = tms.plan_sets
        calls = []

        def shifting_plan(sets):
            calls.append(1)
            return real_plan(sets if len(calls) == 1 else [])

        with mock.patch.object(tms, "plan_sets", side_effect=shifting_plan):
            status = tms.apply_cluster(self.cluster)

        self.assertEqual(status, TagCluster.STATUS_ERROR)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.error, tms.REQUEUE_LIMIT_MESSAGE)
        self.assertEqual(self.cluster.requeue_count, tms.MAX_REQUEUES)

    def test_each_requeue_increments_the_count(self):
        real_plan = tms.plan_sets
        calls = []

        def shifting_plan(sets):
            calls.append(1)
            return real_plan(sets if len(calls) == 1 else [])

        with mock.patch.object(tms, "plan_sets", side_effect=shifting_plan):
            status = tms.apply_cluster(self.cluster)

        self.assertEqual(status, TagCluster.STATUS_PENDING)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.requeue_count, 1)


class UndoClusterLockTests(ChainedUndoTests):
    def test_cluster_undo_takes_one_lock_call(self):
        real_lock = merge_service.lock_tags
        with mock.patch.object(merge_service, "lock_tags", wraps=real_lock) as spy:
            undo_tag_cluster(self.cluster)
        self.assertEqual(spy.call_count, 1)
