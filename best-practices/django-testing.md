# Django Testing — pytest + DRF

## Setup

```bash
pip install pytest pytest-django factory-boy faker pytest-cov
```

```ini
# pyproject.toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.test"
python_files   = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "--tb=short --strict-markers -p no:warnings"

[tool.coverage.run]
source = ["apps", "common"]
omit   = ["*/migrations/*", "*/admin.py", "*/tests/*"]
```

```python
# config/settings/test.py
from .base import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME":   "test_myapp",
        "USER":   "postgres",
        "HOST":   "localhost",
    }
}

# Fast password hashing in tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Synchronous Celery — tasks run inline in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Use in-memory cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Disable throttling in tests
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
}
```

---

## Factories

```python
# apps/users/tests/factories.py
import factory
from factory.django import DjangoModelFactory
from factory import Faker, SubFactory, LazyAttribute
from apps.tenants.models import Tenant
from apps.users.models import User

class TenantFactory(DjangoModelFactory):
    class Meta:
        model = Tenant

    name      = Faker("company")
    slug      = LazyAttribute(lambda o: o.name.lower().replace(" ", "-")[:50])
    plan      = "pro"
    is_active = True

class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    tenant   = SubFactory(TenantFactory)
    email    = Faker("email")
    name     = Faker("name")
    role     = "member"
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "testpass123")
        if create:
            obj.save(update_fields=["password"])

class AdminUserFactory(UserFactory):
    role = "admin"

class OwnerUserFactory(UserFactory):
    role = "owner"
```

---

## Fixtures

```python
# conftest.py
import pytest
from rest_framework.test import APIClient
from apps.users.tests.factories import UserFactory, TenantFactory
from rest_framework_simplejwt.tokens import RefreshToken

@pytest.fixture
def tenant(db):
    return TenantFactory()

@pytest.fixture
def user(tenant):
    return UserFactory(tenant=tenant)

@pytest.fixture
def admin_user(tenant):
    return UserFactory(tenant=tenant, role="admin")

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def auth_client(user):
    """Authenticated API client — JWT cookie set."""
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.cookies["access_token"] = token
    return client

@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    token = str(RefreshToken.for_user(admin_user).access_token)
    client.cookies["access_token"] = token
    return client
```

---

## View Tests

```python
# apps/users/tests/test_views.py
import pytest
from rest_framework import status
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

class TestUserListView:
    def test_unauthenticated_returns_401(self, api_client):
        response = api_client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_only_tenant_users(self, auth_client, user, tenant):
        # Create users in same tenant
        other_users = UserFactory.create_batch(3, tenant=tenant)

        # Create user in different tenant — should not appear
        UserFactory()

        response = auth_client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["pagination"]["total"] == 4  # user + 3 others

    def test_pagination(self, auth_client, user, tenant):
        UserFactory.create_batch(25, tenant=tenant)

        response = auth_client.get("/api/v1/users/?page_size=10")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 10
        assert response.data["pagination"]["total_pages"] == 3

    def test_filter_by_role(self, auth_client, user, tenant):
        UserFactory.create_batch(3, tenant=tenant, role="admin")
        UserFactory.create_batch(2, tenant=tenant, role="viewer")

        response = auth_client.get("/api/v1/users/?role=admin")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["pagination"]["total"] == 3

class TestUserDetailView:
    def test_get_user_by_public_id(self, auth_client, user, tenant):
        target = UserFactory(tenant=tenant)
        response = auth_client.get(f"/api/v1/users/{target.public_id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["public_id"] == target.public_id

    def test_cannot_access_other_tenant_user(self, auth_client):
        other_user = UserFactory()  # different tenant
        response = auth_client.get(f"/api/v1/users/{other_user.public_id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_excludes_sensitive_fields(self, auth_client, user, tenant):
        target = UserFactory(tenant=tenant)
        response = auth_client.get(f"/api/v1/users/{target.public_id}/")
        assert "password" not in response.data
        assert "mfa_secret" not in response.data

class TestUserCreateView:
    def test_member_cannot_create_user(self, auth_client):
        response = auth_client.post("/api/v1/users/invite/", {"email": "new@example.com"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_invite_user(self, admin_client, tenant):
        response = admin_client.post("/api/v1/users/invite/", {"email": "new@example.com"})
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "new@example.com"
```

---

## Auth Tests

```python
# apps/users/tests/test_auth.py
import pytest
from rest_framework import status
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

class TestLogin:
    def test_valid_credentials_set_httponly_cookie(self, api_client, tenant):
        user = UserFactory(tenant=tenant)
        user.set_password("secret123")
        user.save()

        response = api_client.post("/api/v1/auth/login", {
            "email": user.email,
            "password": "secret123",
        })
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.cookies
        assert response.cookies["access_token"]["httponly"]
        assert response.cookies["access_token"]["samesite"] == "Strict"

    def test_invalid_credentials_return_401(self, api_client, user):
        response = api_client.post("/api/v1/auth/login", {
            "email": user.email,
            "password": "wrongpassword",
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_does_not_expose_password_hash(self, api_client, tenant):
        user = UserFactory(tenant=tenant)
        user.set_password("secret123")
        user.save()

        response = api_client.post("/api/v1/auth/login", {
            "email": user.email,
            "password": "secret123",
        })
        assert "password" not in response.data
        assert "mfa_secret" not in response.data

    def test_logout_clears_cookies(self, auth_client):
        response = auth_client.post("/api/v1/auth/logout")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Cookie should be cleared (max_age=0)
        assert response.cookies.get("access_token", {}).get("max_age") == 0

class TestBruteForceProtection:
    def test_rate_limit_after_threshold(self, api_client, user):
        for _ in range(10):
            api_client.post("/api/v1/auth/login", {
                "email": user.email,
                "password": "wrong",
            })
        response = api_client.post("/api/v1/auth/login", {
            "email": user.email,
            "password": "wrong",
        })
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
```

