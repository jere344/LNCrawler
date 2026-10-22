"""Tests for the LLM judge of novel merges: the reply parsing, the provider call, the
LLMCall ledger the budget reads, and the decision the runner makes on a novel candidate.

The runner's own rules (decide, claims, drop of gone targets) are in test_llm_runner.
"""

import json
import shutil
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import Candidate, LLMCall, Novel
from ..services import llm_service, llm_tasks
from .helpers import MergeTestCase
from .test_candidate_apply import novel_pair, two_novels


def _chat_payload(content, finish_reason="stop", total_tokens=120):
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"total_tokens": total_tokens, "completion_tokens": total_tokens - 20},
    }


class _Response:
    def __init__(self, status, payload=None, headers=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class _Sequence(_Session):
    """A session answering each request with the next response of the list."""

    def __init__(self, responses):
        super().__init__(None)
        self.responses = list(responses)

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _judge_pair(profile_a, profile_b, session=None):
    """One judge call and parse, as the novel_merge task makes it."""
    content, _tokens, _call = llm_service._post_chat(
        llm_service.build_messages(profile_a, profile_b),
        llm_tasks.REGISTRY["novel_merge"].max_tokens,
        "novel_merge",
        session=session,
    )
    return llm_service._parse_content(content)


def _provider(name):
    return llm_service.Provider(
        name=name, url=f"http://{name}.test", api_key="k", model=name, reasoning_effort="",
        daily_requests=None, daily_tokens=None, requests_per_minute=None,
        tokens_per_minute=None, cooldown=60, shared_usage=False,
    )


class ParseTests(MergeTestCase):
    def test_parses_fenced_json_and_clamps_confidence(self):
        verdict = llm_service._parse_content(
            '```json\n{"same": true, "confidence": 5, "reason": "x"}\n```'
        )
        self.assertTrue(verdict["same"])
        self.assertEqual(verdict["confidence"], 1.0)

    def test_build_messages_lists_both_entries(self):
        messages = llm_service.build_messages(
            {"title": "Worm"}, {"title": "Worm (Parahumans #1)"}
        )
        user = messages[-1]["content"]
        self.assertIn("Worm", user)
        self.assertIn("Parahumans", user)

    def test_parse_rejects_malformed_and_non_object(self):
        for content in ("", "not json", "[1, 2, 3]", "123"):
            with self.assertRaises(llm_service.LLMError):
                llm_service._parse_content(content)

    def test_parse_salvages_truncated_verdict(self):
        # A long "reason" hitting the token cap used to drop a valid verdict.
        truncated = (
            '{"same": true, "confidence": 0.9, "reason": "Both entries share the '
            "exact title and the same author name, suggesting they refer"
        )
        verdict = llm_service._parse_content(truncated)
        self.assertTrue(verdict["same"])
        self.assertAlmostEqual(verdict["confidence"], 0.9)
        self.assertEqual(verdict["reason"], "")

    def test_parse_salvages_when_only_confidence_present(self):
        verdict = llm_service._parse_content('garbage {"confidence": 0.4}')
        self.assertFalse(verdict["same"])
        self.assertAlmostEqual(verdict["confidence"], 0.4)

    def test_parse_coerces_string_booleans(self):
        self.assertFalse(
            llm_service._parse_content('{"same": "false", "confidence": 0.1}')["same"]
        )
        self.assertTrue(llm_service._parse_content('{"same": "yes"}')["same"])


class JudgeTests(MergeTestCase):
    def test_judge_parses_openai_shape(self):
        payload = {"choices": [{"message": {"content":
            '{"same": true, "confidence": 0.8, "reason": "translation"}'}}]}
        session = _Session(_Response(200, payload))
        verdict = _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertTrue(verdict["same"])
        self.assertAlmostEqual(verdict["confidence"], 0.8)

    def test_judge_raises_rate_limited(self):
        session = _Session(_Response(429, headers={"Retry-After": "30"}))
        with self.assertRaises(llm_service.RateLimited) as ctx:
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(ctx.exception.retry_after, "30")

    def test_judge_raises_llm_error_on_non_json_body(self):
        class _Bad(_Response):
            def json(self):
                raise ValueError("no json")

        session = _Session(_Bad(200, text="<html>oops</html>"))
        with self.assertRaises(llm_service.LLMError):
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)

    @override_settings(LLM_API_KEY="")
    def test_is_configured_false_without_key(self):
        self.assertFalse(llm_service.is_configured())

    @override_settings(LLM_API_KEY="k")
    def test_is_configured_true_with_key(self):
        self.assertTrue(llm_service.is_configured())


