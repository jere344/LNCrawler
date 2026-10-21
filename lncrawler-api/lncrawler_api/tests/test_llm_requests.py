"""Tests for the LLMRequest queue and the tag_r18 task (services/llm_tasks.py)."""

import json
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from ..models import ExternalSource, LLMProviderCooldown, LLMRequest, LLMUsage, Novel, Tag
from ..services import llm_service, llm_tasks
from ..services.llm_service import ProviderUnavailable, RateLimited
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

    def test_parse_accepts_an_empty_list(self):
        # The model lists only explicit or suggestive tags, so a clean batch is an empty list.
        tag = Tag.objects.create(name="Romance")
        req = self.make_request([tag.pk])
        self.assertEqual(llm_tasks.REGISTRY["tag_r18"].parse(req, '{"tags": []}'), {"tags": []})

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


CHAIN_SETTINGS = {
    "cerebras": {
        "api_key": "cerebras-key", "model": "gpt-oss-120b", "base_url": "", "reasoning_effort": "low",
        "daily_requests": None, "daily_tokens": None, "requests_per_minute": None,
        "tokens_per_minute": None, "cooldown": 3600,
    },
    "groq": {
        "api_key": "groq-key", "model": "openai/gpt-oss-20b", "base_url": "", "reasoning_effort": "low",
        "daily_requests": None, "daily_tokens": None, "requests_per_minute": None,
        "tokens_per_minute": None, "cooldown": 60,
    },
}


def _answers(replies):
    """A ``_post_chat`` stand-in: per provider name, a ``(content, tokens)`` reply or an exception to raise."""
    def post(messages, max_tokens, purpose, provider=None, **kwargs):
        reply = replies[provider.name]
        if isinstance(reply, Exception):
            raise reply
        return reply
    return post


