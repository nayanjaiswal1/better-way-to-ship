# Django + DRF Best Practices

## Project Structure

```
backend/
├── config/
│   ├── __init__.py
│   ├── settings/
│   │   ├── base.py          # shared settings
│   │   ├── development.py   # dev overrides
│   │   ├── production.py    # prod overrides
│   │   └── test.py          # test overrides
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py              # for Django Channels / async
├── apps/
│   ├── users/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── permissions.py
│   │   ├── services.py      # business logic (not in views)
│   │   ├── selectors.py     # read queries (not in views)
│   │   ├── tasks.py         # Celery tasks
│   │   ├── signals.py
│   │   ├── admin.py
│   │   └── tests/
│   │       ├── test_views.py
│   │       ├── test_services.py
│   │       └── factories.py
│   ├── tenants/
│   ├── billing/
│   └── notifications/
├── common/
│   ├── models.py            # abstract base models
│   ├── serializers.py       # base serializers
│   ├── permissions.py       # shared permission classes
│   ├── pagination.py
│   ├── middleware.py
│   ├── exceptions.py
│   └── validators.py
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
└── pyproject.toml
```

---

## Settings Management

```bash
pip install django-environ
```

```python
# config/settings/base.py
import environ

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

environ.Env.read_env()  # reads .env file

SECRET_KEY   = env("SECRET_KEY")
DEBUG        = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",

    # Third party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",

    # Apps
    "apps.users",
    "apps.tenants",
    "apps.billing",
    "apps.notifications",
]

DATABASES = {
    "default": env.db("DATABASE_URL"),  # postgresql://user:pass@host/db
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.CookieJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
}

# OpenAPI
SPECTACULAR_SETTINGS = {
    "TITLE": "MyApp API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,   # disable in production via urls.py
}

# Celery
CELERY_BROKER_URL      = env("REDIS_URL")
CELERY_RESULT_BACKEND  = env("REDIS_URL")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT  = ["json"]
CELERY_TIMEZONE        = "UTC"

# Security
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS  = env.list("CSRF_TRUSTED_ORIGINS", default=[])
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE    = True
SECURE_SSL_REDIRECT   = True
SECURE_HSTS_SECONDS   = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD   = True
```

```python
# config/settings/production.py
from .base import *

DEBUG = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING"},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING"},
    },
}
```

---

## Abstract Base Models

```python
# common/models.py
import uuid
from django.db import models
from .ulid import new_ulid

class TimestampedModel(models.Model):
    """All models inherit from this."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class TenantScopedModel(TimestampedModel):
    """Models that belong to a tenant."""
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )
    # Public ID — ULID, safe to expose in URLs
    public_id = models.CharField(
        max_length=26,
        unique=True,
        default=new_ulid,
        editable=False,
        db_index=True,
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

class TenantScopedManager(models.Manager):
    """Auto-scope queries to current tenant and exclude soft-deleted."""
    def get_queryset(self):
        from .tenant_context import get_current_tenant_id
        tenant_id = get_current_tenant_id()
        qs = super().get_queryset().filter(deleted_at__isnull=True)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        return qs
```

```python
# common/ulid.py
import ulid as ulid_lib

def new_ulid() -> str:
    return str(ulid_lib.new())
```

---

## User Model

```python
# apps/users/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from common.models import TimestampedModel
from common.ulid import new_ulid

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    public_id   = models.CharField(max_length=26, unique=True, default=new_ulid, editable=False)
    email       = models.EmailField(unique=True)
    name        = models.CharField(max_length=255)
    tenant      = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="users")
    role        = models.CharField(max_length=20, choices=[
        ("owner",  "Owner"),
        ("admin",  "Admin"),
        ("member", "Member"),
        ("viewer", "Viewer"),
    ], default="member")
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret  = models.CharField(max_length=64, blank=True)  # never in serializer

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["tenant", "email"]),
            models.Index(fields=["public_id"]),
        ]

    def __str__(self):
        return self.email
```

---

## Authentication — JWT httpOnly Cookies

```bash
pip install djangorestframework-simplejwt
```

```python
# apps/users/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

class CookieJWTAuthentication(JWTAuthentication):
    """Read JWT from httpOnly cookie, not Authorization header."""

    def authenticate(self, request):
        token = request.COOKIES.get("access_token")
        if not token:
            return None
        try:
            validated = self.get_validated_token(token)
            return self.get_user(validated), validated
        except (TokenError, InvalidToken):
            return None
```

