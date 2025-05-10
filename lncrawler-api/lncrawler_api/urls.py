from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.contrib.sitemaps.views import sitemap
from . import views

# Configure the REST Framework router
router = DefaultRouter()

# Configure the sitemap
sitemaps = {
}

urlpatterns = [
    # API base routes
    path('', include(router.urls)),


    # Search endpoints
    path('downloader/search/start/', views.start_search, name='start_search'),
    path('downloader/search/status/<str:job_id>/', views.get_search_status, name='get_search_status'),
    path('downloader/search/results/<str:job_id>/', views.get_search_results, name='get_search_results'),
    
    # Download endpoints
    path('downloader/download/start/<str:job_id>/', views.start_download, name='start_download'),
    path('downloader/download/status/<str:job_id>/', views.get_download_status, name='get_download_status'),
    path('downloader/download/results/<str:job_id>/', views.get_download_results, name='get_download_results'),
    
    # Job management
    path('downloader/jobs/cancel/<str:job_id>/', views.cancel_job, name='cancel_job'),
    path('downloader/jobs/', views.list_jobs, name='list_jobs'),
    path('downloader/jobs/<str:job_id>/', views.job_details, name='job_details'),
]