from django.db import models


class LLMProviderCooldown(models.Model):
    """A provider of the LLM chain that is skipped until ``until`` (429 or outage)."""

    name = models.CharField(max_length=50, unique=True)
    until = models.DateTimeField()
    reason = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