```python
# apps/users/views.py — auth endpoints
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from .services import AuthService
from .serializers import LoginSerializer

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = AuthService.authenticate(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        refresh = RefreshToken.for_user(user)
        response = Response({"user": UserSerializer(user).data})

        # httpOnly cookies — inaccessible to JavaScript
        response.set_cookie(
            "access_token",
            str(refresh.access_token),
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Strict",
            max_age=15 * 60,           # 15 minutes
        )
        response.set_cookie(
            "refresh_token",
            str(refresh),
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Strict",
            max_age=7 * 24 * 60 * 60,  # 7 days
        )
        return response

class LogoutView(APIView):
    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response

class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.COOKIES.get("refresh_token")
        if not token:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(token)
            response = Response({"ok": True})
            response.set_cookie(
                "access_token",
                str(refresh.access_token),
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Strict",
                max_age=15 * 60,
            )
            return response
        except Exception:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
```

---

## Serializers

```python
# apps/users/serializers.py
from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["public_id", "email", "name", "role", "created_at"]
        read_only_fields = ["public_id", "created_at"]
        # mfa_secret, password NEVER in fields

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "name", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField()

# Nested serializer — one query with select_related
class UserDetailSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = User
        fields = ["public_id", "email", "name", "role", "tenant_name", "created_at"]
```

---

## ViewSets

```python
# apps/users/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter

from common.permissions import IsTenantMember, IsOwnerOrAdmin
from .models import User
from .serializers import UserSerializer, UserCreateSerializer
from .selectors import get_users_for_tenant
from .services import UserService
from .filters import UserFilter

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantMember]
    filterset_class    = UserFilter
    search_fields      = ["email", "name"]
    ordering_fields    = ["created_at", "name"]
    ordering           = ["-created_at"]

    def get_queryset(self):
        # Selector handles tenant scoping + prefetch
        return get_users_for_tenant(self.request.user.tenant_id)

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ("destroy", "update", "partial_update"):
            return [IsOwnerOrAdmin()]
        return super().get_permissions()

    # Use public_id in URLs — not sequential int
    lookup_field = "public_id"

    @extend_schema(summary="Get current user")
    @action(detail=False, methods=["get"])
    def me(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(summary="Invite user to tenant")
    @action(detail=False, methods=["post"], permission_classes=[IsOwnerOrAdmin])
    def invite(self, request):
        service = UserService()
        user = service.invite(request.data["email"], request.user.tenant)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
```

```python
# apps/users/selectors.py — read queries separated from business logic
from django.db.models import QuerySet
from .models import User

def get_users_for_tenant(tenant_id: int) -> QuerySet[User]:
    return (
        User.objects
        .filter(tenant_id=tenant_id, is_active=True, deleted_at__isnull=True)
        .select_related("tenant")
        .order_by("-created_at")
    )

def get_user_by_public_id(public_id: str, tenant_id: int) -> User:
    return User.objects.get(public_id=public_id, tenant_id=tenant_id, deleted_at__isnull=True)
```

```python
# apps/users/services.py — business logic
from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from .models import User

class UserService:
    def invite(self, email: str, tenant) -> User:
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"tenant": tenant, "name": email.split("@")[0]},
        )
        # Send invite email via Celery
        from .tasks import send_invite_email
        send_invite_email.delay(user.id)
        return user

class AuthService:
    @staticmethod
    def authenticate(email: str, password: str) -> User:
        user = authenticate(email=email, password=password)
        if not user or not user.is_active:
            raise AuthenticationFailed("Invalid credentials")
        return user
```

---

## URL Configuration

```python
# config/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerUI

router = DefaultRouter()

urlpatterns = [
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.tenants.urls")),

    # Health check — no auth required
    path("health", HealthCheckView.as_view()),

    # OpenAPI — only in non-production
    path("openapi.json", SpectacularAPIView.as_view(), name="schema"),
]

# apps/users/urls.py
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")

urlpatterns = router.urls + [
    path("auth/login",   views.LoginView.as_view()),
    path("auth/logout",  views.LogoutView.as_view()),
    path("auth/refresh", views.RefreshView.as_view()),
    path("auth/me",      views.MeView.as_view()),
]
```

