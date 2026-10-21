"""Tests for the optional LLM gray-band adjudication."""

import importlib
import json
from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import ExternalSource, LLMRequest, LLMUsage, MergeCandidate, Novel, NovelFromSource
from ..services import llm_service, llm_tasks
from .helpers import MergeTestCase

migration = importlib.import_module("lncrawler_api.migrations.0088_port_merge_llm_verdicts")


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


def _judge_pair(profile_a, profile_b, session=None):
    """One judge call and parse: what the removed llm_service.judge() did."""
    content, _tokens = llm_service._post_chat(
        llm_service.build_messages(profile_a, profile_b),
        llm_tasks.REGISTRY["novel_merge"].max_tokens,
        "novel_merge",
        session=session,
    )
    return llm_service._parse_content(content)


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
            call_command("run_llm_requests", "novel_merge")
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.llm_checked_at)
        self.assertFalse(LLMRequest.objects.exists())

    def test_stores_verdict(self):
        verdict = {"same": True, "confidence": 0.9, "reason": "same work"}
        with mock.patch.object(llm_service, "_post_chat",
                               return_value=(json.dumps(verdict), 120)):
            with override_settings(LLM_API_KEY="key"):
                call_command("run_llm_requests", "novel_merge")
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.llm_verdict, verdict)
        self.assertIsNotNone(self.candidate.llm_checked_at)
        self.assertEqual(LLMRequest.objects.get().status, LLMRequest.STATUS_DONE)

    def test_respects_daily_budget(self):
        with mock.patch.object(llm_service, "_post_chat") as post:
            with override_settings(LLM_API_KEY="key", LLM_DAILY_REQUESTS=0):
                call_command("run_llm_requests", "novel_merge")
        post.assert_not_called()
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.llm_verdict)
        self.assertIsNone(self.candidate.llm_checked_at)


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
        with mock.patch.object(llm_service, "_post_chat",
                               return_value=(json.dumps(verdict), 120)):
            with override_settings(LLM_API_KEY="key"):
                call_command("run_llm_requests", "novel_merge")
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

    @override_settings(MERGE_LLM_AUTO_CONFIDENCE=0.95)
    def test_same_verdict_below_auto_confidence_stays_pending(self):
        self._judge({"same": True, "confidence": 0.9, "reason": "same work"})
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_PENDING)
        self.assertEqual(Novel.objects.count(), 2)

    @override_settings(MERGE_LLM_AUTO_CONFIDENCE=0.95)
    def test_confident_same_verdict_merges_the_pair(self):
        self._judge({"same": True, "confidence": 0.97, "reason": "same work"})
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_MERGED)
        self.assertEqual(self.candidate.decision, MergeCandidate.DECISION_AUTO)
        self.assertIsNotNone(self.candidate.merged_at)
        self.assertEqual(Novel.objects.count(), 1)

    @override_settings(MERGE_LLM_AUTO_CONFIDENCE=0.95)
    def test_confident_same_verdict_in_a_chain_stays_pending(self):
        c = Novel.objects.create(title="Alpha?", slug="alpha-c", novel_path="alpha-c")
        MergeCandidate.objects.create(
            novel_a=self.b, novel_b=c, title_a=self.b.title, title_b=c.title,
            certainty=0.6, decision=MergeCandidate.DECISION_REVIEW,
        )
        # Both pairs get the verdict; each sees the other still pending.
        self._judge({"same": True, "confidence": 0.99, "reason": "same work"})
        self.assertEqual(self.candidate.status, MergeCandidate.STATUS_PENDING)
        self.assertEqual(Novel.objects.count(), 3)


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
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(self._body(session)["reasoning_effort"], "low")

    @override_settings(LLM_API_KEY="key", LLM_REASONING_EFFORT="")
    def test_reasoning_effort_omitted_when_empty(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}')))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertNotIn("reasoning_effort", self._body(session))

    @override_settings(LLM_API_KEY="key")
    def test_judge_uses_merge_llm_max_tokens(self):
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


