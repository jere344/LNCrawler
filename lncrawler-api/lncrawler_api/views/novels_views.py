from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import F, Avg
from ..models.novels_models import Novel, NovelFromSource, Chapter, SourceVote, NovelRating
from django.utils.text import slugify

@api_view(['GET'])
def list_novels(request):
    """
    List all novels with pagination
    """
    novels = Novel.objects.all().order_by('title')
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    
    paginator = Paginator(novels, page_size)
    page_obj = paginator.get_page(page_number)
    
    novels_data = []
    for novel in page_obj:
        # Get the most upvoted source for cover and basic info
        first_source = novel.sources.order_by('-upvotes', 'downvotes', 'title').first()
        
        # Get average rating
        avg_rating = novel.ratings.aggregate(avg_rating=Avg('rating'))['avg_rating']
        rating_count = novel.ratings.count()
        
        novels_data.append({
            'id': str(novel.id),
            'title': novel.title,
            'slug': novel.slug,
            'cover_url': (settings.LNCRAWL_URL + first_source.cover_path) if first_source and first_source.cover_path else None,
            'sources_count': novel.sources_count,
            'total_chapters': novel.total_chapters,
            'avg_rating': round(avg_rating, 1) if avg_rating else None,
            'rating_count': rating_count
        })
    
    return Response({
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': int(page_number),
        'results': novels_data
    })


@api_view(['GET'])
def novel_detail_by_slug(request, novel_slug):
    """
    Get details for a specific novel using its slug
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    
    # Get average rating
    avg_rating = novel.ratings.aggregate(avg_rating=Avg('rating'))['avg_rating']
    rating_count = novel.ratings.count()
    
    # Get the user's rating if it exists
    client_ip = get_client_ip(request)
    user_rating = None
    if client_ip:
        try:
            rating = novel.ratings.filter(ip_address=client_ip).first()
            if rating:
                user_rating = rating.rating
        except:
            pass
    
    sources = []
    # Order sources by vote score (upvotes - downvotes)
    for source in novel.sources.all().order_by(F('upvotes') - F('downvotes')).reverse():
        authors = [author.name for author in source.authors.all()]
        genres = [genre.name for genre in source.genres.all()]
        tags = [tag.name for tag in source.tags.all()]
        
        # Get the user's vote if it exists
        client_ip = get_client_ip(request)
        user_vote = None
        if client_ip:
            try:
                vote = source.votes.filter(ip_address=client_ip).first()
                if vote:
                    user_vote = vote.vote_type
            except:
                pass
        
        sources.append({
            'id': str(source.id),
            'title': source.title,
            'source_url': source.source_url,
            'source_name': source.source_name,
            'source_slug': source.source_slug,
            'cover_url': (settings.LNCRAWL_URL + source.cover_path) if source.cover_path else None,
            'authors': authors,
            'genres': genres,
            'tags': tags,
            'language': source.language,
            'status': source.status,
            'synopsis': source.synopsis,
            'chapters_count': source.chapters_count,
            'volumes_count': source.volumes_count,
            'last_updated': source.updated_at,
            'upvotes': source.upvotes,
            'downvotes': source.downvotes,
            'vote_score': source.vote_score,
            'user_vote': user_vote,
        })
    
    return Response({
        'id': str(novel.id),
        'title': novel.title,
        'slug': novel.slug,
        'sources': sources,
        'created_at': novel.created_at,
        'updated_at': novel.updated_at,
        'avg_rating': round(avg_rating, 1) if avg_rating else None,
        'rating_count': rating_count,
        'user_rating': user_rating
    })

@api_view(['GET'])
def source_detail(request, novel_slug, source_slug):
    """
    Get details for a specific novel source
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    
    authors = [author.name for author in source.authors.all()]
    genres = [genre.name for genre in source.genres.all()]
    tags = [tag.name for tag in source.tags.all()]
    
    # Get the user's vote if it exists
    client_ip = get_client_ip(request)
    user_vote = None
    if client_ip:
        try:
            vote = source.votes.filter(ip_address=client_ip).first()
            if vote:
                user_vote = vote.vote_type
        except:
            pass
    
    source_data = {
        'id': str(source.id),
        'title': source.title,
        'source_url': source.source_url,
        'source_name': source.source_name,
        'source_slug': source.source_slug,
        'cover_url': (settings.LNCRAWL_URL + source.cover_path) if source.cover_path else None,
        'authors': authors,
        'genres': genres,
        'tags': tags,
        'language': source.language,
        'status': source.status,
        'synopsis': source.synopsis,
        'chapters_count': source.chapters_count,
        'volumes_count': source.volumes_count,
        'last_updated': source.updated_at,
        'novel_id': str(novel.id),
        'novel_slug': novel.slug,
        'novel_title': novel.title,
        'upvotes': source.upvotes,
        'downvotes': source.downvotes,
        'vote_score': source.vote_score,
        'user_vote': user_vote
    }
    
    return Response(source_data)