---

## Permissions

```python
# common/permissions.py
from rest_framework.permissions import BasePermission

class IsTenantMember(BasePermission):
    """User must be authenticated and active tenant member."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

class IsOwnerOrAdmin(BasePermission):
    """Only owners and admins can perform this action."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ("owner", "admin")
        )

class IsOwner(BasePermission):
    """Only tenant owner."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "owner"

class IsObjectOwner(BasePermission):
    """Object must belong to the requesting user."""
    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id

class TenantObjectPermission(BasePermission):
    """Object must belong to the user's tenant."""
    def has_object_permission(self, request, view, obj):
        return obj.tenant_id == request.user.tenant_id
```

---

## Middleware

```python
# common/middleware.py
import uuid
import structlog
from django.utils.deprecation import MiddlewareMixin
from .tenant_context import set_current_tenant_id

logger = structlog.get_logger()

class CorrelationIdMiddleware(MiddlewareMixin):
    """Add correlation ID to every request for distributed tracing."""
    def process_request(self, request):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

    def process_response(self, request, response):
        response["X-Correlation-ID"] = getattr(request, "correlation_id", "")
        return response

class TenantMiddleware(MiddlewareMixin):
    """Set tenant context from authenticated user."""
    def process_request(self, request):
        if request.user.is_authenticated:
            set_current_tenant_id(request.user.tenant_id)
            structlog.contextvars.bind_contextvars(tenant_id=request.user.tenant_id)

class SecurityHeadersMiddleware(MiddlewareMixin):
    """Add security headers to every response."""
    def process_response(self, request, response):
        response["X-Frame-Options"]           = "DENY"
        response["X-Content-Type-Options"]    = "nosniff"
        response["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response["Permissions-Policy"]        = "camera=(), microphone=(), geolocation=()"
        response["Cross-Origin-Opener-Policy"] = "same-origin"
        return response
```

```python
# config/settings/base.py — add middleware
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.middleware.CorrelationIdMiddleware",
    "common.middleware.TenantMiddleware",
    "common.middleware.SecurityHeadersMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

---

## Exception Handling

```python
# common/exceptions.py
from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException
from rest_framework import status
import structlog

