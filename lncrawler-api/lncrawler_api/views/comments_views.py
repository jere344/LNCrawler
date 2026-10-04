from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ..models import Novel, Chapter
from ..models.comments_models import Comment, CommentVote
from ..utils import get_client_ip, resolve_novel_slug
from ..utils.pagination import parse_page_size
from ..serializers.comments_serializers import (
    NovelCommentSerializer, ChapterCommentSerializer, chapter_comment_context,
)
from ..serializers.boards_serializers import BoardCommentSerializer, board_comment_context


MAX_AUTHOR_NAME_LENGTH = 100
MAX_MESSAGE_LENGTH = 10000


@api_view(['GET'])
def novel_comments(request, novel_slug):
    """
    Get comments for a specific novel and its chapters
    """
    novel = resolve_novel_slug(novel_slug)
    
    # Get top-level comments directly on the novel (no parent)
    novel_comments = novel.comments.filter(parent=None)
    
    # Get top-level comments on any chapter of this novel (no parent)
    chapter_comments = Comment.objects.filter(
        chapter__novel_from_source__novel=novel, parent=None
    ).select_related('chapter__novel_from_source__external_source')
    
    # Process novel comments with their replies
    novel_comments_serializer = NovelCommentSerializer(novel_comments, many=True, context={'request': request})
    novel_comments_data = novel_comments_serializer.data
    
    # Process chapter comments with their replies
    chapter_comments_data = []
    for comment in chapter_comments:
        serializer = ChapterCommentSerializer(
            comment, context=chapter_comment_context(request, comment.chapter)
        )
        chapter_comments_data.append(serializer.data)
    
    # Combine and sort by creation date
    all_comments = novel_comments_data + chapter_comments_data
    all_comments.sort(key=lambda x: x['created_at'], reverse=True)

    # Frontend consumes a plain list; paginate top-level comments while keeping replies attached.
    paginator = Paginator(all_comments, parse_page_size(request, 20, 50))
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return Response(page_obj.object_list)

@api_view(['POST'])
def add_comment(request, novel_slug, source_slug=None, chapter_number=None):
    """
    Add a comment to a novel or a chapter.
    If source_slug and chapter_number are provided, it's a chapter comment.
    Otherwise, it's a novel comment.
    """
    parent_id = request.data.get('parent_id')
    user_instance = request.user if request.user.is_authenticated else None
    message = request.data.get('message')
    author_name = request.data.get('author_name')
    contains_spoiler = request.data.get('contains_spoiler', False)
    
    if isinstance(author_name, str):
        author_name = author_name.strip()
    if isinstance(message, str):
        message = message.strip()

    if not message:
        return Response(
            {'error': 'Message is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not author_name:
        if user_instance:
            author_name = user_instance.username
        else:
            return Response(
                {'error': 'Author name is required for anonymous comments'},
                status=status.HTTP_400_BAD_REQUEST
            )

    if not isinstance(author_name, str) or len(author_name) > MAX_AUTHOR_NAME_LENGTH:
        return Response(
            {'error': f'Author name must be at most {MAX_AUTHOR_NAME_LENGTH} characters'},
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

            serializer = NovelCommentSerializer(comment_obj, context={'request': request})
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
            
            serializer = ChapterCommentSerializer(
                comment_obj, context=chapter_comment_context(request, chapter)
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
            
            serializer = NovelCommentSerializer(comment_obj, context={'request': request})
        response_data = serializer.data

        
    return Response(response_data, status=status.HTTP_201_CREATED)

@api_view(['GET'])
def chapter_comments(request, novel_slug, source_slug, chapter_number):
    """
    Get comments for a specific chapter across all sources of the novel
    """
    novel = resolve_novel_slug(novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)
    
    # Get top-level comments for this specific chapter (no parent)
    specific_comments = chapter.comments.filter(parent=None)
    
    
    specific_comments_serializer = ChapterCommentSerializer(
        specific_comments,
        many=True,
        context=chapter_comment_context(request, chapter),
    )
    specific_comments_data = specific_comments_serializer.data
    
    # Get comments for the same chapter number but from different sources
    other_source_comments_data = []
    for other_source in novel.sources.exclude(id=source.id):
        try:
            other_chapter = other_source.chapters.get(chapter_id=chapter_number)
            other_comments = other_chapter.comments.filter(parent=None)
            
            serializer = ChapterCommentSerializer(
                other_comments,
                many=True,
                context=chapter_comment_context(request, other_chapter),
            )
            for comment_data in serializer.data:
                other_source_comments_data.append(comment_data)
                
        except Chapter.DoesNotExist:
            continue
    
    # Combine all comments and sort by creation date
    all_comments = specific_comments_data + other_source_comments_data
    all_comments.sort(key=lambda x: x['created_at'], reverse=True)

    # Frontend consumes a plain list; paginate top-level comments while keeping replies attached.
    paginator = Paginator(all_comments, parse_page_size(request, 20, 50))
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return Response(page_obj.object_list)

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
        serializer = ChapterCommentSerializer(
            comment, context=chapter_comment_context(request, comment.chapter)
        )
    elif comment.board:
        serializer = BoardCommentSerializer(
            comment, context=board_comment_context(request, comment.board)
        )
    else:
        serializer = NovelCommentSerializer(comment, context={'request': request})
    
    return Response(serializer.data, status=status.HTTP_200_OK)
