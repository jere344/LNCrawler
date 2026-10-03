from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.db import transaction

from ..models.users_models import ReadingList, ReadingListItem, ReadingListCollaborator
from ..models.novels_models import Novel
from ..serializers import (
    ReadingListSerializer,
    DetailedReadingListSerializer,
    ReadingListItemSerializer,
    ReadingListCollaboratorSerializer,
    get_reading_list_role,
)

User = get_user_model()


def _forbidden(detail):
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


def _paginated_response(request, query_set, serializer_class):
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)
    paginator = Paginator(query_set, page_size)
    page_obj = paginator.get_page(page_number)
    serializer = serializer_class(page_obj, many=True, context={"request": request})
    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": int(page_number),
        "results": serializer.data,
    })


@api_view(["GET"])
def list_all_reading_lists(request):
    """
    List all public reading lists, with optional title/description search.
    """
    search = request.GET.get("search", "")

    query_set = ReadingList.objects.filter(is_public=True)

    if search:
        query_set = query_set.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search)
        )

    query_set = query_set.order_by('-updated_at')
    return _paginated_response(request, query_set, ReadingListSerializer)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_reading_lists(request):
    """
    Get all reading lists the current user can edit or read: their own lists
    plus lists shared with them as editor or reader.
    """
    query_set = ReadingList.objects.filter(
        Q(user=request.user) | Q(collaborators__user=request.user)
    ).distinct().order_by('-updated_at')

    return _paginated_response(request, query_set, ReadingListSerializer)


