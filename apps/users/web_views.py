from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.models import User


def logout_web_view(request):
    """
    Safely logs out the user via GET or POST, clears Django session,
    removes JWT HttpOnly cookies, and redirects back to the dashboard or login page.
    Prevents Django 5's HTTP 405 Method Not Allowed error on GET requests.
    """
    user_name = request.user.username if request.user.is_authenticated else None
    auth_logout(request)

    response = redirect('/')
    # Clear JWT auth cookies
    access_cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
    refresh_cookie_name = getattr(settings, 'JWT_AUTH_REFRESH_COOKIE', 'refresh_token')
    response.delete_cookie(access_cookie_name)
    response.delete_cookie(refresh_cookie_name)

    if user_name:
        messages.success(request, f"Successfully logged out. See you soon!")
    else:
        messages.info(request, "You are logged out.")

    return response


def login_web_view(request):
    """
    Renders the modern Apex dark-themed login portal for ESPN SACCOS members and administrators.
    Allows quick credential selection and handles standard web session + JWT cookie authentication.
    """
    if request.user.is_authenticated:
        return redirect('/')

    error_message = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)

            response = redirect('/')

            # Issue and attach JWT HttpOnly cookies for API parity
            try:
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                refresh_token = str(refresh)

                cookie_secure = getattr(settings, 'JWT_COOKIE_SECURE', False)
                cookie_samesite = getattr(settings, 'JWT_COOKIE_SAMESITE', 'Lax')
                access_cookie = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
                refresh_cookie = getattr(settings, 'JWT_AUTH_REFRESH_COOKIE', 'refresh_token')

                response.set_cookie(
                    key=access_cookie,
                    value=access_token,
                    httponly=True,
                    secure=cookie_secure,
                    samesite=cookie_samesite,
                    max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
                )
                response.set_cookie(
                    key=refresh_cookie,
                    value=refresh_token,
                    httponly=True,
                    secure=cookie_secure,
                    samesite=cookie_samesite,
                    max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
                )
            except Exception:
                pass

            if getattr(user, 'must_change_password', False):
                messages.warning(
                    request,
                    "Security Notice: You are logging in with a temporary password. Please set a new personal password."
                )
            else:
                messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")

            return response
        else:
            error_message = "Invalid username or password. Please verify your credentials."

    return render(request, 'login.html', {
        'error_message': error_message
    })

