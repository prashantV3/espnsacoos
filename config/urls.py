from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.ledger.web_views import dashboard_ui_view

urlpatterns = [
    # Interactive Web Dashboard with Sidebar, Charts & Live Ledger
    path('', dashboard_ui_view, name='home_dashboard'),
    path('dashboard/', dashboard_ui_view, name='dashboard'),

    # Django Administration Panel
    path('admin/', admin.site.urls),

    # SACCOS REST API v1
    path('api/v1/', include('apps.users.urls')),
    path('api/v1/', include('apps.loans.urls')),
    path('api/v1/', include('apps.ledger.urls')),
]

# Serve static files properly during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