class UsageLedgerTests(MergeTestCase):
    def test_row_written_for_success_and_truncated_replies(self):
        session = _Session(_Response(200, _chat_payload('{"same": true}', total_tokens=900)))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        session = _Session(_Response(200, _chat_payload("", "length", total_tokens=2048)))
        with self.assertRaises(llm_service.LLMTruncated):
            _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        rows = list(LLMUsage.objects.order_by("pk").values_list("purpose", "tokens"))
        self.assertEqual(rows, [("novel_merge", 900), ("novel_merge", 2048)])

    def test_no_row_on_rate_limit_or_http_error(self):
        for response in (_Response(429, headers={}), _Response(500, text="boom")):
            session = _Session(response)
            with self.assertRaises(llm_service.LLMError):
                _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertFalse(LLMUsage.objects.exists())

    def test_missing_usage_records_zero(self):
        payload = {"choices": [{"message": {"content": '{"same": true}'}, "finish_reason": "stop"}]}
        session = _Session(_Response(200, payload))
        _judge_pair({"title": "a"}, {"title": "b"}, session=session)
        self.assertEqual(LLMUsage.objects.get().tokens, 0)

    @override_settings(LLM_DAILY_TOKENS=1000)
    def test_budget_left_counts_all_purposes(self):
        LLMUsage.objects.create(purpose="novel_merge", tokens=300)
        LLMUsage.objects.create(purpose="tag_merge", tokens=200)
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
                       LLM_DAILY_TOKENS=171000, LLM_TOKENS_PER_MINUTE=1000000)
    def test_stops_before_call_when_budget_below_one_call(self):
        # 1000 left is below CALL_TOKENS (1500).
        LLMUsage.objects.create(purpose="tag_merge", tokens=170000)
        with mock.patch.object(llm_service, "_post_chat") as post:
            call_command("run_llm_requests", "novel_merge")
        post.assert_not_called()

    @override_settings(LLM_API_KEY="key",
                       LLM_DAILY_TOKENS=4000, LLM_TOKENS_PER_MINUTE=1000000)
    def test_budget_checked_before_every_call(self):
        def spend(*args, **kwargs):
            LLMUsage.objects.create(purpose="novel_merge", tokens=5000)
            return json.dumps({"same": True, "confidence": 0.9, "reason": "same"}), 5000

        with mock.patch.object(llm_service, "_post_chat", side_effect=spend) as post:
            call_command("run_llm_requests", "novel_merge")
        self.assertEqual(post.call_count, 1)
        self.candidates[0].refresh_from_db()
        self.candidates[1].refresh_from_db()
        self.assertIsNotNone(self.candidates[0].llm_checked_at)
        self.assertIsNone(self.candidates[1].llm_checked_at)

    @override_settings(LLM_API_KEY="key", LLM_DAILY_TOKENS=180000)
    def test_truncated_reply_leaves_candidate_unchecked(self):
        payload = _chat_payload("", "length", total_tokens=2048)
        with mock.patch.object(llm_service.requests, "post",
                               return_value=_Response(200, payload)):
            call_command("run_llm_requests", "novel_merge")
        for candidate in self.candidates:
            candidate.refresh_from_db()
            self.assertIsNone(candidate.llm_checked_at)
            self.assertIsNone(candidate.llm_verdict)
        # Each failed request goes back to the queue with a backoff, not FAILED yet.
        for req in LLMRequest.objects.filter(task="novel_merge"):
            self.assertEqual(req.status, LLMRequest.STATUS_PENDING)
            self.assertEqual(req.attempts, 1)
            self.assertIsNotNone(req.not_before)
        self.assertEqual(list(LLMUsage.objects.values_list("tokens", flat=True)), [2048, 2048])


