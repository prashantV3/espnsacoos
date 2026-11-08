from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


class CookieOrHeaderJWTAuthentication(JWTAuthentication):
    """
    Dual-strategy JWT Authentication:
    1. First looks for 'Authorization: Bearer <token>' header (used by mobile apps).
    2. If no header is provided, inspects HttpOnly cookie 'access_token' (used by web apps to prevent XSS).
    """

    def authenticate(self, request):
        header = self.get_header(request)

        # 1. Mobile Authorization Header check
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token

        # 2. Web HttpOnly Cookie check
        cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
        raw_token = request.COOKIES.get(cookie_name)

        if raw_token is not None:
            try:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token
            except (InvalidToken, AuthenticationFailed):
                return None

        return None

