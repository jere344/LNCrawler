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
]