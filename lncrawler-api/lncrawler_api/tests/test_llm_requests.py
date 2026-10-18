"""Tests for the LLMRequest queue and the tag_r18 task (services/llm_tasks.py)."""

import json
from unittest import mock

from django.test import override_settings

from ..models import ExternalSource, LLMRequest, LLMUsage, Novel, Tag
from ..services import llm_service, llm_tasks
from ..services.llm_service import RateLimited
from .helpers import MergeTestCase


@override_settings(LLM_API_KEY="key")
class TagR18TaskTests(MergeTestCase):
    def make_request(self, tag_ids, **extra):
        return LLMRequest.objects.create(
            task="tag_r18",
            target_type="tag",
            target_ids=list(tag_ids),
            prompt_version="1",
            **extra,
        )

    def test_enqueue_batches_unflagged_tags_and_skips_covered(self):
        for name in ("Alpha", "Beta", "Gamma"):
            Tag.objects.create(name=name)
        Tag.objects.create(name="Adult", is_adult=True)
        task = llm_tasks.REGISTRY["tag_r18"]

        with override_settings(TAG_R18_LLM_TAGS_PER_CALL=2):
            self.assertEqual(task.enqueue(5), 2)
            self.assertEqual(task.enqueue(5), 0)

        batch_sizes = sorted(len(req.target_ids) for req in LLMRequest.objects.filter(task="tag_r18"))
        self.assertEqual(batch_sizes, [1, 2])

    def test_success_flags_only_confident_r18_tags(self):
        strong = Tag.objects.create(name="Smut")
        weak = Tag.objects.create(name="Romance")
        novel = Novel.objects.create(title="Novel", slug="novel", novel_path="n")
        site_a = ExternalSource.objects.create(source_name="site-a")
        site_b = ExternalSource.objects.create(source_name="site-b")
        src_a = self.make_source(novel, site_a, "A", "https://a.example/n", "novel-a", "src-a")
        src_b = self.make_source(novel, site_b, "B", "https://b.example/n", "novel-b", "src-b")
        src_a.tags.add(strong)
        src_b.tags.add(weak)
        req = self.make_request([strong.pk, weak.pk])

        reply = json.dumps({
            "tags": [
                {"id": strong.pk, "r18": True, "confidence": 0.95},
                {"id": weak.pk, "r18": True, "confidence": 0.5},
            ]
        })
        with mock.patch.object(llm_service, "_post_chat", return_value=(reply, 42)):
            counts = llm_tasks.run_task("tag_r18", 5)

        self.assertEqual(counts["done"], 1)
        strong.refresh_from_db()
        weak.refresh_from_db()
        src_a.refresh_from_db()
        src_b.refresh_from_db()
        self.assertTrue(strong.is_adult)
        self.assertFalse(weak.is_adult)
        self.assertTrue(src_a.is_adult)
        self.assertFalse(src_b.is_adult)

        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_DONE)
        self.assertEqual(req.tokens, 42)
        self.assertEqual(len(req.response["tags"]), 2)

    def test_parse_error_retries_then_fails(self):
        tag = Tag.objects.create(name="Smut")
        req = self.make_request([tag.pk])

        with mock.patch.object(llm_service, "_post_chat", return_value=("not json", 5)):
            counts = llm_tasks.run_task("tag_r18", 1)

        req.refresh_from_db()
        self.assertEqual(counts["retry"], 1)
        self.assertEqual(req.status, LLMRequest.STATUS_PENDING)
        self.assertEqual(req.attempts, 1)
        self.assertIsNotNone(req.not_before)

        # Make it due again with one attempt left before max_attempts.
        LLMRequest.objects.filter(pk=req.pk).update(not_before=None, attempts=2)
        with mock.patch.object(llm_service, "_post_chat", return_value=("not json", 5)):
            counts = llm_tasks.run_task("tag_r18", 1)

        req.refresh_from_db()
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(req.status, LLMRequest.STATUS_FAILED)
        self.assertEqual(req.attempts, 3)

    def test_rate_limit_keeps_request_pending_and_stops_run(self):
        first = Tag.objects.create(name="A1")
        second = Tag.objects.create(name="B1")
        r1 = self.make_request([first.pk])
        r2 = self.make_request([second.pk])

        with mock.patch.object(
            llm_service, "_post_chat", side_effect=RateLimited(retry_after="30")
        ) as post:
            counts = llm_tasks.run_task("tag_r18", 5)

        self.assertEqual(post.call_count, 1)
        self.assertTrue(counts["rate_limited"])
        for req in (r1, r2):
            req.refresh_from_db()
            self.assertEqual(req.status, LLMRequest.STATUS_PENDING)
            self.assertEqual(req.attempts, 0)
        self.assertIsNotNone(r1.not_before)

    @override_settings(LLM_DAILY_TOKENS=10000, TAG_R18_LLM_MAX_TOKENS=4096)
    def test_shared_budget_too_low_for_estimate_prevents_calls(self):
        tag = Tag.objects.create(name="Smut")
        # Another workflow spent most of the shared budget: 10000 - 5000 left is
        # below one R18 request's estimate (4096 + prompt reserve).
        LLMUsage.objects.create(purpose=LLMUsage.PURPOSE_NOVEL, tokens=5000)
        pending = self.make_request([tag.pk])

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_task("tag_r18", 5)

        post.assert_not_called()
        pending.refresh_from_db()
        self.assertEqual(pending.status, LLMRequest.STATUS_PENDING)

    def test_parse_drops_unknown_ids_and_non_finite_confidence(self):
        tag = Tag.objects.create(name="Smut")
        req = self.make_request([tag.pk])
        result = llm_tasks.REGISTRY["tag_r18"].parse(
            req, '{"tags": [{"id": %d, "r18": true, "confidence": NaN}, {"id": 999999, "r18": true, "confidence": 1}]}' % tag.pk
        )
        self.assertEqual(result, {"tags": [{"id": tag.pk, "r18": True, "confidence": 0.0}]})

    def test_batch_with_no_tags_left_is_closed_without_a_call(self):
        tag = Tag.objects.create(name="Smut", is_adult=True)
        req = self.make_request([tag.pk])

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_task("tag_r18", 5)

        post.assert_not_called()
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_DONE)
