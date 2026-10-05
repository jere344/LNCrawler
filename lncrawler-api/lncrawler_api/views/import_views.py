"""Endpoints for importing a NovelUpdates XML reading-list export.

Two phases, because matching is interactive:

1. ``parse``  : upload the XML, parse it and return each entry with either a
   matched novel or fuzzy candidates. Writes nothing.
2. ``apply``  : submit the user's resolved entries; creates library bookmarks
   (grouped into folders named after the NU lists) and best-effort progress.
"""

import uuid

from django.db import transaction
from django.db.models import Max
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models.novels_models import Novel
from ..models.sources_models import Chapter, Volume
from ..models.users_models import LibraryFolder, NovelBookmark, ReadingHistory
from ..serializers.novels_serializers import NovelSerializer
from ..services.novelupdates_import_service import (
    MAX_UPLOAD_BYTES,
    folder_name_for,
    match_entries,
    parse_nu_export,
)
from ..utils.query_helpers import apply_novel_prefetches


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def parse_novelupdates_import(request):
    """Parse an uploaded NU export and return entries with match candidates."""
    upload = request.FILES.get("file")
    if upload is None:
        return Response(
            {"error": "No file was uploaded."}, status=status.HTTP_400_BAD_REQUEST
        )
    if upload.size > MAX_UPLOAD_BYTES:
        return Response(
            {"error": "The uploaded file is too large (max 5 MB)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        entries = parse_nu_export(upload.read())
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    match_entries(entries)

    novel_ids = set()
    for entry in entries:
        if entry["novel"] is not None:
            novel_ids.add(entry["novel"].id)
        novel_ids.update(candidate.id for candidate in entry["candidates"])

    novels = apply_novel_prefetches(
        Novel.objects.filter(id__in=novel_ids), request.user
    )
    serialized = NovelSerializer(
        novels, many=True, context={"request": request}
    ).data
    by_id = {str(item["id"]): item for item in serialized}

    payload = []
    for entry in entries:
        payload.append(
            {
                "index": entry["index"],
                "title": entry["title"],
                "list_name": entry["list_name"],
                "folder": folder_name_for(entry["list_name"]),
                "volume": entry["volume"],
                "chapter": entry["chapter"],
                "status": entry["status"],
                "novel": by_id.get(str(entry["novel"].id)) if entry["novel"] else None,
                "candidates": [by_id[str(n.id)] for n in entry["candidates"]],
            }
        )

    return Response({"count": len(payload), "entries": payload})


def _as_int(value):
    try:
        return min(max(0, int(value)), 2**31 - 1)
    except (TypeError, ValueError):
        return 0


def _as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _resolve_chapter(novel, chapter_id, volume_id):
    """Best-effort local Chapter for an NU progress marker, or ``None``."""
    if chapter_id > 0:
        chapter = (
            Chapter.objects.filter(novel_from_source__novel=novel, chapter_id=chapter_id)
            .order_by("novel_from_source_id")
            .first()
        )
        if chapter is not None:
            return chapter

    if volume_id > 0:
        target = (
            Volume.objects.filter(novel_from_source__novel=novel, volume_id=volume_id)
            .exclude(start_chapter__isnull=True)
            .order_by("novel_from_source_id")
            .values_list("start_chapter", flat=True)
            .first()
        )
        if target is None:
            target = (
                Chapter.objects.filter(novel_from_source__novel=novel, volume=volume_id)
                .order_by("chapter_id")
                .values_list("chapter_id", flat=True)
                .first()
            )
        if target is not None:
            return (
                Chapter.objects.filter(novel_from_source__novel=novel, chapter_id=target)
                .order_by("novel_from_source_id")
                .first()
            )
    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def apply_novelupdates_import(request):
    """Create bookmarks/folders/progress from the user's resolved entries."""
    raw_entries = request.data.get("entries")
    if not isinstance(raw_entries, list):
        return Response(
            {"error": "Expected an 'entries' list."}, status=status.HTTP_400_BAD_REQUEST
        )

    wanted_ids = {
        _as_uuid(item.get("novel_id"))
        for item in raw_entries
        if isinstance(item, dict)
    }
    wanted_ids.discard(None)
    novels = {str(n.id): n for n in Novel.objects.filter(id__in=wanted_ids)}

    counters = {
        "bookmarked": 0,
        "already_bookmarked": 0,
        "skipped": 0,
        "progress_set": 0,
        "folders_created": 0,
    }

    with transaction.atomic():
        max_position = NovelBookmark.objects.filter(user=request.user).aggregate(
            max_position=Max("position")
        )["max_position"]
        # ponytail: position is read once then handed out; concurrent applies by
        # the same user can duplicate positions (ordering only). Lock if it matters.
        next_position = (max_position + 1) if max_position is not None else 0

        folders = {}
        for item in raw_entries:
            if not isinstance(item, dict):
                counters["skipped"] += 1
                continue

            novel = novels.get(str(_as_uuid(item.get("novel_id"))))
            if novel is None:
                counters["skipped"] += 1
                continue

            folder = None
            folder_name = (item.get("folder") or "").strip()[:255]
            if folder_name:
                folder = folders.get(folder_name)
                if folder is None:
                    folder, created = LibraryFolder.objects.get_or_create(
                        user=request.user, name=folder_name
                    )
                    if created:
                        counters["folders_created"] += 1
                    folders[folder_name] = folder

            bookmark, created = NovelBookmark.objects.get_or_create(
                user=request.user,
                novel=novel,
                defaults={"position": next_position, "folder": folder},
            )
            if created:
                next_position += 1
                counters["bookmarked"] += 1
            else:
                counters["already_bookmarked"] += 1

            chapter_id = _as_int(item.get("chapter"))
            volume_id = _as_int(item.get("volume"))
            if chapter_id or volume_id:
                chapter = _resolve_chapter(novel, chapter_id, volume_id)
                if chapter is not None:
                    existing = (
                        ReadingHistory.objects.filter(user=request.user, novel=novel)
                        .select_related("last_read_chapter")
                        .first()
                    )
                    current = (
                        existing.last_read_chapter.chapter_id
                        if existing and existing.last_read_chapter
                        else None
                    )
                    # Best-effort: never move a user's progress backwards.
                    if current is None or chapter.chapter_id > current:
                        ReadingHistory.objects.update_or_create(
                            user=request.user,
                            novel=novel,
                            defaults={
                                "source": chapter.novel_from_source,
                                "last_read_chapter": chapter,
                            },
                        )
                        counters["progress_set"] += 1

    return Response(counters)
