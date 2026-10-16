from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ..models import Chapter
from ..models.comments_models import Comment, CommentVote
from ..utils import (
    get_client_ip,
    resolve_novel_slug,
    resolve_author,
    MAX_MESSAGE_LENGTH,
)
from ..utils.pagination import parse_page_size
from ..serializers.comments_serializers import CommentSerializer, chapter_comment_context


def _threaded_comments_response(request, root_comments, reply_comments):
    """Serialize a page of top-level comments with their reply trees.

    The whole thread is loaded up front (roots + every descendant) and the
    replies are stitched into a ``parent_id -> [children]`` map, so the
    recursive serializer never fires a query. The viewer's votes for every
    comment in the thread are fetched in one query and shared through the
    context. Pagination happens before serialization, so only the roots on the
    requested page (and their replies) are rendered.
    """
    root_comments.sort(key=lambda comment: comment.created_at, reverse=True)
    paginator = Paginator(root_comments, parse_page_size(request, 20, 50))
    page_obj = paginator.get_page(request.GET.get('page', 1))
    page_roots = list(page_obj.object_list)

    children = {}
    for reply in reply_comments:
        children.setdefault(reply.parent_id, []).append(reply)
    for bucket in children.values():
        bucket.sort(key=lambda comment: comment.created_at, reverse=True)

    client_ip = get_client_ip(request)
    user_votes = {}
    if client_ip:
        comment_ids = [comment.id for comment in page_roots] + [
            reply.id for reply in reply_comments
        ]
        user_votes = dict(
            CommentVote.objects.filter(
                comment_id__in=comment_ids, ip_address=client_ip
            ).values_list('comment_id', 'vote_type')
        )

    data = []
    for comment in page_roots:
        if comment.chapter_id:
            context = chapter_comment_context(request, comment.chapter)
            profile = 'chapter'
        else:
            context = {'request': request}
            profile = 'novel'
        context = {**context, 'comment_children': children, 'comment_user_votes': user_votes}
        data.append(CommentSerializer(comment, context=context, profile=profile).data)
    return Response(data)


@api_view(['GET'])
def novel_comments(request, novel_slug):
    """
    Get comments for a specific novel and its chapters
    """
    novel = resolve_novel_slug(novel_slug)

    # A comment targets either the novel or one of its chapters; load both
    # kinds (roots and replies) in two queries and build the tree in Python.
    roots = list(
        Comment.objects.filter(
            Q(novel=novel) | Q(chapter__novel_from_source__novel=novel), parent=None
        ).select_related('user', 'chapter__novel_from_source__external_source')
    )
    replies = list(
        Comment.objects.filter(
            Q(novel=novel) | Q(chapter__novel_from_source__novel=novel),
            parent__isnull=False,
        ).select_related('user')
    )
    return _threaded_comments_response(request, roots, replies)

