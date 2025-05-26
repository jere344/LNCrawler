from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import novels_views, comments_views, sources_views, users_views 
from .views.csrf import get_csrf_token

# Configure the REST Framework router
router = DefaultRouter()

# Configure the sitemap
sitemaps = {
}

urlpatterns = [
    # API base routes
    path('', include(router.urls)),

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
]