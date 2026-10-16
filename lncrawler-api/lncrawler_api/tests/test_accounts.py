"""Tests for account and password flows."""

import json
import re

from django.contrib.auth import get_user_model

from django.test import TestCase, override_settings

from django.urls import reverse


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ForgotPasswordEmailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="resetuser", email="reset@example.com", password="pw12345!"
        )

    def test_forgot_password_sends_reset_link(self):
        from django.core import mail

        from auth_app.models import PasswordResetToken

        response = self.client.post(
            reverse("forgot_password"),
            data=json.dumps({"email": self.user.email}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])

        token = PasswordResetToken.objects.get(user=self.user)
        # Only the hash is stored; the email carries the raw token, so verify
        # the emailed link hashes back to the stored row.
        raw = re.search(r"token=([\w\-]+)", message.body).group(1)
        self.assertEqual(PasswordResetToken.hash_token(raw), token.token)
        html = next(content for content, mime in message.alternatives if mime == "text/html")
        self.assertIn(raw, html)