@api_view(["GET"])
def reading_list_detail(request, list_id):
    """
    Get details of a specific reading list including all its items.
    Private lists are only visible to their owner and collaborators.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    if not reading_list.is_public and get_reading_list_role(reading_list, request.user) is None:
        return _forbidden("You do not have access to this reading list.")

    serializer = DetailedReadingListSerializer(reading_list, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_reading_list(request):
    """
    Create a new reading list.
    """
    serializer = ReadingListSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_reading_list(request, list_id):
    """
    Update a reading list's title and description. Editors and the owner can
    edit metadata; only the owner can change visibility.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    role = get_reading_list_role(reading_list, request.user)

    if role not in ('owner', 'editor'):
        return _forbidden("You do not have permission to edit this reading list.")

    if 'is_public' in request.data and role != 'owner':
        return _forbidden("Only the owner can change a list's visibility.")

    serializer = ReadingListSerializer(
        reading_list, data=request.data, partial=True, context={"request": request}
    )
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_reading_list(request, list_id):
    """
    Delete a reading list. Only the creator can delete the list.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)

    if get_reading_list_role(reading_list, request.user) != 'owner':
        return _forbidden("You do not have permission to delete this reading list.")

    reading_list.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_novel_to_list(request, list_id):
    """
    Add a novel to a reading list. The owner and editors can add items.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)

    if get_reading_list_role(reading_list, request.user) not in ('owner', 'editor'):
        return _forbidden("You do not have permission to modify this reading list.")

    # Find the highest position and increment by 1 for new item
    highest_position = ReadingListItem.objects.filter(reading_list=reading_list).order_by('-position').first()
    next_position = (highest_position.position + 1) if highest_position else 0
    data = request.data.copy()
    data['position'] = next_position

    serializer = ReadingListItemSerializer(data=data)
    if serializer.is_valid():
        # Get novel to ensure it exists
        novel_id = serializer.validated_data['novel_id']
        get_object_or_404(Novel, id=novel_id)

        # Create the item
        item = serializer.save(reading_list=reading_list)

        # Return the item with the novel details
        return_serializer = ReadingListItemSerializer(item)
        return Response(return_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_list_item(request, list_id, item_id):
    """
    Update a novel's note or position in a reading list.
    The owner and editors can edit items.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    item = get_object_or_404(ReadingListItem, id=item_id, reading_list=reading_list)

    if get_reading_list_role(reading_list, request.user) not in ('owner', 'editor'):
        return _forbidden("You do not have permission to modify this reading list.")

    serializer = ReadingListItemSerializer(item, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_novel_from_list(request, list_id, item_id):
    """
    Remove a novel from a reading list. The owner and editors can remove items.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    item = get_object_or_404(ReadingListItem, id=item_id, reading_list=reading_list)

    if get_reading_list_role(reading_list, request.user) not in ('owner', 'editor'):
        return _forbidden("You do not have permission to modify this reading list.")

    # Get the position of the item to be deleted
    position_to_delete = item.position

    with transaction.atomic():
        # Delete the item
        item.delete()

        # Only update positions for items that come after the deleted item
        ReadingListItem.objects.filter(
            reading_list=reading_list,
            position__gt=position_to_delete
        ).update(position=F('position') - 1)

    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reorder_list_items(request, list_id):
    """
    Reorder items in a reading list.
    Expects a list of {id: uuid, position: number} objects.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)

    if get_reading_list_role(reading_list, request.user) not in ('owner', 'editor'):
        return _forbidden("You do not have permission to modify this reading list.")

    # Validate request data format
    if not isinstance(request.data, list):
        return Response(
            {"detail": "Expected a list of items with id and position."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Update positions
    with transaction.atomic():
        for item_data in request.data:
            if 'id' not in item_data or 'position' not in item_data:
                continue

            try:
                item = ReadingListItem.objects.get(id=item_data['id'], reading_list=reading_list)
                item.position = item_data['position']
                item.save(update_fields=['position'])
            except ReadingListItem.DoesNotExist:
                pass

    # Return updated list
    updated_list = get_object_or_404(ReadingList, id=list_id)
    serializer = DetailedReadingListSerializer(updated_list, context={"request": request})
    return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def manage_collaborators(request, list_id):
    """
    List collaborators (any user with read access) or add one (owner only).
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    role = get_reading_list_role(reading_list, request.user)

    if request.method == "GET":
        if not reading_list.is_public and role is None:
            return _forbidden("You do not have access to this reading list.")
        serializer = ReadingListCollaboratorSerializer(
            reading_list.collaborators.all(), many=True, context={"request": request}
        )
        return Response(serializer.data)

    # POST: owner only
    if role != 'owner':
        return _forbidden("Only the owner can manage collaborators.")

    target_role = request.data.get('role', ReadingListCollaborator.EDITOR)
    if target_role not in dict(ReadingListCollaborator.ROLE_CHOICES):
        return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

    user_id = request.data.get('user_id')
    username = request.data.get('username')
    if user_id:
        user = User.objects.filter(id=user_id).first()
    elif username:
        user = User.objects.filter(username=username).first()
    else:
        return Response({"detail": "Provide a user_id or username."}, status=status.HTTP_400_BAD_REQUEST)

    if user is None:
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.id == reading_list.user_id:
        return Response({"detail": "The owner already has full access."}, status=status.HTTP_400_BAD_REQUEST)

    collaborator, created = ReadingListCollaborator.objects.update_or_create(
        reading_list=reading_list, user=user, defaults={'role': target_role}
    )
    serializer = ReadingListCollaboratorSerializer(collaborator, context={"request": request})
    return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def collaborator_detail(request, list_id, collaborator_id):
    """
    Change a collaborator's role or remove them. Owner only.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)

    if get_reading_list_role(reading_list, request.user) != 'owner':
        return _forbidden("Only the owner can manage collaborators.")

    collaborator = get_object_or_404(
        ReadingListCollaborator, id=collaborator_id, reading_list=reading_list
    )

    if request.method == "PUT":
        target_role = request.data.get('role')
        if target_role not in dict(ReadingListCollaborator.ROLE_CHOICES):
            return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)
        collaborator.role = target_role
        collaborator.save(update_fields=['role'])
        serializer = ReadingListCollaboratorSerializer(collaborator, context={"request": request})
        return Response(serializer.data)

    collaborator.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
