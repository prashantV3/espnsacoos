from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.users.views import (
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    CookieTokenLogoutView,
    UserProfileView,
    UserViewSet,
    GlobalSettingsView,
    PasswordChangeView,
    PasswordResetConfirmView,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # Auth Endpoints
    path('auth/login/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('auth/logout/', CookieTokenLogoutView.as_view(), name='logout'),
    path('auth/me/', UserProfileView.as_view(), name='user_profile'),
    path('auth/change-password/', PasswordChangeView.as_view(), name='change_password'),
    path('auth/reset-password/', PasswordResetConfirmView.as_view(), name='reset_password'),

    # Global SACCOS Financial Configuration
    path('settings/', GlobalSettingsView.as_view(), name='global_settings'),

    # Users CRUD router
    path('', include(router.urls)),
]