---

## Service / Business Logic Tests

```python
# apps/users/tests/test_services.py
import pytest
from apps.users.services import UserService
from apps.users.tests.factories import UserFactory, TenantFactory

pytestmark = pytest.mark.django_db

class TestUserService:
    def test_invite_creates_user(self):
        tenant = TenantFactory()
        service = UserService()
        user = service.invite("new@example.com", tenant)
        assert user.email == "new@example.com"
        assert user.tenant == tenant

    def test_invite_existing_email_returns_existing_user(self):
        tenant = TenantFactory()
        existing = UserFactory(tenant=tenant, email="existing@example.com")
        service = UserService()
        user = service.invite("existing@example.com", tenant)
        assert user.id == existing.id

    def test_invite_sends_email(self, mailoutbox):
        tenant = TenantFactory()
        service = UserService()
        service.invite("new@example.com", tenant)
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["new@example.com"]
```

---

## Celery Task Tests

```python
# apps/users/tests/test_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from apps.users.tasks import send_invite_email
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

class TestSendInviteEmail:
    def test_sends_email_to_user(self, mailoutbox):
        user = UserFactory()
        send_invite_email(user.id)  # CELERY_TASK_ALWAYS_EAGER=True — runs inline
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == [user.email]

    def test_missing_user_does_not_raise(self):
        # Should not raise — log warning and return
        send_invite_email(999999)  # non-existent user

    @patch("apps.users.tasks.send_mail")
    def test_retries_on_smtp_failure(self, mock_send_mail):
        user = UserFactory()
        mock_send_mail.side_effect = [Exception("SMTP error"), None]

        # With CELERY_TASK_ALWAYS_EAGER, auto-retry runs immediately
        send_invite_email.apply(args=[user.id])
        assert mock_send_mail.call_count == 2
```

---

## Model Tests

```python
# apps/users/tests/test_models.py
import pytest
from django.utils import timezone
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

class TestUserModel:
    def test_public_id_is_ulid(self):
        user = UserFactory()
        assert len(user.public_id) == 26
        assert user.public_id.isalnum()

    def test_soft_delete(self):
        user = UserFactory()
        user.soft_delete()
        user.refresh_from_db()
        assert user.deleted_at is not None
        assert user.deleted_at <= timezone.now()

    def test_soft_deleted_user_excluded_from_default_manager(self):
        user = UserFactory()
        user.soft_delete()
        assert not User.objects.filter(id=user.id).exists()
        # Still accessible via all_objects
        assert User.all_objects.filter(id=user.id).exists()
```

---

## Integration / End-to-End Flow

```python
# apps/billing/tests/test_checkout_flow.py
import pytest
from unittest.mock import patch, MagicMock
from rest_framework import status
from apps.users.tests.factories import UserFactory, TenantFactory

pytestmark = pytest.mark.django_db

class TestCheckoutFlow:
    @patch("apps.billing.services.stripe.checkout.Session.create")
    def test_full_checkout_flow(self, mock_stripe, admin_client, tenant):
        mock_stripe.return_value = MagicMock(url="https://checkout.stripe.com/test")

        # 1. Create checkout session
        response = admin_client.post("/api/v1/billing/checkout/", {"plan": "pro"})
        assert response.status_code == status.HTTP_200_OK
        assert "checkout_url" in response.data

        # 2. Simulate Stripe webhook
        webhook_payload = {
            "type": "checkout.session.completed",
            "data": {"object": {"metadata": {"tenant_id": str(tenant.id)}, "mode": "subscription"}},
        }
        with patch("apps.billing.views.stripe.Webhook.construct_event", return_value=webhook_payload):
            response = admin_client.post(
                "/api/v1/webhooks/stripe/",
                data=webhook_payload,
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="test-sig",
            )
        assert response.status_code == status.HTTP_200_OK

        # 3. Verify tenant plan updated
        tenant.refresh_from_db()
        assert tenant.plan == "pro"
```

---

## Coverage

```bash
# Run tests with coverage
pytest --cov=apps --cov=common --cov-report=term-missing --cov-fail-under=80

# HTML report
pytest --cov=apps --cov-report=html
open htmlcov/index.html
```

```yaml
# .github/workflows/ci.yml
- name: Run tests
  run: |
    pytest --cov=apps --cov=common \
           --cov-report=xml \
           --cov-fail-under=80 \
           -x   # stop on first failure

- name: Upload coverage
  uses: codecov/codecov-action@v4
  with:
    files: coverage.xml
```

---

## Testing Checklist

- [ ] Factory Boy factories for all models — no manual `Model.objects.create()` in tests
- [ ] Separate fixtures for unauthenticated, member, admin, owner clients
- [ ] Every endpoint tested for 401 (no auth) and 403 (wrong role)
- [ ] Cross-tenant access returns 404 — not 403 (don't leak existence)
- [ ] Response never includes `password`, `mfa_secret`, internal IDs
- [ ] Celery tasks tested with `CELERY_TASK_ALWAYS_EAGER = True`
- [ ] Service tests isolated from HTTP layer
- [ ] `mailoutbox` fixture for email content assertions
- [ ] `pytest.mark.django_db` on every test class/function that hits DB
- [ ] 80%+ coverage enforced in CI (`--cov-fail-under=80`)
- [ ] Integration tests cover critical flows (checkout, auth, invites)
