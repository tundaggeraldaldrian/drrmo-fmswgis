"""
URL Configuration for Silay DRRMO Project

This module defines the URL patterns for the entire application.
It includes routes for:
- Admin interface
- User authentication and management
- Maps and GIS features  
- Monitoring and weather data

For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.views.decorators.http import require_GET
import os

# Serve favicon
@require_GET
def favicon(request):
    favicon_path = os.path.join(settings.BASE_DIR, 'silay_drrmo/static/images/drrmo_logo.png')
    if os.path.exists(favicon_path):
        with open(favicon_path, 'rb') as f:
            return HttpResponse(f.read(), content_type='image/png')
    return HttpResponse(status=404)

# Main URL patterns
urlpatterns = [
    path('favicon.ico', favicon),  # Serve favicon
    path('admin/', admin.site.urls),  # Django admin interface
    path('', include('users.urls')),  # User authentication and profiles
    path('maps/', include('maps.urls')),  # GIS mapping features
    path('monitoring/', include('monitoring.urls')),  # Weather and flood monitoring
]

# Serve static and media files in development mode only
# In production, use a web server (nginx/Apache) to serve these files
if settings.DEBUG:
    # Serve static files (CSS, JS, images)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Serve media files (user uploads)
    if hasattr(settings, 'MEDIA_URL') and hasattr(settings, 'MEDIA_ROOT'):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)