"""Tests for the optional LLM gray-band adjudication."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import ExternalSource, LLMUsage, MergeCandidate, Novel, NovelFromSource
from ..services import llm_service
from .helpers import MergeTestCase


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
        verdict = llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertTrue(verdict["same"])
        self.assertAlmostEqual(verdict["confidence"], 0.8)

    def test_judge_raises_rate_limited(self):
        session = _Session(_Response(429, headers={"Retry-After": "30"}))
        with self.assertRaises(llm_service.RateLimited) as ctx:
            llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(ctx.exception.retry_after, "30")

    def test_judge_raises_llm_error_on_non_json_body(self):
        class _Bad(_Response):
            def json(self):
                raise ValueError("no json")

        session = _Session(_Bad(200, text="<html>oops</html>"))
        with self.assertRaises(llm_service.LLMError):
            llm_service.judge({"title": "a"}, {"title": "b"}, session=session)

    @override_settings(LLM_API_KEY="")
    def test_is_configured_false_without_key(self):
        self.assertFalse(llm_service.is_configured())

    @override_settings(LLM_API_KEY="k")
    def test_is_configured_true_with_key(self):
        self.assertTrue(llm_service.is_configured())


class JudgeCommandTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.es = ExternalSource.objects.create(source_name="site")
        self.a = Novel.objects.create(title="Alpha", slug="alpha", novel_path="alpha")
        self.b = Novel.objects.create(title="Alpha!", slug="alpha-b", novel_path="alpha-b")
        self.candidate = MergeCandidate.objects.create(
            novel_a=self.a, novel_b=self.b, title_a=self.a.title, title_b=self.b.title,
            certainty=0.7, decision=MergeCandidate.DECISION_REVIEW,
        )

    def test_noop_when_unconfigured(self):
        with override_settings(LLM_API_KEY=""):
            call_command("judge_merge_candidates")
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.llm_checked_at)

    def test_stores_verdict(self):
        verdict = {"same": True, "confidence": 0.9, "reason": "same work"}
        with mock.patch.object(llm_service, "judge", return_value=verdict):
            with override_settings(LLM_API_KEY="key"):
                call_command("judge_merge_candidates")
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.llm_verdict, verdict)
        self.assertIsNotNone(self.candidate.llm_checked_at)

    def test_respects_daily_budget(self):
        self.candidate.llm_checked_at = None
        self.candidate.save(update_fields=["llm_checked_at"])
        MergeCandidate.objects.filter(pk=self.candidate.pk).update(
            llm_checked_at="2020-01-01T00:00:00Z"
        )
        with override_settings(LLM_API_KEY="key", LLM_DAILY_REQUESTS=0):
            call_command("judge_merge_candidates")
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.llm_verdict)


@override_settings(MERGE_LLM_DISMISS_CONFIDENCE=0.9, MERGE_LLM_DISMISS_MAX_CERTAINTY=0.8)
class JudgeDismissTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.a = Novel.objects.create(title="Alpha", slug="alpha", novel_path="alpha")
        self.b = Novel.objects.create(title="Alpha!", slug="alpha-b", novel_path="alpha-b")
        self.candidate = MergeCandidate.objects.create(
            novel_a=self.a, novel_b=self.b, title_a=self.a.title, title_b=self.b.title,
            certainty=0.7, decision=MergeCandidate.DECISION_REVIEW,
        )

    def _judge(self, verdict):
        with mock.patch.object(llm_service, "judge", return_value=verdict):
            with override_settings(LLM_API_KEY="key"):
                call_command("judge_merge_candidates")
        self.candidate.refresh_from_db()

    def test_confident_different_on_weak_candidate_is_skipped(self):
        self._judge({"same": False, "confidence": 0.95, "reason": "different works"})
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_SKIPPED)
        self.assertIsNotNone(self.candidate.llm_checked_at)

    def test_high_certainty_different_verdict_stays_pending(self):
        self.candidate.certainty = 0.9
        self.candidate.save(update_fields=["certainty"])
        self._judge({"same": False, "confidence": 0.95, "reason": "different works"})
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_PENDING)

    def test_unconfident_different_verdict_stays_pending(self):
        self._judge({"same": False, "confidence": 0.5, "reason": "unsure"})
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_PENDING)

    def test_same_verdict_stays_pending(self):
        self._judge({"same": True, "confidence": 0.99, "reason": "same work"})
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_PENDING)


class ReviewQueueOrderTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        user = get_user_model().objects.create_superuser("admin", "a@a.com", "pw")
        self.client.force_login(user)
        self.count = 0

    def _candidate(self, certainty, verdict=None):
        self.count += 1
        a = Novel.objects.create(
            title=f"Left {self.count}", slug=f"left-{self.count}", novel_path=f"left-{self.count}"
        )
        b = Novel.objects.create(
            title=f"Right {self.count}", slug=f"right-{self.count}", novel_path=f"right-{self.count}"
        )
        return MergeCandidate.objects.create(
            novel_a=a, novel_b=b, title_a=a.title, title_b=b.title, certainty=certainty,
            llm_verdict=verdict,
            llm_checked_at=timezone.now() if verdict is not None else None,
        )

    def test_review_queue_order(self):
        judged_same_high = self._candidate(0.5, {"same": True, "confidence": 0.95, "reason": ""})
        judged_same_low = self._candidate(0.9, {"same": True, "confidence": 0.6, "reason": ""})
        unjudged_high = self._candidate(0.95)
        unjudged_low = self._candidate(0.6)
        judged_different = self._candidate(0.99, {"same": False, "confidence": 0.3, "reason": ""})

        url = reverse("admin:lncrawler_api_mergecandidate_review")
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
        llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(self._body(session)["reasoning_effort"], "low")

    @override_settings(LLM_API_KEY="key", LLM_REASONING_EFFORT="")
    def test_reasoning_effort_omitted_when_empty(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}')))
        llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertNotIn("reasoning_effort", self._body(session))

    @override_settings(LLM_API_KEY="key")
    def test_judge_uses_merge_llm_max_tokens(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}')))
        llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(self._body(session)["max_tokens"], 2048)


class TruncationTests(MergeTestCase):
    def test_length_finish_reason_raises_truncated(self):
        session = _Session(_Response(200, _chat_payload('{"same": tr', finish_reason="length")))
        with self.assertRaises(llm_service.LLMTruncated) as ctx:
            llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertIn("finish_reason='length'", str(ctx.exception))
        self.assertIn("completion_tokens=100", str(ctx.exception))
        self.assertIsInstance(ctx.exception, llm_service.LLMParseError)

    def test_empty_content_raises_truncated(self):
        session = _Session(_Response(200, _chat_payload("", finish_reason="stop")))
        with self.assertRaises(llm_service.LLMTruncated):
            llm_service.judge({"title": "a"}, {"title": "b"}, session=session)

    def test_null_content_raises_truncated(self):
        session = _Session(_Response(200, _chat_payload(None, finish_reason="stop")))
        with self.assertRaises(llm_service.LLMTruncated):
            llm_service.judge({"title": "a"}, {"title": "b"}, session=session)


class UsageLedgerTests(MergeTestCase):
    def test_row_written_for_success_and_truncated_replies(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}', total_tokens=900)))
        llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        session = _Session(_Response(200, _chat_payload("", "length", total_tokens=2048)))
        with self.assertRaises(llm_service.LLMTruncated):
            llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        rows = list(LLMUsage.objects.order_by("pk").values_list("purpose", "tokens"))
        self.assertEqual(rows, [("novel", 900), ("novel", 2048)])

    def test_no_row_on_rate_limit_or_http_error(self):
        for response in (_Response(429, headers={}), _Response(500, text="boom")):
            session = _Session(response)
            with self.assertRaises(llm_service.LLMError):
                llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertFalse(LLMUsage.objects.exists())

    def test_missing_usage_records_zero(self):
        payload = {"choices": [{"message": {"content": '{"same": true}'}, "finish_reason": "stop"}]}
        session = _Session(_Response(200, payload))
        llm_service.judge({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(LLMUsage.objects.get().tokens, 0)

    @override_settings(LLM_DAILY_TOKENS=1000)
    def test_budget_left_counts_all_purposes(self):
        LLMUsage.objects.create(purpose=LLMUsage.PURPOSE_NOVEL, tokens=300)
        LLMUsage.objects.create(purpose=LLMUsage.PURPOSE_TAG, tokens=200)
        self.assertEqual(llm_service.tokens_used_today(), 500)
        self.assertEqual(llm_service.token_budget_left(), 500)


class JudgeTokenBudgetTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.candidates = []
        for n in (1, 2):
            a = Novel.objects.create(title=f"A{n}", slug=f"a{n}", novel_path=f"a{n}")
            b = Novel.objects.create(title=f"B{n}", slug=f"b{n}", novel_path=f"b{n}")
            self.candidates.append(MergeCandidate.objects.create(
                novel_a=a, novel_b=b, title_a=a.title, title_b=b.title,
                certainty=0.9 - n / 10, decision=MergeCandidate.DECISION_REVIEW,
            ))

    @override_settings(LLM_API_KEY="key",
                       MERGE_LLM_MAX_TOKENS=2048, LLM_DAILY_TOKENS=171000)
    def test_stops_before_call_when_budget_below_reserve(self):
        LLMUsage.objects.create(purpose=LLMUsage.PURPOSE_TAG, tokens=170000)
        with mock.patch.object(llm_service, "judge") as judge:
            call_command("judge_merge_candidates")
        judge.assert_not_called()

    @override_settings(LLM_API_KEY="key",
                       MERGE_LLM_MAX_TOKENS=2048, LLM_DAILY_TOKENS=4000)
    def test_budget_checked_before_every_call(self):
        def spend(*args, **kwargs):
            LLMUsage.objects.create(purpose=LLMUsage.PURPOSE_NOVEL, tokens=5000)
            return {"same": True, "confidence": 0.9, "reason": "same"}

        with mock.patch.object(llm_service, "judge", side_effect=spend) as judge:
            call_command("judge_merge_candidates")
        self.assertEqual(judge.call_count, 1)
        self.candidates[0].refresh_from_db()
        self.candidates[1].refresh_from_db()
        self.assertIsNotNone(self.candidates[0].llm_checked_at)
        self.assertIsNone(self.candidates[1].llm_checked_at)

    @override_settings(LLM_API_KEY="key",
                       MERGE_LLM_MAX_TOKENS=2048, LLM_DAILY_TOKENS=180000)
    def test_truncated_reply_leaves_candidate_unchecked(self):
        payload = _chat_payload("", "length", total_tokens=2048)
        with mock.patch.object(llm_service.requests, "post",
                               return_value=_Response(200, payload)):
            call_command("judge_merge_candidates")
        for candidate in self.candidates:
            candidate.refresh_from_db()
            self.assertIsNone(candidate.llm_checked_at)
            self.assertIsNone(candidate.llm_verdict)
        self.assertEqual(LLMUsage.objects.get().tokens, 2048)