@override_settings(LLM_API_KEY="key")
class NovelMergeTaskTests(MergeTestCase):
    def _candidate(self, n, certainty, **extra):
        a = Novel.objects.create(title=f"A{n}", slug=f"qa{n}", novel_path=f"qa{n}")
        b = Novel.objects.create(title=f"B{n}", slug=f"qb{n}", novel_path=f"qb{n}")
        return MergeCandidate.objects.create(
            novel_a=a, novel_b=b, title_a=a.title, title_b=b.title,
            certainty=certainty, decision=MergeCandidate.DECISION_REVIEW, **extra,
        )

    @staticmethod
    def _request(candidate, status, **extra):
        return LLMRequest.objects.create(
            task="novel_merge",
            target_type="merge_candidate",
            target_ids=[str(candidate.pk)],
            prompt_version=llm_tasks.REGISTRY["novel_merge"].prompt_version,
            status=status,
            **extra,
        )

    def test_enqueue_skips_covered_and_requeues_after_done_clear(self):
        pending = self._candidate(1, 0.9)
        failed = self._candidate(2, 0.8)
        judged = self._candidate(3, 0.7, llm_checked_at=timezone.now())
        self._request(pending, LLMRequest.STATUS_PENDING)
        self._request(failed, LLMRequest.STATUS_FAILED)
        self._request(judged, LLMRequest.STATUS_DONE)
        task = llm_tasks.REGISTRY["novel_merge"]

        self.assertEqual(task.enqueue(10), 0)

        # Someone cleared the verdict to re-judge: the DONE request no longer covers it.
        judged.llm_checked_at = None
        judged.save(update_fields=["llm_checked_at"])
        self.assertEqual(task.enqueue(10), 1)
        newest = LLMRequest.objects.filter(task="novel_merge").order_by("-created_at").first()
        self.assertEqual(newest.target_ids, [str(judged.pk)])

    def test_rejudge_action_sends_pairs_back_unjudged(self):
        from django.contrib import admin
        from ..admin.merge_admin import MergeCandidateAdmin

        verdict = {"same": False, "confidence": 1.0, "reason": "different"}
        skipped = self._candidate(1, 0.5, status=MergeCandidate.STATUS_SKIPPED,
                                  llm_verdict=verdict, llm_checked_at=timezone.now())
        pending = self._candidate(2, 0.9, llm_verdict=verdict, llm_checked_at=timezone.now())
        merged = self._candidate(3, 0.9, status=MergeCandidate.STATUS_MERGED)
        stale = self._candidate(4, 0.9, status=MergeCandidate.STATUS_SKIPPED)
        stale.novel_b.delete()
        self._request(skipped, LLMRequest.STATUS_DONE)

        model_admin = MergeCandidateAdmin(MergeCandidate, admin.site)
        with mock.patch.object(model_admin, "message_user"):
            model_admin.rejudge_candidates(None, MergeCandidate.objects.all())

        for candidate in (skipped, pending):
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, MergeCandidate.STATUS_PENDING)
            self.assertIsNone(candidate.llm_checked_at)
            self.assertIsNone(candidate.llm_verdict)
        merged.refresh_from_db()
        stale.refresh_from_db()
        self.assertEqual(merged.status, MergeCandidate.STATUS_MERGED)
        self.assertEqual(stale.status, MergeCandidate.STATUS_SKIPPED)
        # Both re-judged pairs are queued again; the DONE request does not cover them.
        self.assertEqual(llm_tasks.REGISTRY["novel_merge"].enqueue(10), 2)

    @override_settings(MERGE_LLM_DISMISS_CONFIDENCE=0.9, MERGE_LLM_DISMISS_MAX_CERTAINTY=0.8)
    def test_apply_does_not_dismiss_candidate_no_longer_pending(self):
        candidate = self._candidate(1, 0.7, status=MergeCandidate.STATUS_REJECTED)
        req = self._request(candidate, LLMRequest.STATUS_RUNNING, model="openai/test")

        llm_tasks.REGISTRY["novel_merge"].apply(
            req, {"same": False, "confidence": 0.95, "reason": "different works"}
        )

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, MergeCandidate.STATUS_REJECTED)
        self.assertEqual(candidate.llm_reason, "different works")
        self.assertEqual(candidate.llm_model, "openai/test")
        self.assertIsNotNone(candidate.llm_checked_at)


    def test_requeued_done_request_keeps_its_verdict(self):
        verdict = {"same": True, "confidence": 0.9, "reason": "same work"}
        candidate = self._candidate(1, 0.7, llm_verdict=verdict, llm_checked_at=timezone.now())
        req = self._request(candidate, LLMRequest.STATUS_PENDING, response=verdict)

        with mock.patch.object(llm_service, "_post_chat") as post:
            llm_tasks.run_task("novel_merge", 1)

        post.assert_not_called()
        req.refresh_from_db()
        self.assertEqual(req.status, LLMRequest.STATUS_DONE)
        self.assertEqual(req.response, verdict)

    def test_reapply_ignores_skipped_requests(self):
        from django.contrib import admin as django_admin
        from ..admin.llm_admin import LLMRequestAdmin

        candidate = self._candidate(1, 0.7)
        self._request(candidate, LLMRequest.STATUS_DONE, response={"skipped": "no targets left"})
        model_admin = LLMRequestAdmin(LLMRequest, django_admin.site)

        with mock.patch.object(model_admin, "message_user"):
            model_admin.reapply_result(None, LLMRequest.objects.all())

        candidate.refresh_from_db()
        self.assertIsNone(candidate.llm_verdict)
        self.assertIsNone(candidate.llm_checked_at)


