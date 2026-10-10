"""Tests for GitHub issue reporting of unexpected errors."""

import json
import os
import tempfile
from unittest import mock

from django.test import TestCase, override_settings

from api_project import github_issues


def _resp(status_code, payload=None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = ""
    resp.json.return_value = payload or {}
    return resp


@override_settings(
    GITHUB_ISSUES_ENABLED=True,
    GITHUB_REPO="owner/repo",
    GITHUB_TOKEN="token",
    ISSUE_REPORTS_TO_DISK=False,
)
class CreateIssueTests(TestCase):
    def setUp(self):
        # The per-process TTL dedup cache must not leak between tests.
        github_issues._recent.clear()
        self.addCleanup(github_issues._recent.clear)

    @mock.patch("api_project.github_issues.requests.post")
    @mock.patch("api_project.github_issues.requests.get")
    def test_creates_issue_when_no_open_issue(self, get, post):
        get.return_value = _resp(200, {"total_count": 0})
        post.return_value = _resp(201, {"number": 1})

        github_issues.create_issue("title", "body", "abc123")

        post.assert_called_once()
        # The fingerprint is appended so dedup survives restarts.
        self.assertEqual(post.call_args.kwargs["json"]["title"], "title (abc123)")

    @mock.patch("api_project.github_issues.requests.post")
    @mock.patch("api_project.github_issues.requests.get")
    def test_skips_when_open_issue_exists(self, get, post):
        get.return_value = _resp(200, {"total_count": 1})

        github_issues.create_issue("title", "body", "abc123")

        post.assert_not_called()

    @mock.patch("api_project.github_issues.requests.post")
    @mock.patch("api_project.github_issues.requests.get")
    def test_dedups_repeat_in_same_process(self, get, post):
        get.return_value = _resp(200, {"total_count": 0})
        post.return_value = _resp(201, {})

        github_issues.create_issue("title", "body", "abc123")
        github_issues.create_issue("title", "body", "abc123")

        post.assert_called_once()

    @mock.patch("api_project.github_issues.requests.post")
    @mock.patch("api_project.github_issues.requests.get")
    def test_search_failure_does_not_create(self, get, post):
        # Fail closed: if we cannot check for an existing issue, don't risk a dupe.
        get.return_value = _resp(500)

        github_issues.create_issue("title", "body", "abc123")

        post.assert_not_called()


@override_settings(
    GITHUB_ISSUES_ENABLED=False,
    GITHUB_REPO="",
    GITHUB_TOKEN="",
)
class DisabledTests(TestCase):
    @mock.patch("api_project.github_issues.requests.get")
    @mock.patch("api_project.github_issues.requests.post")
    def test_noop_when_disabled(self, post, get):
        github_issues.create_issue("title", "body", "abc123")

        get.assert_not_called()
        post.assert_not_called()


@override_settings(ISSUE_REPORTS_TO_DISK=True)
class DiskReportTests(TestCase):
    def test_writes_one_file_per_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            with override_settings(ISSUE_REPORTS_DIR=d):
                github_issues.create_issue("title", "body", "abc123")
                github_issues.create_issue("title", "body", "abc123")
            self.assertEqual(os.listdir(d), ["abc123.md"])

    @mock.patch("api_project.github_issues.requests.post")
    @mock.patch("api_project.github_issues.requests.get")
    def test_disk_mode_never_calls_github(self, get, post):
        with tempfile.TemporaryDirectory() as d:
            with override_settings(ISSUE_REPORTS_DIR=d):
                github_issues.create_issue("title", "body", "abc123")

        get.assert_not_called()
        post.assert_not_called()


@override_settings(GITHUB_ISSUES_ENABLED=False)
class ReportErrorEndpointTests(TestCase):
    def test_accepts_json_payload(self):
        resp = self.client.post(
            "/report-error/",
            data=json.dumps(
                {"message": "boom", "stack": "at x", "url": "/novels/1"}
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_rejects_get(self):
        self.assertEqual(self.client.get("/report-error/").status_code, 405)

    def test_ignores_extension_origin_stack(self):
        resp = self.client.post(
            "/report-error/",
            data=json.dumps(
                {
                    "message": "Cannot read properties of undefined (reading 'M_ID')",
                    "stack": (
                        "TypeError: Cannot read properties of undefined (reading 'M_ID')\n"
                        "    at Y (chrome-extension://abc/executors/200.js:1:761)\n"
                        "    at E (chrome-extension://abc/executors/200.js:1:1442)"
                    ),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.json(), {"detail": "ignored"})

    def test_keeps_app_error_with_extension_string_below_top_frame(self):
        with self.assertLogs("frontend", level="ERROR"):
            resp = self.client.post(
                "/report-error/",
                data=json.dumps(
                    {
                        "message": "real app error",
                        "stack": (
                            "Error: real app error\n"
                            "    at App (https://lncrawler.monster/assets/app.js:1:1)\n"
                            "    at chrome-extension://abc/hook.js:1:1"
                        ),
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(resp.json(), {"detail": "ok"})


@override_settings(GITHUB_ISSUES_ENABLED=False, ISSUE_REPORTS_TO_DISK=False)
class FrontendFingerprintTests(TestCase):
    """The endpoint's fingerprint must distinguish routes: the message alone is
    identical ("Request failed with status code 500") for every failing
    request, so it cannot be the only input."""

    def _fingerprint(self, context):
        with self.assertLogs("frontend", level="ERROR") as cm:
            resp = self.client.post(
                "/report-error/",
                data=json.dumps(
                    {
                        "message": "Request failed with status code 500",
                        "context": context,
                        "url": "http://api/whatever",
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        return cm.records[-1].github_fingerprint

    def test_different_endpoints_get_different_fingerprints(self):
        a = self._fingerprint("GET /novels/1")
        b = self._fingerprint("GET /users/2")
        self.assertNotEqual(a, b)

    def test_same_endpoint_is_stable(self):
        a = self._fingerprint("GET /novels/1")
        b = self._fingerprint("GET /novels/1")
        self.assertEqual(a, b)


class DiskReportDedupLogTests(TestCase):
    @override_settings(ISSUE_REPORTS_TO_DISK=True)
    def test_duplicate_is_logged(self):
        with tempfile.TemporaryDirectory() as d:
            with override_settings(ISSUE_REPORTS_DIR=d):
                github_issues.create_issue("t", "b", "abc123")
                with self.assertLogs("lncrawler_api", level="INFO") as cm:
                    github_issues.create_issue("t", "b", "abc123")
        self.assertTrue(
            any("duplicate" in r.getMessage().lower() for r in cm.records)
        )


class HandlerForkTests(TestCase):
    """gunicorn runs with preload_app=True: the handler is built in the master
    and then forked, but threads do not survive fork. Each worker must start
    its own drain thread or every API-side report is silently dropped."""

    @mock.patch("api_project.logging_handlers.threading.Thread")
    @mock.patch("api_project.logging_handlers.os.getpid")
    def test_drain_thread_restarts_after_fork(self, getpid, thread):
        from api_project.logging_handlers import GitHubIssueHandler

        handler = GitHubIssueHandler()

        getpid.return_value = 1000
        handler._ensure_drain()
        handler._ensure_drain()  # idempotent within one process
        self.assertEqual(thread.call_count, 1)

        getpid.return_value = 2000  # simulating the forked worker
        handler._ensure_drain()
        self.assertEqual(thread.call_count, 2)

        # A drain thread that died must be re-armed, not trusted forever.
        handler._drain_thread.is_alive.return_value = False
        handler._ensure_drain()
        self.assertEqual(thread.call_count, 3)

