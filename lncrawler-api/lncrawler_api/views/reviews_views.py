from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from ..models.novels_models import Novel
from ..models.reviews_models import Review, ReviewReaction
from ..serializers.reviews_serializers import (
    ReviewListSerializer, ReviewCreateSerializer, ReactionCreateSerializer
)
from ..utils.ip_utils import get_client_ip


@api_view(['GET'])
@permission_classes([AllowAny])
def novel_reviews(request, novel_slug):
    """Get all reviews for a novel with pagination"""
    novel = get_object_or_404(Novel, slug=novel_slug)
    reviews = Review.objects.filter(novel=novel).select_related('user', 'novel').prefetch_related('reactions__user')
    
    # Pagination
    page_number = request.GET.get('page', 1)
    page_size = min(int(request.GET.get('page_size', 4)), 50) 
    
    paginator = Paginator(reviews, page_size)
    page_obj = paginator.get_page(page_number)
    
    serializer = ReviewListSerializer(page_obj, many=True, context={'request': request})
    
    return Response({
        'reviews': serializer.data,
        'pagination': {
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_reviews': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_review(request, novel_slug):
    """Add a new review for a novel"""
    novel = get_object_or_404(Novel, slug=novel_slug)
    
    # Check if user already reviewed this novel
    if Review.objects.filter(novel=novel, user=request.user).exists():
        return Response(
            {'error': 'You have already reviewed this novel. Edit your existing review instead.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = ReviewCreateSerializer(data=request.data)
    if serializer.is_valid():
        review = serializer.save(novel=novel, user=request.user)
        response_serializer = ReviewListSerializer(review, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def review_detail(request, review_id):
    """Get, update, or delete a specific review"""
    review = get_object_or_404(Review, id=review_id)
    
    if request.method == 'GET':
        serializer = ReviewListSerializer(review, context={'request': request})
        return Response(serializer.data)
    
    # Only the review author can modify or delete
    if review.user != request.user:
        return Response(
            {'error': 'You can only modify your own reviews.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    if request.method == 'PUT':
        serializer = ReviewCreateSerializer(review, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            response_serializer = ReviewListSerializer(review, context={'request': request})
            return Response(response_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([AllowAny])
def add_reaction(request, review_id):
    """Add or update a reaction to a review"""
    review = get_object_or_404(Review, id=review_id)
    ip_address = get_client_ip(request)
    
    serializer = ReactionCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    reaction_type = serializer.validated_data['reaction']
    
    # Check for existing reaction
    if request.user.is_authenticated:
        existing_reaction = ReviewReaction.objects.filter(
            review=review, user=request.user
        ).first()
    else:
        existing_reaction = ReviewReaction.objects.filter(
            review=review, ip_address=ip_address, user__isnull=True
        ).first()
    
    if existing_reaction:
        if existing_reaction.reaction == reaction_type:
            # Same reaction - remove it
            existing_reaction.delete()
            return Response({'message': 'Reaction removed'}, status=status.HTTP_200_OK)
        else:
            # Different reaction - update it
            existing_reaction.reaction = reaction_type
            existing_reaction.save()
            return Response({'message': 'Reaction updated'}, status=status.HTTP_200_OK)
    else:
        # New reaction
        ReviewReaction.objects.create(
            review=review,
            user=request.user if request.user.is_authenticated else None,
            ip_address=ip_address,
            reaction=reaction_type
        )
        return Response({'message': 'Reaction added'}, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def remove_reaction(request, review_id):
    """Remove a reaction from a review"""
    review = get_object_or_404(Review, id=review_id)
    ip_address = get_client_ip(request)
    
    if request.user.is_authenticated:
        reaction = get_object_or_404(ReviewReaction, review=review, user=request.user)
    else:
        reaction = get_object_or_404(
            ReviewReaction, review=review, ip_address=ip_address, user__isnull=True
        )
    
    reaction.delete()
    return Response({'message': 'Reaction removed'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_reviews(request):
    """Get all reviews by the authenticated user"""
    reviews = Review.objects.filter(user=request.user).select_related('novel').prefetch_related('reactions__user')
    
    # Pagination
    page_number = request.GET.get('page', 1)
    page_size = min(int(request.GET.get('page_size', 20)), 50)
    
    paginator = Paginator(reviews, page_size)
    page_obj = paginator.get_page(page_number)
    
    serializer = ReviewListSerializer(page_obj, many=True, context={'request': request})
    
    return Response({
        'reviews': serializer.data,
        'pagination': {
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_reviews': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }
    })
