"""Tests for the tag_r18 task (services/llm_tasks.py), the per-minute caps and the provider
chain (services/llm_service.py), on the Candidate queue and the LLMCall ledger.

The runner's claims, retries and drop of gone targets are in test_llm_runner.
"""

import json
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from ..models import Candidate, ExternalSource, LLMCall, LLMProviderCooldown, Novel, Tag
from ..services import llm_service, llm_tasks
from ..services.llm_service import LLMParseError, ProviderUnavailable, RateLimited
from ..services.tag_r18_service import queue_r18_candidates
from .helpers import MergeTestCase
from .test_llm_runner import make_candidate, reply


@override_settings(LLM_API_KEY="key")
class TagR18TaskTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(llm_service, "chat")
        self.chat = patcher.start()
        self.addCleanup(patcher.stop)

    def make_request(self, tag, **extra):
        return make_candidate("tag_r18", [tag.pk], [tag.name], **extra)

    def test_queue_makes_one_candidate_per_non_adult_tag_without_one(self):
        for name in ("Alpha", "Beta", "Gamma"):
            Tag.objects.create(name=name)
        Tag.objects.create(name="Adult", is_adult=True)

        self.assertEqual(queue_r18_candidates(5), 3)
        self.assertEqual(queue_r18_candidates(5), 0)
        targets = sorted(c.target_ids[0] for c in Candidate.objects.filter(kind="tag_r18"))
        self.assertEqual(len(targets), 3)

    def test_queue_respects_its_limit(self):
        for name in ("Alpha", "Beta", "Gamma"):
            Tag.objects.create(name=name)
        self.assertEqual(queue_r18_candidates(2), 2)
        self.assertEqual(queue_r18_candidates(5), 1)

    def test_confident_explicit_tag_is_flagged_and_weak_one_is_not(self):
        strong = Tag.objects.create(name="Smut")
        weak = Tag.objects.create(name="Romance")
        novel = Novel.objects.create(title="Novel", slug="novel", novel_path="n")
        site_a = ExternalSource.objects.create(source_name="site-a")
        site_b = ExternalSource.objects.create(source_name="site-b")
        src_a = self.make_source(novel, site_a, "A", "https://a.example/n", "novel-a", "src-a")
        src_b = self.make_source(novel, site_b, "B", "https://b.example/n", "novel-b", "src-b")
        src_a.tags.add(strong)
        src_b.tags.add(weak)
        strong_candidate = self.make_request(strong)
        weak_candidate = self.make_request(weak)

        self.chat.return_value = reply({"tags": [
            {"id": strong.pk, "rating": "explicit", "confidence": 0.95},
            {"id": weak.pk, "rating": "explicit", "confidence": 0.5},
        ]})
        counts = llm_tasks.run_queue(["tag_r18"])

        self.assertEqual(counts["done"], 2)
        strong.refresh_from_db()
        weak.refresh_from_db()
        src_a.refresh_from_db()
        src_b.refresh_from_db()
        self.assertTrue(strong.is_adult)
        self.assertFalse(weak.is_adult)
        self.assertTrue(src_a.is_adult)
        self.assertFalse(src_b.is_adult)
        strong_candidate.refresh_from_db()
        weak_candidate.refresh_from_db()
        self.assertEqual(strong_candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(weak_candidate.status, Candidate.STATUS_REVIEW)

    def test_parse_error_retries_then_fails(self):
        tag = Tag.objects.create(name="Smut")
        candidate = self.make_request(tag)
        self.chat.side_effect = LLMParseError("no JSON object in reply")

        counts = llm_tasks.run_queue(["tag_r18"])
        self.assertEqual(counts["retry"], 1)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 1)
        self.assertIsNotNone(candidate.not_before)

        for _ in range(2):
            Candidate.objects.update(not_before=None)
            llm_tasks.run_queue(["tag_r18"])
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_ERROR)
        self.assertEqual(candidate.attempts, 3)

    def test_rate_limit_keeps_candidates_pending_and_stops_run(self):
        first = self.make_request(Tag.objects.create(name="A1"))
        second = self.make_request(Tag.objects.create(name="B1"))
        self.chat.side_effect = RateLimited(retry_after="30")

        counts = llm_tasks.run_queue(["tag_r18"], limit=5)

        self.assertEqual(self.chat.call_count, 1)
        self.assertTrue(counts["rate_limited"])
        for candidate in (first, second):
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
            self.assertEqual(candidate.attempts, 0)
        self.assertIsNotNone(first.not_before)

    def test_tag_already_adult_is_dropped_without_a_call(self):
        tag = Tag.objects.create(name="Smut", is_adult=True)
        candidate = self.make_request(tag)

        llm_tasks.run_queue(["tag_r18"])

        self.chat.assert_not_called()
        self.assertFalse(Candidate.objects.filter(pk=candidate.pk).exists())

    def test_parse_drops_unknown_ids_and_non_finite_confidence(self):
        tag = Tag.objects.create(name="Smut")
        candidate = make_candidate("tag_r18", [tag.pk])
        content = (
            '{"tags": [{"id": %d, "rating": "explicit", "confidence": NaN}, '
            '{"id": 999999, "rating": "explicit", "confidence": 1}]}' % tag.pk
        )
        result = llm_tasks.REGISTRY["tag_r18"].parse([candidate], None, content)
        self.assertEqual(set(result), {candidate.pk})
        self.assertEqual(result[candidate.pk]["answer"], "yes")
        self.assertEqual(result[candidate.pk]["confidence"], 0.0)

    def test_suggestive_tag_is_not_flagged_adult(self):
        tag = Tag.objects.create(name="Sexy")
        candidate = make_candidate("tag_r18", [tag.pk])
        content = json.dumps({"tags": [{"id": tag.pk, "rating": "suggestive", "confidence": 0.99}]})
        result = llm_tasks.REGISTRY["tag_r18"].parse([candidate], None, content)
        self.assertEqual(result[candidate.pk]["answer"], "no")
        self.assertEqual(result[candidate.pk]["rating"], "suggestive")

    def test_parse_skips_unknown_rating(self):
        porn = Tag.objects.create(name="Porn")
        smut = Tag.objects.create(name="Smut")
        porn_candidate = make_candidate("tag_r18", [porn.pk])
        smut_candidate = make_candidate("tag_r18", [smut.pk])
        content = (
            '{"tags": [{"id": %d, "rating": "porn", "confidence": 1}, '
            '{"id": %d, "rating": "explicit", "confidence": 0.9}]}' % (porn.pk, smut.pk)
        )
        result = llm_tasks.REGISTRY["tag_r18"].parse(
            [porn_candidate, smut_candidate], None, content,
        )
        self.assertEqual(result[porn_candidate.pk]["answer"], "no")
        self.assertEqual(result[porn_candidate.pk]["rating"], "omitted")
        self.assertEqual(result[smut_candidate.pk]["answer"], "yes")
        self.assertEqual(result[smut_candidate.pk]["confidence"], 0.9)

    def test_parse_accepts_an_empty_list(self):
        # The model lists only explicit or suggestive tags, so a clean batch is an empty list.
        tag = Tag.objects.create(name="Romance")
        candidate = make_candidate("tag_r18", [tag.pk])
        result = llm_tasks.REGISTRY["tag_r18"].parse([candidate], None, '{"tags": []}')
        self.assertEqual(result[candidate.pk]["answer"], "no")


