"""Admin helpers shared by the candidate and LLM admins."""
import json

from django.contrib import messages
from django.utils.html import format_html

from ..services.merge_service import MergeError


def _pretty_json(value):
    if value is None:
        return "-"
    return format_html(
        '<pre style="white-space:pre-wrap">{}</pre>',
        json.dumps(value, indent=2, ensure_ascii=False),
    )


def undo_and_report(modeladmin, request, items, undo, label, noun):
    """Run ``undo`` on each item, reporting every ``MergeError`` and how many were undone.

    A failure is shown as ``"<label(item)>: <error>"``; the summary counts the
    undone items as ``noun``.
    """
    undone = 0
    for item in items:
        try:
            undo(item)
        except MergeError as exc:
            modeladmin.message_user(request, f"{label(item)}: {exc}", messages.ERROR)
        else:
            undone += 1
    modeladmin.message_user(request, f"Undid {undone} {noun}(s).", messages.SUCCESS)
