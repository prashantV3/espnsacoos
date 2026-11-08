from django.conf import settings
from rest_framework import status, viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.users.models import User, GlobalSettings
from apps.users.serializers import (
    UserSerializer,
    UserCreateUpdateSerializer,
    GlobalSettingsSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
)
from apps.users.permissions import IsSuperUser, IsAdminOrSuperUser


class CookieTokenObtainPairView(TokenObtainPairView):
    """
    Dual-Strategy JWT Login:
    Returns tokens in JSON response (for mobile apps)
    AND sets HttpOnly, Secure, SameSite cookies (for web clients to prevent XSS).
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            access_token = response.data.get('access')
            refresh_token = response.data.get('refresh')

            user = User.objects.get(username=request.data.get('username'))
            response.data['user'] = UserSerializer(user).data
            response.data['must_change_password'] = user.must_change_password

            # Set HttpOnly Cookies for Web
            cookie_secure = getattr(settings, 'JWT_COOKIE_SECURE', False)
            cookie_samesite = getattr(settings, 'JWT_COOKIE_SAMESITE', 'Lax')
            access_cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
            refresh_cookie_name = getattr(settings, 'JWT_AUTH_REFRESH_COOKIE', 'refresh_token')

            response.set_cookie(
                key=access_cookie_name,
                value=access_token,
                httponly=True,
                secure=cookie_secure,
                samesite=cookie_samesite,
                max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
            )
            response.set_cookie(
                key=refresh_cookie_name,
                value=refresh_token,
                httponly=True,
                secure=cookie_secure,
                samesite=cookie_samesite,
                max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
            )
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """
    Refreshes access token reading refresh token from request body OR HttpOnly cookie.
    Sets renewed HttpOnly cookie.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_cookie_name = getattr(settings, 'JWT_AUTH_REFRESH_COOKIE', 'refresh_token')
        refresh_token = request.data.get('refresh') or request.COOKIES.get(refresh_cookie_name)

        if not refresh_token:
            return Response(
                {'detail': 'Refresh token was not provided in request body or cookie.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data={'refresh': refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        response_data = serializer.validated_data
        response = Response(response_data, status=status.HTTP_200_OK)

        access_token = response_data.get('access')
        cookie_secure = getattr(settings, 'JWT_COOKIE_SECURE', False)
        cookie_samesite = getattr(settings, 'JWT_COOKIE_SAMESITE', 'Lax')
        access_cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')

        response.set_cookie(
            key=access_cookie_name,
            value=access_token,
            httponly=True,
            secure=cookie_secure,
            samesite=cookie_samesite,
            max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
        )
        return response


class CookieTokenLogoutView(APIView):
    """
    Logs out the user by deleting HttpOnly authentication cookies.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({'detail': 'Successfully logged out.'}, status=status.HTTP_200_OK)
        access_cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
        refresh_cookie_name = getattr(settings, 'JWT_AUTH_REFRESH_COOKIE', 'refresh_token')

        response.delete_cookie(access_cookie_name)
        response.delete_cookie(refresh_cookie_name)
        return response


class UserProfileView(APIView):
    """
    Returns the currently authenticated user's profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class UserViewSet(viewsets.ModelViewSet):
    """
    Admin & Superuser endpoint to manage SACCOS users and roles.
    """
    queryset = User.objects.all().order_by('-date_joined')
    permission_classes = [IsAdminOrSuperUser]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return UserCreateUpdateSerializer
        return UserSerializer


class GlobalSettingsView(APIView):
    """
    GET: Authenticated users can view global rates & rules.
    PUT/PATCH: Only Superusers can configure interest rates & rules.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsSuperUser()]

    def get(self, request):
        settings_obj = GlobalSettings.get_settings()
        serializer = GlobalSettingsSerializer(settings_obj)
        return Response(serializer.data)

    def put(self, request):
        settings_obj = GlobalSettings.get_settings()
        serializer = GlobalSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


class PasswordChangeView(APIView):
    """
    POST /api/v1/auth/change-password/
    Allows logged-in members and operators to change their password.
    Validates current password and updates must_change_password to False.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        old_password = serializer.validated_data['old_password']
        new_password = serializer.validated_data['new_password']

        if not user.check_password(old_password):
            return Response(
                {'old_password': ['Current password is incorrect.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.must_change_password = False
        user.save()

        return Response({
            'detail': 'Password changed successfully. Your account is now secured.',
            'must_change_password': False
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/reset-password/
    Allows members to reset their password using their username or email.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data['username_or_email'].strip()
        new_password = serializer.validated_data['new_password']

        user = User.objects.filter(username=identifier).first() or User.objects.filter(email__iexact=identifier).first()

        if not user:
            return Response(
                {'username_or_email': ['No account found with this username or email address.']},
                status=status.HTTP_404_NOT_FOUND
            )

        user.set_password(new_password)
        user.must_change_password = False
        user.save()

        return Response({
            'detail': f'Password for {user.username} has been successfully reset. You can now log in with your new password.',
            'must_change_password': False
        }, status=status.HTTP_200_OK)

