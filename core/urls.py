from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Admin Interface
    path('admin/', admin.site.urls),

    # API Documentation (drf-spectacular)
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API Version 1 Routes
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/rewards/', include('rewards.urls')),
    path('api/v1/reminders/', include('reminders.urls')),
    path('api/v1/ocr/', include('ocr.urls')),

    # Web Frontend (template-based)
    path('web/', include('frontend.urls', namespace='frontend')),

    # Root redirect → login
    path('', RedirectView.as_view(url='/web/login/', permanent=False)),
]
