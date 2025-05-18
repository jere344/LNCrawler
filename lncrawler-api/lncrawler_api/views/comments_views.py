from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from ..models import Novel, Chapter
from ..models.comments_models import Comment, CommentVote
from ..utils import get_client_ip
from auth_app.serializers import OtherUserSerializer


def get_comment_with_replies(comment, request, from_other_source=False, source_name=None, type=None, chapter_title=None, chapter_id=None, source_slug=None):
    """
    Recursively get a comment and all its replies in a nested structure
    """
    result = {
        'id': str(comment.id),
        'author_name': comment.author_name,
        'message': comment.message,
        'contains_spoiler': comment.contains_spoiler,
        'created_at': comment.created_at,
        'from_other_source': from_other_source,
        'has_replies': comment.replies.exists(),
        'upvotes': comment.upvotes,
        'downvotes': comment.downvotes,
        'vote_score': comment.vote_score,
        'replies': []
    }
    
    if comment.user: 
        serializer = OtherUserSerializer(comment.user, context={'request': request})
        result['user'] = serializer.data
    
    # Add optional fields if they exist
    if source_name:
        result['source_name'] = source_name
    if type:
        result['type'] = type
    if chapter_title:
        result['chapter_title'] = chapter_title
    if chapter_id is not None:
        result['chapter_id'] = chapter_id
    if source_slug:
        result['source_slug'] = source_slug
    
    # Get all replies to this comment
    for reply in comment.replies.all().order_by('created_at'):
        result['replies'].append(get_comment_with_replies(
            reply,
            request,
            from_other_source=from_other_source,
            source_name=source_name,
            type=type,
            chapter_title=chapter_title,
            chapter_id=chapter_id,
            source_slug=source_slug
        ))
    
    return result

@api_view(['GET'])
def novel_comments(request, novel_slug):
    """
    Get comments for a specific novel and its chapters
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    
    # Get top-level comments directly on the novel (no parent)
    novel_comments = novel.comments.filter(parent=None)
    
    # Get chapter IDs for comments on chapters
    chapter_ids = []
    for source in novel.sources.all():
        chapter_ids.extend(source.chapters.values_list('id', flat=True))
    
    # Get top-level comments on chapters (no parent)
    chapter_comments = Comment.objects.filter(chapter_id__in=chapter_ids, parent=None)
    
    # Process novel comments with their replies
    novel_comments_data = []
    for comment in novel_comments:
        comment_data = get_comment_with_replies(comment, request, type='novel')
        novel_comments_data.append(comment_data)
    
    # Process chapter comments with their replies
    chapter_comments_data = []
    for comment in chapter_comments:
        chapter = comment.chapter
        source = chapter.novel_from_source
        
        comment_data = get_comment_with_replies(
            comment,
            request,
            type='chapter',
            chapter_title=chapter.title,
            chapter_id=chapter.chapter_id,
            source_name=source.source_name,
            source_slug=source.source_slug
        )
        chapter_comments_data.append(comment_data)
    
    # Combine and sort by creation date
    all_comments = novel_comments_data + chapter_comments_data
    all_comments.sort(key=lambda x: x['created_at'], reverse=True)
    
    return Response(all_comments)

@api_view(['POST'])
def add_comment(request, novel_slug, source_slug=None, chapter_number=None):
    """
    Add a comment to a novel or a chapter.
    If source_slug and chapter_number are provided, it's a chapter comment.
    Otherwise, it's a novel comment.
    """
    message = request.data.get('message')
    contains_spoiler = request.data.get('contains_spoiler', False)
    parent_id = request.data.get('parent_id')

    user_instance = None
    author_name_to_save = None

    if request.user.is_authenticated:
        user_instance = request.user
        author_name_to_save = request.user.username
    else:
        author_name_to_save = request.data.get('author_name')

    if not author_name_to_save or not message:
        return Response(
            {'error': 'Author name (if anonymous) and message are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    novel = get_object_or_404(Novel, slug=novel_slug)
    client_ip = get_client_ip(request)
    
    parent_comment_obj = None
    comment_obj = None
    comment_data_for_response = {}

    if source_slug and chapter_number is not None:
        # Chapter comment
        source = get_object_or_404(novel.sources, source_slug=source_slug)
        chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)
        
        if parent_id:
            try:
                parent_comment_obj = Comment.objects.get(id=parent_id, chapter=chapter)
            except Comment.DoesNotExist:
                return Response(
                    {'error': 'Parent comment not found for this chapter'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        comment_obj = Comment.objects.create(
            chapter=chapter,
            user=user_instance,
            author_name=author_name_to_save,
            message=message,
            contains_spoiler=contains_spoiler,
            ip_address=client_ip,
            parent=parent_comment_obj
        )
        comment_data_for_response = get_comment_with_replies(comment_obj, request)
    else:
        # Novel comment
        if parent_id:
            try:
                parent_comment_obj = Comment.objects.get(id=parent_id, novel=novel)
            except Comment.DoesNotExist:
                return Response(
                    {'error': 'Parent comment not found for this novel'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        comment_obj = Comment.objects.create(
            novel=novel,
            user=user_instance,
            author_name=author_name_to_save,
            message=message,
            contains_spoiler=contains_spoiler,
            ip_address=client_ip,
            parent=parent_comment_obj
        )
        comment_data_for_response = get_comment_with_replies(comment_obj, request, type='novel')

    return Response(comment_data_for_response, status=status.HTTP_201_CREATED)

@api_view(['GET'])
def chapter_comments(request, novel_slug, source_slug, chapter_number):
    """
    Get comments for a specific chapter across all sources of the novel
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)
    
    # Get top-level comments for this specific chapter (no parent)
    specific_comments = chapter.comments.filter(parent=None)
    
    # Get comments for the same chapter number but from different sources
    other_source_comments = []
    for other_source in novel.sources.exclude(id=source.id):
        try:
            other_chapter = other_source.chapters.get(chapter_id=chapter_number)
            other_comments = other_chapter.comments.filter(parent=None)
            
            for comment in other_comments:
                comment_data = get_comment_with_replies(
                    comment,
                    request,
                    from_other_source=True,
                    source_name=other_source.source_name
                )
                other_source_comments.append(comment_data)
        except Chapter.DoesNotExist:
            continue
    
    # Process specific chapter comments with their replies
    specific_comments_data = []
    for comment in specific_comments:
        comment_data = get_comment_with_replies(comment, request)
        specific_comments_data.append(comment_data)
    
    # Combine all comments and sort by creation date
    all_comments = specific_comments_data + other_source_comments
    all_comments.sort(key=lambda x: x['created_at'], reverse=True)
    
    return Response(all_comments)

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
