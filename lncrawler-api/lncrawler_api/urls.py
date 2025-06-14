from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import novels_views, comments_views, sources_views, users_views, boards_views, reviews_views, reading_lists_views
from .views.csrf import get_csrf_token
from django.contrib.sitemaps.views import sitemap, index
from django.views.decorators.cache import cache_page
from .views.sitemap import (
    StaticViewSitemap,
    NovelSitemap,
    SourceSitemap,
    ChapterListSitemap,
    # ChapterReaderSitemap,
    ImageGallerySitemap,
)

# Configure the REST Framework router
router = DefaultRouter()

# Configure the sitemap
sitemaps = {
    'static': StaticViewSitemap,
    'novels': NovelSitemap,
    'sources': SourceSitemap,
    'chapterlists': ChapterListSitemap,
    # 'chapters': ChapterReaderSitemap,
    'galleries': ImageGallerySitemap,
}

urlpatterns = [
    # API base routes
    path('', include(router.urls)),

    # Board endpoints
    path('boards/', boards_views.list_boards, name='list_boards'),
    path('boards/<slug:board_slug>/', boards_views.board_detail, name='board_detail'),
    path('boards/<slug:board_slug>/comments/', boards_views.board_comments, name='board_comments'),
    path('boards/<slug:board_slug>/comments/add/', boards_views.add_board_comment, name='add_board_comment'),

    # Novel comments
    path('novels/<slug:novel_slug>/comments/', comments_views.novel_comments, name='novel_comments'),
    path('novels/<slug:novel_slug>/comments/add/', comments_views.add_comment, name='add_novel_comment'),
    
    # Chapter comments
    path('novels/<slug:novel_slug>/<slug:source_slug>/chapter/<int:chapter_number>/comments/', 
         comments_views.chapter_comments, name='chapter_comments'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/chapter/<int:chapter_number>/comments/add/', 
         comments_views.add_comment, name='add_chapter_comment'),

    # Comment voting
    path('comments/<uuid:comment_id>/vote/', comments_views.vote_comment, name='vote_comment'),
    
    # Comment editing
    path('comments/<uuid:comment_id>/edit/', comments_views.edit_comment, name='edit_comment'),

    # Novel-related endpoints with new URL structure
    path('novels/', novels_views.list_novels, name='list_novels'),
    path('novels/home/', novels_views.home_page, name='home_page'),  # Add this new endpoint
    path('novels/search/', novels_views.search_novels, name='search_novels'),  # Add this new endpoint
    path('novels/autocomplete/', novels_views.autocomplete_suggestion, name='autocomplete_suggestion'),  # Add this new endpoint
    path('novels/featured/random/', novels_views.random_featured_novel, name='random_featured_novel'),  # Add this new endpoint
    
    # User-specific Novel Bookmarking
    path('users/bookmarks/novels/', users_views.list_bookmarked_novels, name='list_bookmarked_novels'),
    path('users/bookmarks/novels/<slug:novel_slug>/add/', users_views.add_novel_bookmark, name='add_novel_bookmark'),
    path('users/bookmarks/novels/<slug:novel_slug>/remove/', users_views.remove_novel_bookmark, name='remove_novel_bookmark'),
    
    # User Reading History
    path('users/reading-history/', users_views.list_reading_history, name='list_reading_history'),
    path('users/reading-history/<uuid:history_id>/delete/', users_views.delete_reading_history, name='delete_reading_history'),
    path('users/reading-history/mark-read/<slug:novel_slug>/<slug:source_slug>/chapter/<int:chapter_number>/', 
         users_views.mark_chapter_as_read, name='mark_chapter_as_read'),

    
    # Review endpoints
    path('novels/<slug:novel_slug>/reviews/', reviews_views.novel_reviews, name='novel_reviews'),
    path('novels/<slug:novel_slug>/reviews/add/', reviews_views.add_review, name='add_review'),
    path('reviews/<uuid:review_id>/', reviews_views.review_detail, name='review_detail'),
    path('reviews/<uuid:review_id>/reactions/add/', reviews_views.add_reaction, name='add_reaction'),
    path('reviews/<uuid:review_id>/reactions/remove/', reviews_views.remove_reaction, name='remove_reaction'),
    path('users/reviews/', reviews_views.user_reviews, name='user_reviews'),

    # Novel detail and source endpoints
    path('novels/<slug:novel_slug>/', novels_views.novel_detail_by_slug, name='novel_detail_by_slug'),
    path('novels/<slug:novel_slug>/rate/', novels_views.rate_novel, name='rate_novel'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/', sources_views.source_detail, name='source_detail'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/vote/', sources_views.vote_source, name='vote_source'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/chapters/', sources_views.novel_chapters_by_source, name='novel_chapters_by_source'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/chapter/<int:chapter_number>/', sources_views.chapter_content_by_number, name='chapter_content_by_number'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/gallery/', sources_views.source_image_gallery, name='source_image_gallery'),

    # downloader endpoints
    path('downloader/search/start/', views.start_search, name='start_search'),
    path('downloader/search/status/<str:job_id>/', views.get_search_status, name='get_search_status'),
    path('downloader/search/results/<str:job_id>/', views.get_search_results, name='get_search_results'),
    
    path('downloader/download/start/<str:job_id>/', views.start_download, name='start_download'),
    path('downloader/download/start-direct/', views.start_direct_download, name='start_direct_download'),
    path('downloader/download/status/<str:job_id>/', views.get_download_status, name='get_download_status'),
    path('downloader/download/results/<str:job_id>/', views.get_download_results, name='get_download_results'),
    
    path('downloader/jobs/cancel/<str:job_id>/', views.cancel_job, name='cancel_job'),
    path('downloader/jobs/', views.list_jobs, name='list_jobs'),
    path('downloader/jobs/<str:job_id>/', views.job_details, name='job_details'),

    # CSRF token endpoint
    path('csrf-token/', get_csrf_token, name='csrf_token'),
    
    # sitemap - 100h cache
    path('sitemap.xml', cache_page(360000)(index), {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.index'),
    path('sitemap-<section>.xml', cache_page(360000)(sitemap), {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),

    # Reading List endpoints
    path('reading-lists/', reading_lists_views.list_all_reading_lists, name='list_all_reading_lists'),
    path('reading-lists/create/', reading_lists_views.create_reading_list, name='create_reading_list'),
    path('reading-lists/<uuid:list_id>/', reading_lists_views.reading_list_detail, name='reading_list_detail'),
    path('reading-lists/<uuid:list_id>/update/', reading_lists_views.update_reading_list, name='update_reading_list'),
    path('reading-lists/<uuid:list_id>/delete/', reading_lists_views.delete_reading_list, name='delete_reading_list'),
    path('reading-lists/<uuid:list_id>/add-novel/', reading_lists_views.add_novel_to_list, name='add_novel_to_list'),
    path('reading-lists/<uuid:list_id>/reorder/', reading_lists_views.reorder_list_items, name='reorder_list_items'),
    path('reading-lists/<uuid:list_id>/items/<uuid:item_id>/update/', reading_lists_views.update_list_item, name='update_list_item'),
    path('reading-lists/<uuid:list_id>/items/<uuid:item_id>/remove/', reading_lists_views.remove_novel_from_list, name='remove_novel_from_list'),
    path('users/reading-lists/', reading_lists_views.get_user_reading_lists, name='get_user_reading_lists'),
]