@override_settings(LLM_PROVIDERS=["cerebras", "groq"], LLM_PROVIDER_SETTINGS=CHAIN_SETTINGS)
class ProviderChainTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.tag = Tag.objects.create(name="Smut")
        self.reply = json.dumps({"tags": [{"id": self.tag.pk, "rating": "explicit", "confidence": 0.95}]})
        self.ok = (self.reply, 42)

    def make_request(self):
        return LLMRequest.objects.create(
            task="tag_r18", target_type="tag", target_ids=[self.tag.pk], prompt_version="1",
        )

    def test_first_provider_answers(self):
        req = self.make_request()
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": self.ok})) as post:
            counts = llm_tasks.run_task("tag_r18", 1)

        self.assertEqual(counts["done"], 1)
        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["cerebras"])
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_DONE)
        self.assertEqual(req.model, "gpt-oss-120b")

    def test_rate_limit_without_retry_after_falls_through_to_next_provider(self):
        req = self.make_request()
        replies = {"cerebras": RateLimited(), "groq": self.ok}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)) as post:
            counts = llm_tasks.run_task("tag_r18", 1)

        self.assertEqual(counts["done"], 1)
        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["cerebras", "groq"])
        cooling = LLMProviderCooldown.objects.get(name="cerebras")
        self.assertGreater(cooling.until, timezone.now() + timedelta(seconds=3500))
        self.assertLess(cooling.until, timezone.now() + timedelta(seconds=3700))
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_DONE)
        self.assertEqual(req.attempts, 1)
        self.assertEqual(req.model, "openai/gpt-oss-20b")

    def test_cooling_provider_is_skipped_until_its_cooldown_ends(self):
        LLMProviderCooldown.objects.create(
            name="cerebras", until=timezone.now() + timedelta(hours=1), reason="HTTP 429",
        )
        self.make_request()
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": self.ok, "groq": self.ok})) as post:
            llm_tasks.run_task("tag_r18", 1)
        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["groq"])

        # A new tag: the first one is already flagged, so its request would be closed without a call.
        LLMProviderCooldown.objects.filter(name="cerebras").update(until=timezone.now() - timedelta(seconds=1))
        other = Tag.objects.create(name="Other")
        LLMRequest.objects.create(
            task="tag_r18", target_type="tag", target_ids=[other.pk], prompt_version="1",
        )
        reply = json.dumps({"tags": [{"id": other.pk, "rating": "explicit", "confidence": 0.95}]})
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": (reply, 42)})) as post:
            llm_tasks.run_task("tag_r18", 1)
        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["cerebras"])

    def test_every_provider_rate_limited_gives_the_request_back(self):
        req = self.make_request()
        replies = {"cerebras": RateLimited(), "groq": RateLimited()}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            counts = llm_tasks.run_task("tag_r18", 1)

        self.assertTrue(counts["rate_limited"])
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_PENDING)
        self.assertEqual(req.attempts, 0)
        self.assertAlmostEqual((req.not_before - timezone.now()).total_seconds(), 60, delta=5)
        self.assertFalse(llm_service.can_afford())

    @override_settings(LLM_PROVIDER_SETTINGS={
        **CHAIN_SETTINGS, "groq": {**CHAIN_SETTINGS["groq"], "daily_requests": 2},
    })
    def test_groq_daily_cap_blocks_the_chain_while_cerebras_cools_down(self):
        LLMProviderCooldown.objects.create(
            name="cerebras", until=timezone.now() + timedelta(hours=1), reason="HTTP 429",
        )
        LLMUsage.objects.create(purpose="tag_r18", provider="groq", tokens=0)
        LLMUsage.objects.create(purpose="tag_r18", provider="groq", tokens=0)
        self.make_request()

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_task("tag_r18", 1)

        post.assert_not_called()
        self.assertFalse(llm_service.can_afford())

    def test_post_chat_sends_the_provider_request_and_records_it(self):
        cerebras = llm_service.providers()[0]
        session = mock.Mock()
        session.post.return_value = mock.Mock(status_code=503, headers={}, text="busy")
        with self.assertRaises(ProviderUnavailable):
            llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session)
        self.assertFalse(LLMUsage.objects.exists())

        response = mock.Mock(status_code=200, headers={}, text="")
        response.json.return_value = {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 7},
        }
        session.post.return_value = response
        llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session)

        self.assertEqual(LLMUsage.objects.get().provider, "cerebras")
        self.assertEqual(session.post.call_args.args[0], "https://api.cerebras.ai/v1/chat/completions")
        self.assertEqual(session.post.call_args.kwargs["headers"]["Authorization"], "Bearer cerebras-key")
        self.assertEqual(session.post.call_args.kwargs["json"]["model"], "gpt-oss-120b")

    def test_post_chat_merges_the_provider_extra_body(self):
        settings = {**CHAIN_SETTINGS, "cerebras": {**CHAIN_SETTINGS["cerebras"], "extra_body": {"thinking": {"type": "disabled"}}}}
        with override_settings(LLM_PROVIDER_SETTINGS=settings):
            cerebras = llm_service.providers()[0]
        response = mock.Mock(status_code=200, headers={}, text="")
        response.json.return_value = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        session = mock.Mock()
        session.post.return_value = response
        llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session)

        body = session.post.call_args.kwargs["json"]
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["model"], "gpt-oss-120b")

    def test_post_chat_sends_the_response_schema_as_structured_output(self):
        cerebras = llm_service.providers()[0]
        response = mock.Mock(status_code=200, headers={}, text="")
        response.json.return_value = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        session = mock.Mock()
        session.post.return_value = response
        schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session, response_schema=schema)

        self.assertEqual(
            session.post.call_args.kwargs["json"]["response_format"],
            {"type": "json_schema", "json_schema": {"name": "tag_r18", "strict": True, "schema": schema}},
        )

    def test_post_chat_sends_no_response_format_when_provider_disables_it(self):
        settings = {**CHAIN_SETTINGS, "cerebras": {**CHAIN_SETTINGS["cerebras"], "json_schema": False}}
        with override_settings(LLM_PROVIDER_SETTINGS=settings):
            cerebras = llm_service.providers()[0]
        response = mock.Mock(status_code=200, headers={}, text="")
        response.json.return_value = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        session = mock.Mock()
        session.post.return_value = response
        llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session,
                               response_schema={"type": "object"})

        self.assertNotIn("response_format", session.post.call_args.kwargs["json"])

    def test_run_queue_passes_the_task_schema_to_post_chat(self):
        self.make_request()
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": self.ok})) as post:
            llm_tasks.run_queue(["tag_r18"])

        self.assertEqual(post.call_args.kwargs["response_schema"], llm_tasks.TagR18Task.response_schema)

    def test_chat_outage_cools_the_provider_for_five_minutes_and_falls_through(self):
        replies = {"cerebras": ProviderUnavailable("HTTP 503: busy"), "groq": self.ok}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            content, tokens, provider = llm_service.chat([], 10, "tag_r18")

        self.assertEqual(provider.name, "groq")
        self.assertEqual(content, self.reply)
        cooling = LLMProviderCooldown.objects.get(name="cerebras")
        self.assertAlmostEqual((cooling.until - timezone.now()).total_seconds(), 300, delta=5)

    def test_other_http_error_tries_the_next_provider_without_cooldown(self):
        replies = {"cerebras": llm_service.LLMError("HTTP 400: unknown model"), "groq": self.ok}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            _content, _tokens, provider = llm_service.chat([], 10, "tag_r18")

        self.assertEqual(provider.name, "groq")
        self.assertFalse(LLMProviderCooldown.objects.exists())

    def test_other_http_error_everywhere_is_raised(self):
        replies = {"cerebras": llm_service.LLMError("HTTP 400: a"), "groq": llm_service.LLMError("HTTP 400: b")}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            with self.assertRaisesMessage(llm_service.LLMError, "HTTP 400: b"):
                llm_service.chat([], 10, "tag_r18")

    def test_parse_error_is_not_sent_to_the_next_provider(self):
        replies = {"cerebras": llm_service.LLMTruncated("cut"), "groq": self.ok}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)) as post:
            with self.assertRaises(llm_service.LLMTruncated):
                llm_service.chat([], 10, "tag_r18")
        self.assertEqual(post.call_count, 1)

    def test_post_chat_maps_bad_key_and_network_errors_to_unavailable(self):
        cerebras = llm_service.providers()[0]
        session = mock.Mock()
        session.post.return_value = mock.Mock(status_code=401, headers={}, text="bad key")
        with self.assertRaises(ProviderUnavailable):
            llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session)
        session.post.side_effect = llm_service.requests.ConnectionError("refused")
        with self.assertRaises(ProviderUnavailable):
            llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session)

    def test_provider_without_model_is_skipped(self):
        settings = {**CHAIN_SETTINGS, "cerebras": {**CHAIN_SETTINGS["cerebras"], "model": ""}}
        with override_settings(LLM_PROVIDER_SETTINGS=settings), \
                mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"groq": self.ok})):
            _content, _tokens, provider = llm_service.chat([], 10, "tag_r18")
        self.assertEqual(provider.name, "groq")

    def test_every_provider_down_records_why_on_the_request(self):
        req = LLMRequest.objects.create(
            task="tag_r18", target_type="tag", target_ids=[self.tag.pk], prompt_version="1",
        )
        replies = {"cerebras": ProviderUnavailable("HTTP 401: bad key"), "groq": RateLimited(retry_after="30")}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            llm_tasks.run_queue(["tag_r18"])

        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_PENDING)
        self.assertEqual(req.attempts, 0)
        self.assertIn("cerebras: HTTP 401: bad key", req.error)
        self.assertIn("groq: HTTP 429", req.error)


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


def _strict_violations(node, path="$"):
    """Where ``node`` has an object strict structured output would reject."""
    found = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                found.append(f"{path}: additionalProperties is not false")
            if sorted(node.get("required", [])) != sorted(node.get("properties", {})):
                found.append(f"{path}: required does not list every property")
        for key, value in node.items():
            found.extend(_strict_violations(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_strict_violations(value, f"{path}[{index}]"))
    return found


class ResponseSchemaTests(SimpleTestCase):
    def test_every_registered_task_schema_is_strict_compatible(self):
        for name, task in llm_tasks.REGISTRY.items():
            with self.subTest(task=name):
                self.assertIsNotNone(task.response_schema)
                self.assertEqual(_strict_violations(task.response_schema), [])