@override_settings(LLM_API_KEY="key", LLM_DAILY_TOKENS=100000,
                   LLM_TOKENS_PER_MINUTE=8000, LLM_REQUESTS_PER_MINUTE=30)
class LLMBudgetRunTests(MergeTestCase):
    """The per-minute caps read the LLMCall rows, so the runner stops before a call."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(llm_service, "chat")
        self.chat = patcher.start()
        self.addCleanup(patcher.stop)

    def make_tag_candidate(self, name):
        tag = Tag.objects.create(name=name)
        return make_candidate("tag_r18", [tag.pk], [name])

    def make_merge_candidate(self):
        first = Tag.objects.create(name="M1")
        second = Tag.objects.create(name="M2")
        return make_candidate("tag_merge", [first.pk, second.pk], ["M1", "M2"])

    def test_per_minute_token_cap_stops_the_pass(self):
        candidate = self.make_tag_candidate("Smut")
        # Used + CALL_TOKENS is over LLM_TOKENS_PER_MINUTE (8000).
        LLMCall.objects.create(kind="tag_r18", tokens=8000 - llm_service.CALL_TOKENS + 1)

        llm_tasks.run_queue(["tag_r18"], limit=5)

        self.chat.assert_not_called()
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)

    @override_settings(LLM_REQUESTS_PER_MINUTE=2)
    def test_per_minute_request_cap_stops_the_pass(self):
        candidate = self.make_tag_candidate("Smut")
        LLMCall.objects.create(kind="tag_r18", tokens=0)
        LLMCall.objects.create(kind="tag_r18", tokens=0)

        llm_tasks.run_queue(["tag_r18"], limit=5)

        self.chat.assert_not_called()
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)

    def test_usage_older_than_a_minute_does_not_count(self):
        self.make_tag_candidate("Smut")
        old = LLMCall.objects.create(kind="tag_r18", tokens=8000)
        LLMCall.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(seconds=61))
        self.chat.side_effect = LLMParseError("no JSON object in reply")

        llm_tasks.run_queue(["tag_r18"], limit=5)

        self.chat.assert_called_once()

    def test_round_robin_takes_one_call_per_task_in_turn(self):
        self.make_tag_candidate("A1")
        merge = self.make_merge_candidate()
        self.chat.side_effect = LLMParseError("no JSON object in reply")

        llm_tasks.run_queue(["tag_r18", "tag_merge"], limit=2)

        self.assertEqual([call.args[2] for call in self.chat.call_args_list], ["tag_r18", "tag_merge"])
        merge.refresh_from_db()
        self.assertEqual(merge.attempts, 1)

    def test_rate_limit_stops_every_task(self):
        self.make_tag_candidate("A1")
        merge = self.make_merge_candidate()
        self.chat.side_effect = RateLimited(retry_after="30")

        counts = llm_tasks.run_queue(["tag_r18", "tag_merge"], limit=5)

        self.assertEqual(self.chat.call_count, 1)
        self.assertTrue(counts["rate_limited"])
        merge.refresh_from_db()
        self.assertEqual(merge.status, Candidate.STATUS_PENDING)
        self.assertEqual(merge.attempts, 0)


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
    """A ``_post_chat`` stand-in: per provider name, a ``(content, tokens, call)`` reply or an exception to raise."""
    def post(messages, max_tokens, purpose, provider=None, **kwargs):
        reply_for = replies[provider.name]
        if isinstance(reply_for, Exception):
            raise reply_for
        return reply_for
    return post


@override_settings(LLM_PROVIDERS=["cerebras", "groq"], LLM_PROVIDER_SETTINGS=CHAIN_SETTINGS)
class ProviderChainTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.tag = Tag.objects.create(name="Smut")
        self.reply = json.dumps({"tags": [{"id": self.tag.pk, "rating": "explicit", "confidence": 0.95}]})
        self.ok = (self.reply, 42, None)

    def make_candidate(self):
        return make_candidate("tag_r18", [self.tag.pk], [self.tag.name])

    def test_first_provider_answers(self):
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": self.ok})) as post:
            _content, _tokens, provider, _call = llm_service.chat([], 10, "tag_r18")

        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["cerebras"])
        self.assertEqual(provider.model, "gpt-oss-120b")

    def test_rate_limit_without_retry_after_falls_through_to_next_provider(self):
        replies = {"cerebras": RateLimited(), "groq": self.ok}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)) as post:
            _content, _tokens, provider, _call = llm_service.chat([], 10, "tag_r18")

        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["cerebras", "groq"])
        self.assertEqual(provider.model, "openai/gpt-oss-20b")
        cooling = LLMProviderCooldown.objects.get(name="cerebras")
        self.assertGreater(cooling.until, timezone.now() + timedelta(seconds=3500))
        self.assertLess(cooling.until, timezone.now() + timedelta(seconds=3700))

    def test_cooling_provider_is_skipped_until_its_cooldown_ends(self):
        LLMProviderCooldown.objects.create(
            name="cerebras", until=timezone.now() + timedelta(hours=1), reason="HTTP 429",
        )
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": self.ok, "groq": self.ok})) as post:
            llm_service.chat([], 10, "tag_r18")
        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["groq"])

        LLMProviderCooldown.objects.filter(name="cerebras").update(until=timezone.now() - timedelta(seconds=1))
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": self.ok})) as post:
            llm_service.chat([], 10, "tag_r18")
        self.assertEqual([c.kwargs["provider"].name for c in post.call_args_list], ["cerebras"])

    def test_every_provider_rate_limited_gives_the_candidate_back(self):
        candidate = self.make_candidate()
        replies = {"cerebras": RateLimited(), "groq": RateLimited()}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            counts = llm_tasks.run_queue(["tag_r18"])

        self.assertTrue(counts["rate_limited"])
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 0)
        self.assertAlmostEqual((candidate.not_before - timezone.now()).total_seconds(), 60, delta=5)
        self.assertFalse(llm_service.can_afford())

    @override_settings(LLM_PROVIDER_SETTINGS={
        **CHAIN_SETTINGS, "groq": {**CHAIN_SETTINGS["groq"], "daily_requests": 2},
    })
    def test_groq_daily_cap_blocks_the_chain_while_cerebras_cools_down(self):
        LLMProviderCooldown.objects.create(
            name="cerebras", until=timezone.now() + timedelta(hours=1), reason="HTTP 429",
        )
        LLMCall.objects.create(kind="tag_r18", provider="groq", tokens=0)
        LLMCall.objects.create(kind="tag_r18", provider="groq", tokens=0)
        self.make_candidate()

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_queue(["tag_r18"])

        post.assert_not_called()
        self.assertFalse(llm_service.can_afford())

    def test_post_chat_sends_the_provider_request_and_records_it(self):
        cerebras = llm_service.providers()[0]
        session = mock.Mock()
        session.post.return_value = mock.Mock(status_code=503, headers={}, text="busy")
        with self.assertRaises(ProviderUnavailable):
            llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session)
        self.assertFalse(LLMCall.objects.exists())

        response = mock.Mock(status_code=200, headers={}, text="")
        response.json.return_value = {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 7},
        }
        session.post.return_value = response
        llm_service._post_chat([], 10, "tag_r18", provider=cerebras, session=session)

        call = LLMCall.objects.get()
        self.assertEqual((call.provider, call.kind, call.tokens), ("cerebras", "tag_r18", 7))
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
        self.make_candidate()
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers({"cerebras": self.ok})) as post:
            llm_tasks.run_queue(["tag_r18"])

        self.assertEqual(post.call_args.kwargs["response_schema"], llm_tasks.TagR18Task.response_schema)

    def test_chat_outage_cools_the_provider_for_five_minutes_and_falls_through(self):
        replies = {"cerebras": ProviderUnavailable("HTTP 503: busy"), "groq": self.ok}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            content, _tokens, provider, _call = llm_service.chat([], 10, "tag_r18")

        self.assertEqual(provider.name, "groq")
        self.assertEqual(content, self.reply)
        cooling = LLMProviderCooldown.objects.get(name="cerebras")
        self.assertAlmostEqual((cooling.until - timezone.now()).total_seconds(), 300, delta=5)

    def test_other_http_error_tries_the_next_provider_without_cooldown(self):
        replies = {"cerebras": llm_service.LLMError("HTTP 400: unknown model"), "groq": self.ok}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            _content, _tokens, provider, _call = llm_service.chat([], 10, "tag_r18")

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
            _content, _tokens, provider, _call = llm_service.chat([], 10, "tag_r18")
        self.assertEqual(provider.name, "groq")

    def test_every_provider_down_records_why_on_the_candidate(self):
        candidate = self.make_candidate()
        replies = {"cerebras": ProviderUnavailable("HTTP 401: bad key"), "groq": RateLimited(retry_after="30")}
        with mock.patch.object(llm_service, "_post_chat", side_effect=_answers(replies)):
            llm_tasks.run_queue(["tag_r18"])

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 0)
        self.assertIn("cerebras: HTTP 401: bad key", candidate.reason)
        self.assertIn("groq: HTTP 429", candidate.reason)


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
