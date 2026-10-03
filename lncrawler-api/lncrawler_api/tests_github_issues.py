"""Tests for GitHub issue reporting of unexpected errors."""

import json
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
        self.assertEqual(post.call_args.kwargs["json"]["title"], "title")

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
