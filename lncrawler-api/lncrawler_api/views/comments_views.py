import uuid

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from ..models.comments_models import Comment, CommentVote
from ..utils.novel_resolution import get_chapter_or_404, get_source_or_404
from ..utils import (
    get_client_ip,
    resolve_novel_slug,
    resolve_author,
    MAX_MESSAGE_LENGTH,
)
from ..serializers.comments_serializers import CommentSerializer, chapter_comment_context

# How many reply levels are loaded under a page's roots. Deeper replies are not shown.
MAX_REPLY_DEPTH = 50


def _load_replies(root_ids):
    """Load the replies under ``root_ids`` one level at a time.

    Returns ``(children, reply_ids)``: a ``parent_id -> [replies]`` map (newest
    first) and the ids of every reply loaded. Each level is one query and the
    walk stops at the first empty level or after ``MAX_REPLY_DEPTH`` levels.
    """
    children = {}
    reply_ids = []
    frontier = list(root_ids)
    for _ in range(MAX_REPLY_DEPTH):
        if not frontier:
            break
        level = list(
            Comment.objects.filter(parent_id__in=frontier)
            .select_related('user')
            .order_by('-created_at')
        )
        for reply in level:
            children.setdefault(reply.parent_id, []).append(reply)
        reply_ids.extend(reply.id for reply in level)
        frontier = [reply.id for reply in level]
    return children, reply_ids


def _serialize_comment(request, comment, **extra_context):
    """Serialize one comment with the labels of the target it was posted on.

    A chapter comment uses the ``chapter`` profile, so its chapter must be
    loaded with its source. ``extra_context`` is merged into the serializer
    context (the thread views pass the reply map and the vote map).
    """
    if comment.chapter_id:
        context = chapter_comment_context(request, comment.chapter)
        profile = 'chapter'
    else:
        context = {'request': request}
        profile = 'novel'
    return CommentSerializer(
        comment, context={**context, **extra_context}, profile=profile
    ).data


