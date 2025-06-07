from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import F, Q

from ..models.users_models import ReadingList, ReadingListItem
from ..models.novels_models import Novel
from ..serializers import (
    ReadingListSerializer, 
    DetailedReadingListSerializer, 
    ReadingListItemSerializer
)

@api_view(["GET"])
def list_all_reading_lists(request):
    """
    List all reading lists, with optional filtering.
    """
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)
    user_id = request.GET.get("user_id")
    search = request.GET.get("search", "")
    
    query_set = ReadingList.objects.all()
    
    if user_id:
        query_set = query_set.filter(user_id=user_id)
        
    if search:
        query_set = query_set.filter(
            Q(title__icontains=search) | 
            Q(description__icontains=search)
        )
        
    query_set = query_set.order_by('-created_at')
    paginator = Paginator(query_set, page_size)
    page_obj = paginator.get_page(page_number)
    
    serializer = ReadingListSerializer(page_obj, many=True, context={"request": request})
    
    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": int(page_number),
        "results": serializer.data,
    })


@api_view(["GET"])
def get_user_reading_lists(request):
    """
    Get all reading lists for a specific user.
    """
    page_number = request.GET.get("page", 1)
    page_size = request.GET.get("page_size", 20)
    search = request.GET.get("search", "")
    
    user_id = request.GET.get("user_id", request.user.id if request.user.is_authenticated else None)
    if not user_id:
        return Response(
            {"detail": "User ID is required."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    query_set = ReadingList.objects.filter(user_id=user_id)
    
    if search:
        query_set = query_set.filter(
            Q(title__icontains=search) | 
            Q(description__icontains=search)
        )
    
    query_set = query_set.order_by('-created_at')
    if not query_set.exists():
        return Response(
            {"detail": "No reading lists found for this user."},
            status=status.HTTP_404_NOT_FOUND
        )
        
    paginator = Paginator(query_set, page_size)
    page_obj = paginator.get_page(page_number)
    
    serializer = ReadingListSerializer(page_obj, many=True, context={"request": request})
    
    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": int(page_number),
        "results": serializer.data,
    })


@api_view(["GET"])
def reading_list_detail(request, list_id):
    """
    Get details of a specific reading list including all its items.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    serializer = DetailedReadingListSerializer(reading_list, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_reading_list(request):
    """
    Create a new reading list.
    """
    serializer = ReadingListSerializer(data=request.data)
    if serializer.is_valid():
        reading_list = serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_reading_list(request, list_id):
    """
    Update a reading list's title and description.
    Only the creator can edit the list.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    
    # Check if user is the creator
    if reading_list.user != request.user:
        return Response(
            {"detail": "You do not have permission to edit this reading list."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = ReadingListSerializer(reading_list, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_reading_list(request, list_id):
    """
    Delete a reading list.
    Only the creator can delete the list.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    
    # Check if user is the creator
    if reading_list.user != request.user:
        return Response(
            {"detail": "You do not have permission to delete this reading list."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    reading_list.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_novel_to_list(request, list_id):
    """
    Add a novel to a reading list.
    Only the creator can add items to the list.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    
    # Check if user is the creator
    if reading_list.user != request.user:
        return Response(
            {"detail": "You do not have permission to modify this reading list."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Add novel_id to request data
    request.data['reading_list'] = list_id
    
    # Find the highest position and increment by 1 for new item
    highest_position = ReadingListItem.objects.filter(reading_list=reading_list).order_by('-position').first()
    next_position = (highest_position.position + 1) if highest_position else 0
    request.data['position'] = next_position
    
    serializer = ReadingListItemSerializer(data=request.data)
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
    Only the creator can edit items in the list.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    item = get_object_or_404(ReadingListItem, id=item_id, reading_list=reading_list)
    
    # Check if user is the creator
    if reading_list.user != request.user:
        return Response(
            {"detail": "You do not have permission to modify this reading list."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = ReadingListItemSerializer(item, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_novel_from_list(request, list_id, item_id):
    """
    Remove a novel from a reading list.
    Only the creator can remove items from the list.
    """
    reading_list = get_object_or_404(ReadingList, id=list_id)
    item = get_object_or_404(ReadingListItem, id=item_id, reading_list=reading_list)
    
    # Check if user is the creator
    if reading_list.user != request.user:
        return Response(
            {"detail": "You do not have permission to modify this reading list."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get the position of the item to be deleted
    position_to_delete = item.position
    
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
    
    # Check if user is the creator
    if reading_list.user != request.user:
        return Response(
            {"detail": "You do not have permission to modify this reading list."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Validate request data format
    if not isinstance(request.data, list):
        return Response(
            {"detail": "Expected a list of items with id and position."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Update positions
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
