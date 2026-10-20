"""Tests for the LLMRequest queue and the tag_r18 task (services/llm_tasks.py)."""

import json
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

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

        with mock.patch.object(llm_tasks.TagR18Task, "batch_size", 2):
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
                {"id": strong.pk, "rating": "explicit", "confidence": 0.95},
                {"id": weak.pk, "rating": "explicit", "confidence": 0.5},
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

    @override_settings(LLM_DAILY_TOKENS=10000, LLM_TOKENS_PER_MINUTE=100000)
    def test_shared_budget_too_low_for_one_call_prevents_calls(self):
        tag = Tag.objects.create(name="Smut")
        # Another workflow spent most of the shared budget: 10000 - 9000 left is
        # below one call (llm_service.CALL_TOKENS).
        LLMUsage.objects.create(purpose="novel_merge", tokens=9000)
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
            req, '{"tags": [{"id": %d, "rating": "explicit", "confidence": NaN}, {"id": 999999, "rating": "explicit", "confidence": 1}]}' % tag.pk
        )
        self.assertEqual(
            result,
            {"tags": [{"id": tag.pk, "rating": "explicit", "r18": True, "confidence": 0.0}]},
        )

    def test_suggestive_tag_is_not_flagged_adult(self):
        tag = Tag.objects.create(name="Sexy")
        req = self.make_request([tag.pk])

        reply = json.dumps({"tags": [{"id": tag.pk, "rating": "suggestive", "confidence": 0.99}]})
        with mock.patch.object(llm_service, "_post_chat", return_value=(reply, 10)):
            counts = llm_tasks.run_task("tag_r18", 5)

        self.assertEqual(counts["done"], 1)
        tag.refresh_from_db()
        self.assertFalse(tag.is_adult)
        req.refresh_from_db()
        self.assertEqual(req.response["tags"][0]["rating"], "suggestive")
        self.assertFalse(req.response["tags"][0]["r18"])

    def test_parse_skips_unknown_rating(self):
        porn = Tag.objects.create(name="Porn")
        smut = Tag.objects.create(name="Smut")
        req = self.make_request([porn.pk, smut.pk])
        result = llm_tasks.REGISTRY["tag_r18"].parse(
            req,
            '{"tags": [{"id": %d, "rating": "porn", "confidence": 1}, '
            '{"id": %d, "rating": "explicit", "confidence": 0.9}]}' % (porn.pk, smut.pk),
        )
        self.assertEqual(
            result,
            {"tags": [{"id": smut.pk, "rating": "explicit", "r18": True, "confidence": 0.9}]},
        )

    def test_batch_with_no_tags_left_is_closed_without_a_call(self):
        tag = Tag.objects.create(name="Smut", is_adult=True)
        req = self.make_request([tag.pk])

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_task("tag_r18", 5)

        post.assert_not_called()
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_DONE)


@override_settings(LLM_API_KEY="key", LLM_DAILY_TOKENS=100000,
                   LLM_TOKENS_PER_MINUTE=8000, LLM_REQUESTS_PER_MINUTE=30)
