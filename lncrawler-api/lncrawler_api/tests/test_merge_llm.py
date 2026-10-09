"""Tests for the optional LLM gray-band adjudication."""

from unittest import mock

from django.core.management import call_command
from django.test import override_settings

from ..models import ExternalSource, MergeCandidate, Novel, NovelFromSource
from ..services import llm_service
from .helpers import MergeTestCase


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

    @override_settings(MERGE_LLM_API_KEY="")
    def test_is_configured_false_without_key(self):
        self.assertFalse(llm_service.is_configured())

    @override_settings(MERGE_LLM_API_KEY="k")
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
        with override_settings(MERGE_LLM_API_KEY=""):
            call_command("judge_merge_candidates")
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.llm_checked_at)

    def test_stores_verdict(self):
        verdict = {"same": True, "confidence": 0.9, "reason": "same work"}
        with mock.patch.object(llm_service, "judge", return_value=verdict):
            with override_settings(MERGE_LLM_API_KEY="key", MERGE_LLM_DAILY_LIMIT=20):
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
        with override_settings(MERGE_LLM_API_KEY="key", MERGE_LLM_DAILY_LIMIT=0):
            call_command("judge_merge_candidates")
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.llm_verdict)
