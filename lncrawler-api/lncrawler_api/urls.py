from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.contrib.sitemaps.views import sitemap
from . import views
from .views import novels_views

# Configure the REST Framework router
router = DefaultRouter()

# Configure the sitemap
sitemaps = {
}

urlpatterns = [
    # API base routes
    path('', include(router.urls)),

    # Novel-related endpoints with new URL structure
    path('novels/', novels_views.list_novels, name='list_novels'),
    path('novels/<slug:novel_slug>/', novels_views.novel_detail_by_slug, name='novel_detail_by_slug'),
    path('novels/<slug:novel_slug>/rate/', novels_views.rate_novel, name='rate_novel'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/', novels_views.source_detail, name='source_detail'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/vote/', novels_views.vote_source, name='vote_source'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/chapters/', novels_views.novel_chapters_by_source, name='novel_chapters_by_source'),
    path('novels/<slug:novel_slug>/<slug:source_slug>/chapter/<int:chapter_number>/', novels_views.chapter_content_by_number, name='chapter_content_by_number'),

    # downloader endpoints
    path('downloader/search/start/', views.start_search, name='start_search'),
    path('downloader/search/status/<str:job_id>/', views.get_search_status, name='get_search_status'),
    path('downloader/search/results/<str:job_id>/', views.get_search_results, name='get_search_results'),
    
    path('downloader/download/start/<str:job_id>/', views.start_download, name='start_download'),
    path('downloader/download/status/<str:job_id>/', views.get_download_status, name='get_download_status'),
    path('downloader/download/results/<str:job_id>/', views.get_download_results, name='get_download_results'),
    
    path('downloader/jobs/cancel/<str:job_id>/', views.cancel_job, name='cancel_job'),
    path('downloader/jobs/', views.list_jobs, name='list_jobs'),
    path('downloader/jobs/<str:job_id>/', views.job_details, name='job_details'),
]