class LLMQueueTests(MergeTestCase):
    def make_tag_request(self, name):
        tag = Tag.objects.create(name=name)
        return LLMRequest.objects.create(
            task="tag_r18", target_type="tag", target_ids=[tag.pk], prompt_version="1",
        )

    def make_merge_request(self):
        # The cluster does not exist, so the real build_messages would close it; tests patch it.
        return LLMRequest.objects.create(
            task="tag_merge", target_type="tag_cluster", target_ids=[0], prompt_version="1",
        )

    def test_per_minute_token_cap_stops_the_pass(self):
        req = self.make_tag_request("Smut")
        # 6501 + CALL_TOKENS (1500) is over LLM_TOKENS_PER_MINUTE (8000).
        LLMUsage.objects.create(purpose="tag_r18", tokens=8000 - llm_service.CALL_TOKENS + 1)

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_task("tag_r18", 5)

        post.assert_not_called()
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_PENDING)

    @override_settings(LLM_REQUESTS_PER_MINUTE=2)
    def test_per_minute_request_cap_stops_the_pass(self):
        req = self.make_tag_request("Smut")
        LLMUsage.objects.create(purpose="tag_r18", tokens=0)
        LLMUsage.objects.create(purpose="tag_r18", tokens=0)

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_task("tag_r18", 5)

        post.assert_not_called()
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_PENDING)

    def test_usage_older_than_a_minute_does_not_count(self):
        self.make_tag_request("Smut")
        old = LLMUsage.objects.create(purpose="tag_r18", tokens=8000)
        LLMUsage.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(seconds=61))

        with mock.patch.object(llm_service, "_post_chat", return_value=("not json", 5)) as post:
            llm_tasks.run_task("tag_r18", 5)

        post.assert_called_once()

    def test_round_robin_takes_one_call_per_task_in_turn(self):
        self.make_tag_request("A1")
        second = self.make_tag_request("B1")
        self.make_merge_request()

        with mock.patch.object(llm_tasks.TagMergeTask, "build_messages", return_value=[]), \
                mock.patch.object(llm_service, "_post_chat", return_value=("not json", 5)) as post:
            llm_tasks.run_queue(["tag_r18", "tag_merge"], limit=2)

        self.assertEqual([call.args[2] for call in post.call_args_list], ["tag_r18", "tag_merge"])
        second.refresh_from_db()
        self.assertEqual(second.status, LLMRequest.STATUS_PENDING)
        self.assertEqual(second.attempts, 0)

    def test_rate_limit_stops_every_task(self):
        self.make_tag_request("A1")
        merge = self.make_merge_request()

        with mock.patch.object(llm_tasks.TagMergeTask, "build_messages", return_value=[]), \
                mock.patch.object(llm_service, "_post_chat",
                                  side_effect=RateLimited(retry_after="30")) as post:
            counts = llm_tasks.run_queue(["tag_r18", "tag_merge"], limit=5)

        self.assertEqual(post.call_count, 1)
        self.assertTrue(counts["rate_limited"])
        merge.refresh_from_db()
        self.assertEqual(merge.status, LLMRequest.STATUS_PENDING)
        self.assertEqual(merge.attempts, 0)

    def test_top_up_keeps_at_most_queue_backlog_pending(self):
        for n in range(8):
            Tag.objects.create(name=f"T{n}")
        task = llm_tasks.REGISTRY["tag_r18"]

        with mock.patch.object(llm_tasks.TagR18Task, "batch_size", 1):
            self.assertEqual(llm_tasks._top_up(task, None), llm_tasks.QUEUE_BACKLOG)
            self.assertEqual(llm_tasks._top_up(task, None), 0)

        self.assertEqual(
            LLMRequest.objects.filter(task="tag_r18", status=LLMRequest.STATUS_PENDING).count(),
            llm_tasks.QUEUE_BACKLOG,
        )

    def test_usage_row_purpose_is_the_task_name(self):
        self.make_tag_request("Smut")
        response = mock.Mock(status_code=200, headers={}, text="")
        response.json.return_value = {
            "choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 7},
        }
        session = mock.Mock()
        session.post.return_value = response

        llm_tasks.run_task("tag_r18", 1, session=session)

        self.assertEqual(LLMUsage.objects.get().purpose, "tag_r18")


class ParseConfidenceTests(SimpleTestCase):
    def test_clamps_finite_numbers_to_unit_interval(self):
        self.assertEqual(llm_service.parse_confidence(0.4), 0.4)
        self.assertEqual(llm_service.parse_confidence(3), 1.0)
        self.assertEqual(llm_service.parse_confidence(-2), 0.0)

    def test_non_finite_values_fall_back_to_default_in_both_modes(self):
        for value in (float("nan"), float("inf"), float("-inf"), "nan", "inf"):
            with self.subTest(value=value):
                self.assertEqual(llm_service.parse_confidence(value, default=0.25), 0.25)
                self.assertEqual(
                    llm_service.parse_confidence(value, default=0.25, strict=True), 0.25
                )

    def test_strict_mode_rejects_bools_and_strings(self):
        self.assertEqual(llm_service.parse_confidence(True, default=0.5, strict=True), 0.5)
        self.assertEqual(llm_service.parse_confidence("0.9", default=0.5, strict=True), 0.5)
        self.assertEqual(llm_service.parse_confidence("0.9", default=0.5), 0.9)
