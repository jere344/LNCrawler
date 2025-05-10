from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from ..models.novels_models import Novel, NovelFromSource, Chapter
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
        # Get the first source for cover and basic info
        first_source = novel.sources.first()
        
        novels_data.append({
            'id': str(novel.id),
            'title': novel.title,
            'slug': novel.slug,
            'cover_url': first_source.cover_url if first_source else None,
            'sources_count': novel.sources_count,
            'total_chapters': novel.total_chapters,
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
    
    sources = []
    for source in novel.sources.all():
        authors = [author.name for author in source.authors.all()]
        genres = [genre.name for genre in source.genres.all()]
        tags = [tag.name for tag in source.tags.all()]
        
        sources.append({
            'id': str(source.id),
            'title': source.title,
            'source_url': source.source_url,
            'source_name': source.source_name,
            'source_slug': source.source_slug,
            'cover_url': source.cover_url,
            'authors': authors,
            'genres': genres,
            'tags': tags,
            'language': source.language,
            'status': source.status,
            'synopsis': source.synopsis,
            'chapters_count': source.chapters_count,
            'volumes_count': source.volumes_count,
            'last_updated': source.updated_at,
        })
    
    return Response({
        'id': str(novel.id),
        'title': novel.title,
        'slug': novel.slug,
        'sources': sources,
        'created_at': novel.created_at,
        'updated_at': novel.updated_at,
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
    
    source_data = {
        'id': str(source.id),
        'title': source.title,
        'source_url': source.source_url,
        'source_name': source.source_name,
        'source_slug': source.source_slug,
        'cover_url': source.cover_url,
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
        'novel_title': novel.title
    }
    
    return Response(source_data)

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
        'prev_chapter': source.chapters.filter(chapter_id__lt=chapter_number).order_by('-chapter_id').values('chapter_id').first(),
        'next_chapter': source.chapters.filter(chapter_id__gt=chapter_number).order_by('chapter_id').values('chapter_id').first()
    })