def _flag(value):
    """Read a boolean flag from a JSON or form payload.

    JSON booleans are kept as they are. The strings "true" and "1" mean True,
    "false" and "0" mean False (any case). Anything else is False.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1')
    return False


def _validated_comment_input(data, default_spoiler=False):
    """Return ``(message, contains_spoiler)`` from a comment payload.

    The message is stripped, then must be non-empty and at most
    ``MAX_MESSAGE_LENGTH`` characters. Raises ``ValidationError`` otherwise.
    """
    message = data.get('message')
    if not isinstance(message, str) or not message.strip():
        raise ValidationError('Message is required')
    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValidationError(f'Message must be at most {MAX_MESSAGE_LENGTH} characters')
    return message, _flag(data.get('contains_spoiler', default_spoiler))


def _create_comment(novel, *, user, author_name, message, contains_spoiler,
                    ip_address, chapter=None, parent=None):
    """Save a comment on ``chapter`` (or on ``novel`` when there is no chapter)
    and count it on ``novel``."""
    comment = Comment.objects.create(
        novel=novel if chapter is None else None,
        chapter=chapter,
        parent=parent,
        user=user,
        author_name=author_name,
        message=message,
        contains_spoiler=contains_spoiler,
        ip_address=ip_address,
    )
    novel.increment_comment_count()
    return comment


def _threaded_comments_response(request, comments):
    """Serialize every top-level comment with its full reply tree, as a plain list.

    ``comments`` is the base queryset of the target (novel or chapter, replies
    included). Threads are small, so all the roots are loaded and ranked in the
    database without pagination. Their replies are loaded level by level and
    stitched into a ``parent_id -> [children]`` map so the recursive serializer
    never queries. The viewer's votes are fetched in one query for the roots and
    every reply loaded with them.

    ``?ordering=top`` ranks the roots by vote score (then newest first); any
    other value keeps the default newest-first order. Replies are always
    newest first.
    """
    ordering = request.GET.get('ordering', 'new')
    roots = list(
        comments.roots().ranked(ordering).select_related(
            'user', 'chapter__novel_from_source__external_source'
        )
    )
    children, reply_ids = _load_replies([comment.id for comment in roots])

    client_ip = get_client_ip(request)
    user_votes = {}
    if client_ip:
        comment_ids = [comment.id for comment in roots] + reply_ids
        user_votes = dict(
            CommentVote.objects.filter(
                comment_id__in=comment_ids, ip_address=client_ip
            ).values_list('comment_id', 'vote_type')
        )

    return Response([
        _serialize_comment(
            request, comment, comment_children=children, comment_user_votes=user_votes
        )
        for comment in roots
    ])


@api_view(['GET'])
def novel_comments(request, novel_slug):
    """
    Get comments for a specific novel and its chapters
    """
    novel = resolve_novel_slug(novel_slug)
    return _threaded_comments_response(request, Comment.objects.for_novel(novel))

@api_view(['POST'])
def add_comment(request, novel_slug, source_slug=None, chapter_number=None):
    """
    Add a comment to a novel or a chapter.
    If source_slug and chapter_number are provided, it's a chapter comment.
    Otherwise, it's a novel comment. A ``parent_id`` makes it a reply, which
    must belong to the same novel.
    """
    parent_id = request.data.get('parent_id')
    author_name = request.data.get('author_name')

    try:
        user_instance, author_name = resolve_author(request, author_name)
        message, contains_spoiler = _validated_comment_input(request.data)
    except ValidationError as exc:
        return Response(
            {'error': exc.messages[0]},
            status=status.HTTP_400_BAD_REQUEST
        )

    client_ip = get_client_ip(request)
    novel = resolve_novel_slug(novel_slug)

    chapter = None
    parent = None
    # If we are replying to a comment, the reply takes the parent's target
    if parent_id:
        try:
            parent_uuid = uuid.UUID(str(parent_id))
        except ValueError:
            return Response(
                {'error': 'Invalid parent_id'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # The parent's chapter (and its source) is loaded with it so a chapter
        # reply can be serialized with the chapter labels, without extra queries.
        parent = get_object_or_404(
            Comment.objects.select_related('chapter__novel_from_source__external_source'),
            id=parent_uuid,
        )
        parent_novel_id = (
            parent.novel_id or parent.chapter.novel_from_source.novel_id
        )
        # A reply to a comment of another novel is not found on this novel. On
        # the chapter route the parent must also be a comment of this chapter number.
        on_chapter_route = bool(source_slug and chapter_number)
        if parent_novel_id != novel.id or (
            on_chapter_route and (
                parent.chapter_id is None or parent.chapter.chapter_id != chapter_number
            )
        ):
            raise Http404('No comment matches the given query.')
        chapter = parent.chapter
    elif source_slug and chapter_number:
        source = get_source_or_404(novel, source_slug)
        chapter = get_chapter_or_404(source, chapter_number)

    comment_obj = _create_comment(
        novel,
        chapter=chapter,
        parent=parent,
        user=user_instance,
        author_name=author_name,
        message=message,
        contains_spoiler=contains_spoiler,
        ip_address=client_ip,
    )
    # A new comment has no replies and no votes yet, so the thread maps stay empty.
    return Response(
        _serialize_comment(request, comment_obj, comment_children={}, comment_user_votes={}),
        status=status.HTTP_201_CREATED,
    )

@api_view(['GET'])
def chapter_comments(request, novel_slug, source_slug, chapter_number):
    """
    Get comments for a specific chapter across all sources of the novel
    """
    novel = resolve_novel_slug(novel_slug)
    source = get_source_or_404(novel, source_slug)
    get_chapter_or_404(source, chapter_number)

    # Every source of the novel carries its own copy of this chapter number;
    # the commented chapter is shared across them, so one query covers them all.
    return _threaded_comments_response(
        request, Comment.objects.for_chapter_number(novel.id, chapter_number)
    )

@api_view(['POST'])
def vote_comment(request, comment_id):
    """
    Vote on a comment (upvote or downvote).
    """
    comment = get_object_or_404(Comment, id=comment_id)
    vote_type = request.data.get('vote_type')
    client_ip = get_client_ip(request)

    if vote_type not in ['up', 'down']:
        return Response(
            {'error': 'Invalid vote_type. Must be "up" or "down".'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not client_ip:
        return Response(
            {'error': 'Could not identify the voter.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    vote, created = CommentVote.objects.update_or_create(
        comment=comment,
        ip_address=client_ip,
        defaults={'vote_type': vote_type}
    )

    # Re-fetch comment to get updated vote counts
    comment.refresh_from_db()

    return Response({
        'id': str(comment.id),
        'upvotes': comment.upvotes,
        'downvotes': comment.downvotes,
        'vote_score': comment.vote_score
    }, status=status.HTTP_200_OK)

@api_view(['PUT'])
def edit_comment(request, comment_id):
    """
    Edit a comment. Only the comment owner can edit it.
    """
    comment = get_object_or_404(
        Comment.objects.select_related('chapter__novel_from_source__external_source'),
        id=comment_id,
    )

    # Check if user is authenticated and is the comment owner
    if not request.user.is_authenticated:
        return Response({'error': 'You must be logged in to edit a comment'},
                       status=status.HTTP_401_UNAUTHORIZED)

    if comment.user != request.user:
        return Response({'error': 'You can only edit your own comments'},
                       status=status.HTTP_403_FORBIDDEN)

    try:
        message, contains_spoiler = _validated_comment_input(
            request.data, default_spoiler=comment.contains_spoiler
        )
    except ValidationError as exc:
        return Response(
            {'error': exc.messages[0]},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Update comment fields
    comment.message = message
    comment.contains_spoiler = contains_spoiler
    comment.edited = True
    comment.save()

    # Return the updated comment using the appropriate serializer. The thread maps
    # are empty so the subtree is not walked; the frontend keeps its cached replies.
    return Response(
        _serialize_comment(request, comment, comment_children={}, comment_user_votes={}),
        status=status.HTTP_200_OK,
    )