class OutputDirMixin:
    """Novel merges write under LNCRAWL_OUTPUT_PATH: give each test its own directory."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-merge-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        output.enable()
        self.addCleanup(output.disable)


class JudgeCommandTests(OutputDirMixin, MergeTestCase):
    def setUp(self):
        super().setUp()
        self.first, self.second = two_novels(self)
        self.candidate = novel_pair(
            self.first, self.second, status=Candidate.STATUS_PENDING, verdict=None,
        )
        patcher = mock.patch.object(llm_service, "chat")
        self.chat = patcher.start()
        self.addCleanup(patcher.stop)

    def test_noop_when_unconfigured(self):
        with override_settings(LLM_API_KEY=""):
            call_command("run_llm", "novel_merge")
        self.chat.assert_not_called()
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_PENDING)

    def test_stores_verdict(self):
        verdict = {"same": True, "confidence": 0.9, "reason": "same work"}
        self.chat.return_value = (json.dumps(verdict), 120, "provider", None)
        with override_settings(LLM_API_KEY="key"):
            call_command("run_llm", "novel_merge")
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.verdict["answer"], "yes")
        self.assertAlmostEqual(self.candidate.confidence, 0.9)
        self.assertEqual(self.candidate.status, Candidate.STATUS_REVIEW)

    def test_respects_daily_budget(self):
        with override_settings(LLM_API_KEY="key", LLM_DAILY_REQUESTS=0):
            call_command("run_llm", "novel_merge")
        self.chat.assert_not_called()
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.STATUS_PENDING)
        self.assertIsNone(self.candidate.verdict)


class JudgeDecisionTests(OutputDirMixin, MergeTestCase):
    """The novel_merge decision, through the command, with the default thresholds."""

    def setUp(self):
        super().setUp()
        self.first, self.second = two_novels(self)
        self.candidate = novel_pair(
            self.first, self.second, status=Candidate.STATUS_PENDING, verdict=None,
        )
        patcher = mock.patch.object(llm_service, "chat")
        self.chat = patcher.start()
        self.addCleanup(patcher.stop)

    def _judge(self, verdict):
        self.chat.return_value = (json.dumps(verdict), 120, "provider", None)
        with override_settings(LLM_API_KEY="key"):
            call_command("run_llm", "novel_merge")
        self.candidate.refresh_from_db()

    def test_confident_different_is_rejected(self):
        self._judge({"same": False, "confidence": 0.95, "reason": "different works"})
        self.assertEqual(self.candidate.status, Candidate.STATUS_REJECTED)
        self.assertEqual(self.candidate.decided_by, Candidate.DECIDED_LLM)

    def test_unconfident_different_waits_for_review(self):
        self._judge({"same": False, "confidence": 0.5, "reason": "unsure"})
        self.assertEqual(self.candidate.status, Candidate.STATUS_REVIEW)

    def test_same_verdict_below_auto_confidence_waits_for_review(self):
        self._judge({"same": True, "confidence": 0.9, "reason": "same work"})
        self.assertEqual(self.candidate.status, Candidate.STATUS_REVIEW)
        self.assertEqual(Novel.objects.filter(pk__in=[self.first.pk, self.second.pk]).count(), 2)

    def test_confident_same_verdict_merges_the_pair(self):
        self._judge({"same": True, "confidence": 0.97, "reason": "same work"})
        self.assertEqual(self.candidate.status, Candidate.STATUS_APPLIED)
        self.assertEqual(self.candidate.decided_by, Candidate.DECIDED_LLM)
        self.assertEqual(Novel.objects.filter(pk__in=[self.first.pk, self.second.pk]).count(), 1)


class ReviewQueueOrderTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        user = self.make_superuser()
        self.client.force_login(user)
        self.count = 0

    def make_superuser(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_superuser("admin", "a@a.com", "pw")

    def _candidate(self, certainty, verdict=None):
        self.count += 1
        return Candidate.objects.create(
            kind=Candidate.KIND_NOVEL_MERGE,
            target_ids=[self.count * 2, self.count * 2 + 1],
            target_names=[f"Left {self.count}", f"Right {self.count}"],
            signature=f"queue-{self.count}",
            status=Candidate.STATUS_REVIEW,
            certainty=certainty,
            verdict=verdict,
            confidence=verdict["confidence"] if verdict else None,
        )

    def test_review_queue_order(self):
        judged_same_high = self._candidate(0.5, {"answer": "yes", "confidence": 0.95, "reason": ""})
        judged_same_low = self._candidate(0.9, {"answer": "yes", "confidence": 0.6, "reason": ""})
        unjudged_high = self._candidate(0.95)
        unjudged_low = self._candidate(0.6)
        judged_different = self._candidate(0.99, {"answer": "no", "confidence": 0.3, "reason": ""})

        url = reverse("admin:lncrawler_api_candidate_review", args=["novel_merge"])
        expected = [judged_same_high, judged_same_low, unjudged_high, unjudged_low, judged_different]
        for candidate in expected:
            response = self.client.get(url)
            self.assertEqual(response.context["candidate"].pk, candidate.pk)
            self.client.post(url, {"candidate": str(candidate.pk), "action": "skip"})


class RequestBodyTests(MergeTestCase):
    @staticmethod
    def _body(session):
        return session.calls[0][1]["json"]

    @override_settings(LLM_API_KEY="key", LLM_REASONING_EFFORT="low")
    def test_reasoning_effort_sent_when_set(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}')))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(self._body(session)["reasoning_effort"], "low")

    @override_settings(LLM_API_KEY="key", LLM_REASONING_EFFORT="")
    def test_reasoning_effort_omitted_when_empty(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}')))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertNotIn("reasoning_effort", self._body(session))

    @override_settings(LLM_API_KEY="key")
    def test_judge_uses_novel_merge_max_tokens(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}')))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(self._body(session)["max_tokens"], 2048)


class TruncationTests(MergeTestCase):
    def test_length_finish_reason_raises_truncated(self):
        session = _Session(_Response(200, _chat_payload('{"same": tr', finish_reason="length")))
        with self.assertRaises(llm_service.LLMTruncated) as ctx:
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertIn("finish_reason='length'", str(ctx.exception))
        self.assertIn("completion_tokens=100", str(ctx.exception))
        self.assertIsInstance(ctx.exception, llm_service.LLMParseError)

    def test_empty_content_raises_truncated(self):
        session = _Session(_Response(200, _chat_payload("", finish_reason="stop")))
        with self.assertRaises(llm_service.LLMTruncated):
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)

    def test_null_content_raises_truncated(self):
        session = _Session(_Response(200, _chat_payload(None, finish_reason="stop")))
        with self.assertRaises(llm_service.LLMTruncated):
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)


class LLMCallLedgerTests(MergeTestCase):
    """Every reply the provider returned is one LLMCall: the budget and the history read it."""

    def test_row_written_for_success_and_truncated_replies(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}', total_tokens=900)))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        session = _Session(_Response(200, _chat_payload("", "length", total_tokens=2048)))
        with self.assertRaises(llm_service.LLMTruncated):
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        rows = list(LLMCall.objects.order_by("pk").values_list("kind", "tokens"))
        self.assertEqual(rows, [("novel_merge", 900), ("novel_merge", 2048)])

    def test_non_json_reply_is_charged_and_kept(self):
        session = _Session(_Response(200, _chat_payload("not json", total_tokens=300)))
        with self.assertRaises(llm_service.LLMError):
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        call = LLMCall.objects.get()
        self.assertEqual(call.tokens, 300)

    def test_fallback_reply_is_charged_to_the_provider_that_answered(self):
        session = _Sequence([
            _Response(500, text="down"),
            _Response(200, _chat_payload('{"same": true}', total_tokens=300)),
        ])
        messages = llm_service.build_messages({"title": "a"}, {"title": "b"})
        providers = [_provider("first"), _provider("second")]
        with mock.patch.object(llm_service, "providers", return_value=providers):
            with override_settings(LLM_API_KEY="key"):
                _content, tokens, provider, _call = llm_service.chat(
                    messages, 2048, "novel_merge", session=session,
                )
        self.assertEqual(provider.name, "second")
        self.assertEqual(tokens, 300)
        # The 500 of the first provider is not charged: one row, under the second.
        call = LLMCall.objects.get()
        self.assertEqual((call.provider, call.tokens), ("second", 300))

    def test_no_row_on_rate_limit_or_http_error(self):
        for response in (_Response(429, headers={}), _Response(500, text="boom")):
            session = _Session(response)
            with self.assertRaises(llm_service.LLMError):
                _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertFalse(LLMCall.objects.exists())

    def test_missing_usage_records_zero(self):
        payload = {"choices": [{"message": {"content": '{"same": true}'}, "finish_reason": "stop"}]}
        session = _Session(_Response(200, payload))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(LLMCall.objects.get().tokens, 0)

    @override_settings(LLM_DAILY_TOKENS=1000)
    def test_budget_left_counts_all_purposes(self):
        LLMCall.objects.create(kind="novel_merge", tokens=300)
        LLMCall.objects.create(kind="tag_merge", tokens=200)
        self.assertEqual(llm_service.tokens_used_today(), 500)
        self.assertEqual(llm_service.token_budget_left(), 500)


class JudgeTokenBudgetTests(OutputDirMixin, MergeTestCase):
    def setUp(self):
        super().setUp()
        self.candidates = []
        for n in (1, 2):
            a = Novel.objects.create(title=f"A{n}", slug=f"a{n}", novel_path=f"a{n}")
            b = Novel.objects.create(title=f"B{n}", slug=f"b{n}", novel_path=f"b{n}")
            self.candidates.append(Candidate.objects.create(
                kind=Candidate.KIND_NOVEL_MERGE, target_ids=[str(a.pk), str(b.pk)],
                target_names=[a.title, b.title], signature=f"budget-{n}",
                status=Candidate.STATUS_PENDING,
            ))

    @override_settings(LLM_API_KEY="key",
                       LLM_DAILY_TOKENS=171000, LLM_TOKENS_PER_MINUTE=1000000)
    def test_stops_before_call_when_budget_below_one_call(self):
        # 1000 left is below CALL_TOKENS (2500).
        LLMCall.objects.create(kind="tag_merge", tokens=170000)
        with mock.patch.object(llm_service, "chat") as chat:
            call_command("run_llm", "novel_merge")
        chat.assert_not_called()

    @override_settings(LLM_API_KEY="key",
                       LLM_DAILY_TOKENS=4000, LLM_TOKENS_PER_MINUTE=1000000)
    def test_budget_checked_before_every_call(self):
        def spend(*args, **kwargs):
            LLMCall.objects.create(kind="novel_merge", tokens=5000)
            return json.dumps({"same": True, "confidence": 0.9, "reason": "same"}), 5000, "p", None

        with mock.patch.object(llm_service, "chat", side_effect=spend) as chat:
            call_command("run_llm", "novel_merge")
        self.assertEqual(chat.call_count, 1)
        self.candidates[0].refresh_from_db()
        self.candidates[1].refresh_from_db()
        self.assertEqual(self.candidates[0].status, Candidate.STATUS_REVIEW)
        self.assertEqual(self.candidates[1].status, Candidate.STATUS_PENDING)

    @override_settings(LLM_API_KEY="key", LLM_DAILY_TOKENS=180000)
    def test_truncated_reply_leaves_candidate_unchecked_and_is_charged(self):
        payload = _chat_payload("", "length", total_tokens=2048)
        with mock.patch.object(llm_service.requests, "post",
                               return_value=_Response(200, payload)):
            call_command("run_llm", "novel_merge")
        for candidate in self.candidates:
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
            self.assertIsNone(candidate.verdict)
            # Each failed request goes back to the queue with a backoff, not ERROR yet.
            self.assertEqual(candidate.attempts, 1)
            self.assertIsNotNone(candidate.not_before)
        self.assertTrue(LLMCall.objects.exists())
        self.assertEqual(set(LLMCall.objects.values_list("tokens", flat=True)), {2048})

    @override_settings(LLM_API_KEY="key", LLM_DAILY_TOKENS=180000)
    def test_non_json_reply_leaves_candidate_unchecked_and_is_charged(self):
        payload = _chat_payload("I cannot decide.", total_tokens=400)
        with mock.patch.object(llm_service.requests, "post",
                               return_value=_Response(200, payload)):
            call_command("run_llm", "novel_merge")
        self.candidates[0].refresh_from_db()
        self.assertEqual(self.candidates[0].status, Candidate.STATUS_PENDING)
        self.assertIsNone(self.candidates[0].verdict)
        self.assertEqual(self.candidates[0].attempts, 1)
        self.assertTrue(LLMCall.objects.exists())
        self.assertEqual(set(LLMCall.objects.values_list("tokens", flat=True)), {400})
