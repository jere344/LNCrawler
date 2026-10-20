"""Admin actions shared by the tag and author merge admins."""
from django.contrib import messages

from ..services.merge_service import MergeError


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
