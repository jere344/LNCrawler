from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import F, Avg, Q, Count
from ..models.novels_models import Novel, SourceVote, NovelRating, Genre, Tag, Author, NovelViewCount, WeeklyNovelView
from ..utils import get_client_ip
from datetime import datetime, timedelta


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
    
    # Get current ISO year and week
    current_date = datetime.now()
    current_year_week = f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"
    
    novels_data = []
    for novel in page_obj:
        # Get the most upvoted source for cover and basic info
        first_source = novel.sources.order_by('-upvotes', 'downvotes', 'title').first()
        
        # Get average rating
        avg_rating = novel.ratings.aggregate(avg_rating=Avg('rating'))['avg_rating']
        rating_count = novel.ratings.count()
        
        # Get view counts
        view_count = NovelViewCount.objects.filter(novel=novel).first()
        total_views = view_count.views if view_count else 0
        
        # Get current week views
        weekly_view = WeeklyNovelView.objects.filter(
            novel=novel,
            year_week=current_year_week
        ).first()
        weekly_views = weekly_view.views if weekly_view else 0
        
        novels_data.append({
            'id': str(novel.id),
            'title': novel.title,
            'slug': novel.slug,
            'cover_url': (settings.LNCRAWL_URL + first_source.cover_path) if first_source and first_source.cover_path else None,
            'sources_count': novel.sources_count,
            'total_chapters': novel.total_chapters,
            'avg_rating': round(avg_rating, 1) if avg_rating else None,
            'rating_count': rating_count,
            'total_views': total_views,
            'weekly_views': weekly_views
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
    
    # Get view counts
    view_count = NovelViewCount.objects.filter(novel=novel).first()
    total_views = view_count.views if view_count else 0
    
    # Get current week views
    current_date = datetime.now()
    current_year_week = f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"
    weekly_view = WeeklyNovelView.objects.filter(
        novel=novel,
        year_week=current_year_week
    ).first()
    weekly_views = weekly_view.views if weekly_view else 0
    
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
        'user_rating': user_rating,
        'total_views': total_views,
        'weekly_views': weekly_views
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
    
    # Increment view count for the novel
    view_count, created = NovelViewCount.objects.get_or_create(novel=novel)
    view_count.increment()
    
    # Increment weekly view count
    WeeklyNovelView.increment_for_novel(novel)
    
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

@api_view(['GET'])
def search_novels(request):
    """
    Search novels with various filters
    """
    # Get search parameters
    query = request.GET.get('query', '').strip()
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    
    # Get filter parameters
    genres = request.GET.getlist('genre', [])
    tags = request.GET.getlist('tag', [])
    authors = request.GET.getlist('author', [])
    status = request.GET.get('status', '')
    min_rating = request.GET.get('min_rating', None)
    sort_by = request.GET.get('sort_by', 'title')
    sort_order = request.GET.get('sort_order', 'asc')
    
    # Start with all novels
    novels_query = Novel.objects.all()
    
    # Apply search query if provided
    if query:
        novels_query = novels_query.filter(
            Q(title__icontains=query) | 
            Q(sources__synopsis__icontains=query) | 
            Q(sources__authors__name__icontains=query)
        ).distinct()
    
    # Filter by genres
    if genres:
        novels_query = novels_query.filter(
            sources__genres__name__in=genres
        ).distinct()
    
    # Filter by tags
    if tags:
        novels_query = novels_query.filter(
            sources__tags__name__in=tags
        ).distinct()
    
    # Filter by authors
    if authors:
        novels_query = novels_query.filter(
            sources__authors__name__in=authors
        ).distinct()
    
    # Filter by status
    if status:
        novels_query = novels_query.filter(
            sources__status=status
        ).distinct()
    
    # Filter by minimum rating
    if min_rating and min_rating.isdigit():
        min_rating_val = float(min_rating)
        # Get novels with average rating >= min_rating
        novels_with_min_rating = Novel.objects.annotate(
            avg_rating=Avg('ratings__rating')
        ).filter(avg_rating__gte=min_rating_val)
        novels_query = novels_query.filter(id__in=novels_with_min_rating)
    
    # Apply sorting
    if sort_by == 'rating':
        # Sort by rating requires annotation
        novels_query = novels_query.annotate(
            avg_rating=Avg('ratings__rating')
        )
        order_field = '-avg_rating' if sort_order == 'desc' else 'avg_rating'
        novels_query = novels_query.order_by(order_field, 'title')
    elif sort_by == 'title':
        order_field = '-title' if sort_order == 'desc' else 'title'
        novels_query = novels_query.order_by(order_field)
    elif sort_by == 'date_added':
        order_field = '-created_at' if sort_order == 'desc' else 'created_at'
        novels_query = novels_query.order_by(order_field)
    elif sort_by == 'popularity':
        # Using total number of ratings as a proxy for popularity
        novels_query = novels_query.annotate(
            num_ratings=Count('ratings')
        )
        order_field = '-num_ratings' if sort_order == 'desc' else 'num_ratings'
        novels_query = novels_query.order_by(order_field, 'title')
    else:
        # Default sorting by title
        novels_query = novels_query.order_by('title')
    
    # Pagination
    paginator = Paginator(novels_query, page_size)
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
        'results': novels_data,
        'filters': {
            'statuses': ['Ongoing', 'Completed', 'Unknown', 'On Hiatus', 'Cancelled']
        }
    })

@api_view(['GET'])
def autocomplete_suggestion(request):
    """
    Get autocomplete suggestions for genres, tags, or authors with novel counts
    """
    search_type = request.GET.get('type', '')
    query = request.GET.get('query', '').strip()
    limit = int(request.GET.get('limit', '10'))
    
    if len(query) < 3:
        return Response([])
    
    if search_type == 'genre':
        # Count novels for each genre
        genre_counts = Genre.objects.filter(name__icontains=query).annotate(
            novel_count=Count('novels', distinct=True)
        ).order_by('-novel_count')[:limit]
        
        suggestions = [{'name': genre.name, 'count': genre.novel_count} for genre in genre_counts]
        
    elif search_type == 'tag':
        # Count novels for each tag
        tag_counts = Tag.objects.filter(name__icontains=query).annotate(
            novel_count=Count('novenovelslfromsource', distinct=True)
        ).order_by('-novel_count')[:limit]
        
        suggestions = [{'name': tag.name, 'count': tag.novel_count} for tag in tag_counts]
        
    elif search_type == 'author':
        # Count novels for each author
        author_counts = Author.objects.filter(name__icontains=query).annotate(
            novel_count=Count('novels', distinct=True)
        ).order_by('-novel_count')[:limit]
        
        suggestions = [{'name': author.name, 'count': author.novel_count} for author in author_counts]
        
    else:
        return Response({'error': 'Invalid search type'}, status=status.HTTP_400_BAD_REQUEST)
    
    return Response(suggestions)
