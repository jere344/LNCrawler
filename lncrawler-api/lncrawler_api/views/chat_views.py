from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from ..models.chat_models import ChatMessage
from ..utils import get_client_ip, resolve_author, MAX_MESSAGE_LENGTH
from ..utils.pagination import paginated_response
from ..serializers.chat_serializers import ChatMessageSerializer


@api_view(['GET'])
def list_chat(request):
    """List chat messages, newest first. Envelope: {count, total_pages, current_page, results}."""
    messages = ChatMessage.objects.select_related('parent', 'user')
    return paginated_response(
        request, messages, ChatMessageSerializer, default_size=100, max_size=100
    )


@api_view(['POST'])
def add_chat_message(request):
    """Post a chat message, optionally as a reply to an existing one."""
    parent_id = request.data.get('parent_id')
    message = request.data.get('message')
    author_name = request.data.get('author_name')
    contains_spoiler = bool(request.data.get('contains_spoiler', False))

    try:
        user_instance, author_name = resolve_author(request, author_name)
    except ValidationError as exc:
        return Response({'error': exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(message, str):
        message = message.strip()

    if not message:
        return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(message, str) or len(message) > MAX_MESSAGE_LENGTH:
        return Response(
            {'error': f'Message must be at most {MAX_MESSAGE_LENGTH} characters'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    parent = None
    if parent_id:
        try:
            parent = ChatMessage.objects.get(id=parent_id)
        except (ChatMessage.DoesNotExist, ValidationError, ValueError):
            return Response(
                {'error': 'Parent message not found'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    chat_message = ChatMessage.objects.create(
        user=user_instance,
        author_name=author_name,
        message=message,
        contains_spoiler=contains_spoiler,
        ip_address=get_client_ip(request),
        parent=parent,
    )

    serializer = ChatMessageSerializer(chat_message, context={'request': request})
    return Response(serializer.data, status=status.HTTP_201_CREATED)