logger = structlog.get_logger()

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        # Standardize error shape
        response.data = {
            "error": {
                "code":    getattr(exc, "default_code", "error"),
                "message": str(exc.detail) if hasattr(exc, "detail") else str(exc),
                "status":  response.status_code,
            }
        }
    else:
        # Unhandled exception — 500
        logger.exception("Unhandled exception", exc_info=exc)
        from rest_framework.response import Response
        response = Response(
            {"error": {"code": "internal_error", "message": "Internal server error", "status": 500}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response

class AppValidationError(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "validation_error"

class ResourceNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"

class ForbiddenError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "forbidden"
```

---

## Pagination

```python
# common/pagination.py
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class PageNumberPagination(PageNumberPagination):
    page_size              = 20
    page_size_query_param  = "page_size"
    max_page_size          = 100
    page_query_param       = "page"

    def get_paginated_response(self, data):
        return Response({
            "data": data,
            "pagination": {
                "page":        self.page.number,
                "page_size":   self.page.paginator.per_page,
                "total":       self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "has_next":    self.page.has_next(),
                "has_previous": self.page.has_previous(),
            },
        })
```

---

## Filtering

```python
# apps/users/filters.py
import django_filters
from .models import User

class UserFilter(django_filters.FilterSet):
    role           = django_filters.CharFilter()
    created_after  = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = User
        fields = ["role", "is_active"]

# Usage: GET /api/v1/users?role=admin&created_after=2026-01-01
```

---

## Health Check

```python
# common/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import connection
from django.core.cache import cache

class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {}

        # DB check
        try:
            connection.ensure_connection()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"

        # Cache check
        try:
            cache.set("health_check", "ok", 5)
            checks["cache"] = "ok"
        except Exception:
            checks["cache"] = "error"

        status_code = 200 if all(v == "ok" for v in checks.values()) else 503
        return Response({"status": "ok" if status_code == 200 else "degraded", **checks}, status=status_code)
```

---

## Django ORM — Performance Patterns

```python
# ✅ Always use select_related / prefetch_related — never N+1
users = (
    User.objects
    .filter(tenant_id=tenant_id)
    .select_related("tenant")           # FK — single JOIN
    .prefetch_related("groups")         # M2M — separate query, cached
    .only("id", "public_id", "email", "name", "role")  # avoid SELECT *
)

# ✅ Bulk operations
User.objects.bulk_create([User(...) for u in users], batch_size=500)
User.objects.filter(tenant_id=tenant_id).update(is_active=False)

# ✅ defer heavy fields
users = User.objects.defer("mfa_secret", "password")

# ✅ exists() instead of count() for boolean checks
if User.objects.filter(email=email, tenant=tenant).exists():
    raise AppValidationError("Email already in use")

# ✅ annotate instead of Python loops
from django.db.models import Count, Q
users = User.objects.annotate(
    open_ticket_count=Count("tickets", filter=Q(tickets__status="open"))
)

# ✅ iterator() for large querysets — avoid loading all into memory
for user in User.objects.filter(is_active=True).iterator(chunk_size=500):
    process(user)
```

---

## Django Migrations — Production Safe

```bash
# Always check migration before applying in production
python manage.py sqlmigrate users 0003

# Apply with timeout (avoid locking)
# See zero-downtime-migrations.md for Expand-Contract pattern

# Never edit applied migrations — always create new ones
python manage.py makemigrations

# Squash migrations periodically for performance
python manage.py squashmigrations users 0001 0020
```

```python
# migrations/0003_add_index.py — safe index creation
from django.db import migrations, models

class Migration(migrations.Migration):
    atomic = False  # required for CONCURRENTLY

    operations = [
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_users_tenant_role ON users (tenant_id, role)",
            reverse_sql="DROP INDEX CONCURRENTLY idx_users_tenant_role",
        ),
    ]
```

---

## Django Admin — Secure

```python
# apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ["email", "name", "tenant", "role", "is_active", "created_at"]
    list_filter   = ["role", "is_active", "tenant"]
    search_fields = ["email", "name"]
    ordering      = ["-created_at"]
    readonly_fields = ["public_id", "created_at", "updated_at", "last_login"]

    # Never show mfa_secret in admin
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "public_id", "tenant", "role")}),
        ("Flags", {"fields": ("is_active", "is_staff", "mfa_enabled")}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "last_login")}),
    )
    exclude = ["mfa_secret"]

# Restrict admin to staff IP range via middleware or nginx
# Never expose /admin/ publicly without IP allowlist
```

---

## Bootstrap Endpoint — Django Equivalent

```python
# apps/core/views.py
class BootstrapView(APIView):
    """Single call replaces user + flags + nav + tenant queries at startup."""

    def get(self, request):
        user   = request.user
        tenant = user.tenant

        # Parallel data fetch via select_related
        flags      = FeatureFlag.objects.filter(tenant=tenant)
        nav_items  = NavItem.get_for_role(user.role)
        plan_limits = PlanLimit.objects.get(plan=tenant.plan)

        return Response({
            "user":    UserSerializer(user).data,
            "tenant":  TenantSerializer(tenant).data,
            "flags":   {f.key: f.enabled for f in flags},
            "nav":     NavItemSerializer(nav_items, many=True).data,
            "plan":    PlanLimitSerializer(plan_limits).data,
        })
```

---

## Django Checklist

- [ ] Custom User model with `public_id` (ULID) — never expose `pk`
- [ ] JWT in httpOnly cookies — not Authorization header
- [ ] `select_related` / `prefetch_related` on all list endpoints — no N+1
- [ ] `only()` or `defer()` to avoid `SELECT *` on large tables
- [ ] Selectors (read queries) and Services (business logic) separated from views
- [ ] Custom exception handler — consistent error shape
- [ ] Correlation ID middleware — traceable across services
- [ ] Tenant middleware — scopes context automatically
- [ ] Security headers middleware
- [ ] `atomic = False` + `CONCURRENTLY` for production index migrations
- [ ] Admin excludes sensitive fields (`mfa_secret`, `password` hash)
- [ ] Health check endpoint with DB + cache checks
- [ ] `DEBUG=False` enforced in production settings
- [ ] OpenAPI docs disabled in production (`SERVE_INCLUDE_SCHEMA = False`)