@api_view(['POST'])
def add_comment(request, novel_slug, source_slug=None, chapter_number=None):
    """
    Add a comment to a novel or a chapter.
    If source_slug and chapter_number are provided, it's a chapter comment.
    Otherwise, it's a novel comment.
    """
    parent_id = request.data.get('parent_id')
    message = request.data.get('message')
    author_name = request.data.get('author_name')
    contains_spoiler = bool(request.data.get('contains_spoiler', False))
    
    try:
        user_instance, author_name = resolve_author(request, author_name)
    except ValidationError as exc:
        return Response(
            {'error': exc.messages[0]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if isinstance(message, str):
        message = message.strip()

    if not message:
        return Response(
            {'error': 'Message is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not isinstance(message, str) or len(message) > MAX_MESSAGE_LENGTH:
        return Response(
            {'error': f'Message must be at most {MAX_MESSAGE_LENGTH} characters'},
            status=status.HTTP_400_BAD_REQUEST
        )

    client_ip = get_client_ip(request)
    novel = resolve_novel_slug(novel_slug)

    # If we are replying to a comment, use the parent comment data
    if parent_id:
        try:
            parent_comment_obj = get_object_or_404(Comment, id=parent_id)
            comment_obj = Comment.objects.create(
                novel=parent_comment_obj.novel,
                chapter=parent_comment_obj.chapter,
                user=user_instance,
                author_name=author_name,
                message=message,
                contains_spoiler=contains_spoiler,
                ip_address=client_ip,
                parent=parent_comment_obj
            )
            
            # Increment comment count for the novel
            novel.increment_comment_count()

            serializer = CommentSerializer(comment_obj, context={'request': request}, profile='novel')
            response_data = serializer.data

        except Comment.DoesNotExist:
            return Response(
                {'error': 'Parent comment not found for this novel'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # else we have to check for the novel and chapter
    else:
        if source_slug and chapter_number: # Chapter comment
            source = get_object_or_404(novel.sources, source_slug=source_slug)
            chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)
            comment_obj = Comment.objects.create(
                chapter=chapter,
                user=user_instance,
                author_name=author_name,
                message=message,
                contains_spoiler=contains_spoiler,
                ip_address=client_ip
            )
            
            # Increment comment count for the novel
            novel.increment_comment_count()
            
            serializer = CommentSerializer(
                comment_obj, context=chapter_comment_context(request, chapter), profile='chapter'
            )
        else: # Novel comment
            comment_obj = Comment.objects.create(
                novel=novel,
                user=user_instance,
                author_name=author_name,
                message=message,
                contains_spoiler=contains_spoiler,
                ip_address=client_ip
            )
            
            # Increment comment count for the novel
            novel.increment_comment_count()
            
            serializer = CommentSerializer(comment_obj, context={'request': request}, profile='novel')
        response_data = serializer.data

        
    return Response(response_data, status=status.HTTP_201_CREATED)

@api_view(['GET'])
def chapter_comments(request, novel_slug, source_slug, chapter_number):
    """
    Get comments for a specific chapter across all sources of the novel
    """
    novel = resolve_novel_slug(novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    get_object_or_404(source.chapters, chapter_id=chapter_number)

    # Every source of the novel carries its own copy of this chapter number;
    # the commented chapter is shared across them, so gather them all at once
    # instead of querying each source's chapter in a loop.
    chapters = list(
        Chapter.objects.filter(
            novel_from_source__novel=novel, chapter_id=chapter_number
        ).select_related('novel_from_source__external_source')
    )
    roots = list(
        Comment.objects.filter(chapter__in=chapters, parent=None).select_related(
            'user', 'chapter__novel_from_source__external_source'
        )
    )
    replies = list(
        Comment.objects.filter(
            chapter__in=chapters, parent__isnull=False
        ).select_related('user')
    )
    return _threaded_comments_response(request, roots, replies)

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
    comment = get_object_or_404(Comment, id=comment_id)
    
    # Check if user is authenticated and is the comment owner
    if not request.user.is_authenticated:
        return Response({'error': 'You must be logged in to edit a comment'}, 
                       status=status.HTTP_401_UNAUTHORIZED)
    
    if comment.user != request.user:
        return Response({'error': 'You can only edit your own comments'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    message = request.data.get('message')
    contains_spoiler = request.data.get('contains_spoiler', comment.contains_spoiler)
    
    if not message:
        return Response({'error': 'Message is required'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    # Update comment fields
    comment.message = message
    comment.contains_spoiler = contains_spoiler
    comment.edited = True
    comment.save()
    
    # Return the updated comment using the appropriate serializer
    if comment.chapter:
        serializer = CommentSerializer(
            comment, context=chapter_comment_context(request, comment.chapter), profile='chapter'
        )
    else:
        serializer = CommentSerializer(comment, context={'request': request}, profile='novel')
    
    return Response(serializer.data, status=status.HTTP_200_OK)