class PortMergeVerdictsMigrationTests(MergeTestCase):
    def _candidate(self, n, **extra):
        a = Novel.objects.create(title=f"A{n}", slug=f"ma{n}", novel_path=f"ma{n}")
        b = Novel.objects.create(title=f"B{n}", slug=f"mb{n}", novel_path=f"mb{n}")
        return MergeCandidate.objects.create(
            novel_a=a, novel_b=b, title_a=a.title, title_b=b.title, **extra,
        )

    def test_forward_creates_done_request_per_judged_candidate(self):
        verdict = {"same": True, "confidence": 0.9, "reason": "same work"}
        checked_at = timezone.now() - timedelta(days=3)
        judged = self._candidate(
            1, llm_verdict=verdict, llm_reason="same work",
            llm_model="openai/gpt-oss-20b", llm_checked_at=checked_at,
        )
        self._candidate(2)  # never judged
        self._candidate(3, llm_verdict=verdict)  # verdict without a check time

        migration.port_verdicts(apps, None)

        req = LLMRequest.objects.get(task="novel_merge")
        self.assertEqual(req.target_ids, [str(judged.pk)])
        self.assertEqual(req.target_type, "merge_candidate")
        self.assertEqual(req.status, LLMRequest.STATUS_DONE)
        self.assertEqual(req.response, verdict)
        self.assertEqual(req.model, "openai/gpt-oss-20b")
        self.assertEqual(req.attempts, 1)
        self.assertEqual(req.tokens, 0)
        self.assertEqual(req.finished_at, checked_at)
        self.assertEqual(req.created_at, checked_at)
        self.assertFalse(LLMUsage.objects.exists())

    def test_reverse_deletes_only_novel_merge_requests(self):
        LLMRequest.objects.create(task="tag_r18", target_type="tag", target_ids=[1], prompt_version="1")
        LLMRequest.objects.create(
            task="novel_merge", target_type="merge_candidate", target_ids=["x"], prompt_version="1",
        )

        migration.unport_verdicts(apps, None)

        self.assertEqual(list(LLMRequest.objects.values_list("task", flat=True)), ["tag_r18"])
