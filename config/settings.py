"""
Django settings for config project.
Financial Ledger & Loan Management System
"""

import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import dj_database_url
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-saccos-default-dev-secret-key-replace-in-prod')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '*').split(',') if host.strip()]

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Application definition — unfold MUST come before django.contrib.admin
INSTALLED_APPS = [
    'unfold',                           # django-unfold: must be before admin
    'unfold.contrib.filters',           # Unfold enhanced filters
    'unfold.contrib.forms',             # Unfold styled form widgets
    'unfold.contrib.inlines',           # Unfold tabular/stacked inlines
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    # Local SACCOS apps
    'apps.users.apps.UsersConfig',
    'apps.loans.apps.LoansConfig',
    'apps.ledger.apps.LedgerConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'apps.users.middleware.AdminAccessRestrictionMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database — Supabase PostgreSQL via DATABASE_URL or SQLite locally
DATABASE_URL = os.getenv('DATABASE_URL', '')
if 'test' in sys.argv:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
elif DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=True)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================
# UNFOLD ADMIN CONFIGURATION
# ============================================================
UNFOLD = {
    "SITE_TITLE": "ESPN SACCOS",
    "SITE_HEADER": "ESPN SACCOS Admin",
    "SITE_SUBHEADER": "Financial Ledger & Loan Management",
    "SITE_URL": "/",
    "SITE_ICON": {
        "light": lambda request: static("admin/img/saccos_logo_light.svg"),
        "dark": lambda request: static("admin/img/saccos_logo_dark.svg"),
    },
    "SITE_LOGO": {
        "light": lambda request: static("admin/img/saccos_logo_light.svg"),
        "dark": lambda request: static("admin/img/saccos_logo_dark.svg"),
    },
    "SITE_SYMBOL": "account_balance",
    "SITE_FAVICONS": [],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SHOW_BACK_BUTTON": True,
    "ENVIRONMENT": "apps.users.admin_helpers.environment_callback",
    "DASHBOARD_CALLBACK": "apps.ledger.admin_dashboard.dashboard_callback",
    "LOGIN": {
        "image": lambda request: static("admin/img/login_bg.svg"),
        "redirect_after": lambda request: reverse_lazy("admin:index"),
    },
    "STYLES": [],
    "SCRIPTS": [],
    "BORDER_RADIUS": "8px",
    "COLORS": {
        "font": {
            "subtle-light": "107 114 128",
            "subtle-dark": "156 163 175",
            "default-light": "17 24 39",
            "default-dark": "243 244 246",
            "important-light": "0 0 0",
            "important-dark": "255 255 255",
        },
        "primary": {
            "50": "240 253 244",
            "100": "220 252 231",
            "200": "187 247 208",
            "300": "134 239 172",
            "400": "74 222 128",
            "500": "34 197 94",
            "600": "22 163 74",
            "700": "21 128 61",
            "800": "22 101 52",
            "900": "20 83 45",
            "950": "5 46 22",
        },
    },
    "EXTENSIONS": {
        "modeltranslation": {
            "flags": {},
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Financial Dashboard"),
                "separator": True,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Overview Dashboard"),
                        "icon": "dashboard",
                        "link": "/dashboard/",
                    },
                    {
                        "title": _("Admin Home"),
                        "icon": "home",
                        "link": reverse_lazy("admin:index"),
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            {
                "title": _("Loan Portfolio"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Primary Loans (EMI)"),
                        "icon": "credit_card",
                        "link": reverse_lazy("admin:loans_primaryloan_changelist"),
                        "badge": "apps.loans.admin_helpers.active_loans_badge",
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Emergency Advances"),
                        "icon": "bolt",
                        "link": reverse_lazy("admin:loans_emergencyadvance_changelist"),
                        "badge": "apps.loans.admin_helpers.overdue_advances_badge",
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            {
                "title": _("Double-Entry Ledger"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("All Transactions"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:ledger_transaction_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Ledger Entries"),
                        "icon": "menu_book",
                        "link": reverse_lazy("admin:ledger_ledgerentry_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Chart of Accounts"),
                        "icon": "account_tree",
                        "link": reverse_lazy("admin:ledger_account_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            {
                "title": _("Reports & Analytics"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Trial Balance (JSON)"),
                        "icon": "balance",
                        "link": "/api/v1/reports/trial-balance/",
                    },
                    {
                        "title": _("Member Dashboard"),
                        "icon": "person",
                        "link": "/api/v1/dashboard/me/",
                    },
                ],
            },
            {
                "title": _("User Administration"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Members & Staff"),
                        "icon": "group",
                        "link": reverse_lazy("admin:users_user_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Global Settings"),
                        "icon": "settings",
                        "link": reverse_lazy("admin:users_globalsettings_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Auth Groups"),
                        "icon": "lock_person",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
    "TABS": [
        {
            "models": ["loans.primaryloan", "loans.emergencyadvance"],
            "items": [
                {
                    "title": _("Primary Loans"),
                    "link": reverse_lazy("admin:loans_primaryloan_changelist"),
                },
                {
                    "title": _("Emergency Advances"),
                    "link": reverse_lazy("admin:loans_emergencyadvance_changelist"),
                },
            ],
        },
        {
            "models": ["ledger.transaction", "ledger.ledgerentry", "ledger.account"],
            "items": [
                {
                    "title": _("Transactions"),
                    "link": reverse_lazy("admin:ledger_transaction_changelist"),
                },
                {
                    "title": _("Journal Entries"),
                    "link": reverse_lazy("admin:ledger_ledgerentry_changelist"),
                },
                {
                    "title": _("Chart of Accounts"),
                    "link": reverse_lazy("admin:ledger_account_changelist"),
                },
            ],
        },
    ],
}

# ============================================================
# REST FRAMEWORK
# ============================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.users.authentication.CookieOrHeaderJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# ============================================================
# SIMPLE JWT
# ============================================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_EXPIRATION_MINUTES', 60))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_EXPIRATION_DAYS', 7))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# JWT Cookie Configuration
JWT_AUTH_COOKIE = 'access_token'
JWT_AUTH_REFRESH_COOKIE = 'refresh_token'
JWT_COOKIE_SECURE = os.getenv('JWT_COOKIE_SECURE', 'False').lower() in ('true', '1', 't')
JWT_COOKIE_SAMESITE = os.getenv('JWT_COOKIE_SAMESITE', 'Lax')

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5173').split(',') if origin.strip()
]
