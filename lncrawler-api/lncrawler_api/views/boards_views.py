from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from ..models.boards_models import Board
from ..models.comments_models import Comment
from ..utils import get_client_ip
from ..serializers.boards_serializers import BoardSerializer, BoardCommentSerializer

@api_view(['GET'])
def list_boards(request):
    """
    Get list of all active boards
    """
    boards = Board.objects.filter(is_active=True)
    serializer = BoardSerializer(boards, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def board_detail(request, board_slug):
    """
    Get details of a specific board
    """
    board = get_object_or_404(Board, slug=board_slug, is_active=True)
    serializer = BoardSerializer(board)
    return Response(serializer.data)

@api_view(['GET'])
def board_comments(request, board_slug):
    """
    Get comments for a specific board
    """
    board = get_object_or_404(Board, slug=board_slug, is_active=True)
    
    # Get top-level comments for this board (no parent)
    comments = board.comments.filter(parent=None)
    
    serializer = BoardCommentSerializer(
        comments, 
        many=True, 
        context={
            'request': request,
            'board_name': board.name,
            'board_slug': board.slug
        })
    
    return Response(serializer.data)

@api_view(['POST'])
def add_board_comment(request, board_slug):
    """
    Add a comment to a board
    """
    board = get_object_or_404(Board, slug=board_slug, is_active=True)
    
    parent_id = request.data.get('parent_id')
    user_instance = request.user if request.user.is_authenticated else None
    message = request.data.get('message')
    author_name = request.data.get('author_name')
    contains_spoiler = request.data.get('contains_spoiler', False)
    
    if not author_name or not message:
        return Response(
            {'error': 'Author name (if anonymous) and message are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    client_ip = get_client_ip(request)

    # If we are replying to a comment, use the parent comment data
    if parent_id:
        try:
            parent_comment_obj = get_object_or_404(Comment, id=parent_id, board=board)
            comment_obj = Comment.objects.create(
                board=board,
                user=user_instance,
                author_name=author_name,
                message=message,
                contains_spoiler=contains_spoiler,
                ip_address=client_ip,
                parent=parent_comment_obj
            )
        except Comment.DoesNotExist:
            return Response(
                {'error': 'Parent comment not found for this board'},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        # Top-level board comment
        comment_obj = Comment.objects.create(
            board=board,
            user=user_instance,
            author_name=author_name,
            message=message,
            contains_spoiler=contains_spoiler,
            ip_address=client_ip
        )
    
    # Increment comment count for the board
    board.increment_comment_count()
    
    serializer = BoardCommentSerializer(comment_obj, context={
        'request': request,
        'board_name': board.name,
        'board_slug': board.slug
    })
    
    return Response(serializer.data, status=status.HTTP_201_CREATED)