def get_client_ip(request):
    """
    Get client IP address from request
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@api_view(['POST'])
def vote_source(request, novel_slug, source_slug):
    """
    Upvote or downvote a specific novel source
    """
    vote_type = request.data.get('vote_type')
    if vote_type not in ['up', 'down']:
        return Response(
            {'error': 'Invalid vote type. Use "up" or "down".'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    client_ip = get_client_ip(request)
    
    if not client_ip:
        return Response(
            {'error': 'Could not determine your IP address.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create or update the vote
    vote, created = SourceVote.objects.update_or_create(
        source=source,
        ip_address=client_ip,
        defaults={'vote_type': vote_type}
    )
    
    # Return updated vote counts
    return Response({
        'upvotes': source.upvotes,
        'downvotes': source.downvotes,
        'vote_score': source.vote_score,
        'user_vote': vote_type
    })

@api_view(['GET'])
def novel_chapters_by_source(request, novel_slug, source_slug):
    """
    Get all chapters for a specific novel source using slugs
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    
    chapters = source.chapters.all().order_by('chapter_id')
    
    chapters_data = []
    for chapter in chapters:
        chapters_data.append({
            'id': str(chapter.id),
            'chapter_id': chapter.chapter_id,
            'title': chapter.title,
            'url': chapter.url,
            'volume': chapter.volume,
            'volume_title': chapter.volume_title,
            'has_content': chapter.has_content
        })
    
    return Response({
        'novel_id': str(novel.id),
        'novel_title': novel.title,
        'novel_slug': novel.slug,
        'source_id': str(source.id),
        'source_name': source.source_name,
        'source_slug': source.source_slug,
        'chapters': chapters_data
    })

@api_view(['GET'])
def chapter_content_by_number(request, novel_slug, source_slug, chapter_number):
    """
    Get content for a specific chapter by its number
    """
    novel = get_object_or_404(Novel, slug=novel_slug)
    source = get_object_or_404(novel.sources, source_slug=source_slug)
    chapter = get_object_or_404(source.chapters, chapter_id=chapter_number)
    
    if not chapter.has_content:
        return Response(
            {"error": "Chapter content not available"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    body = chapter.body

    previous_chapter = source.chapters.filter(chapter_id__lt=chapter_number).order_by('-chapter_id').first()
    next_chapter = source.chapters.filter(chapter_id__gt=chapter_number).order_by('chapter_id').first()
    
    return Response({
        'id': str(chapter.id),
        'chapter_id': chapter.chapter_id,
        'title': chapter.title,
        'novel_title': novel.title,
        'novel_id': str(novel.id),
        'novel_slug': novel.slug,
        'source_id': str(source.id),
        'source_name': source.source_name,
        'source_slug': source.source_slug,
        'body': body,
        'prev_chapter': previous_chapter.chapter_id if previous_chapter and previous_chapter.has_content else None,
        'next_chapter': next_chapter.chapter_id if next_chapter and next_chapter.has_content else None,
    })

@api_view(['POST'])
def rate_novel(request, novel_slug):
    """
    Rate a novel from 1-5 stars
    """
    rating_value = request.data.get('rating')
    try:
        rating_value = int(rating_value)
        if rating_value < 1 or rating_value > 5:
            raise ValueError("Rating must be between 1 and 5")
    except (ValueError, TypeError):
        return Response(
            {'error': 'Invalid rating. Must be an integer between 1 and 5.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    novel = get_object_or_404(Novel, slug=novel_slug)
    client_ip = get_client_ip(request)
    
    if not client_ip:
        return Response(
            {'error': 'Could not determine your IP address.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create or update the rating
    rating, created = NovelRating.objects.update_or_create(
        novel=novel,
        ip_address=client_ip,
        defaults={'rating': rating_value}
    )
    
    # Get updated average rating
    avg_rating = novel.ratings.aggregate(avg_rating=Avg('rating'))['avg_rating']
    rating_count = novel.ratings.count()
    
    return Response({
        'avg_rating': round(avg_rating, 1) if avg_rating else None,
        'rating_count': rating_count,
        'user_rating': rating_value
    })
