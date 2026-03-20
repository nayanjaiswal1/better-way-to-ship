# Django Permissions — RBAC + ABAC

## Role Hierarchy

```python
# common/roles.py
from enum import StrEnum

class Role(StrEnum):
    OWNER  = "owner"
    ADMIN  = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

# Roles ordered by privilege — owner > admin > member > viewer
ROLE_HIERARCHY = [Role.OWNER, Role.ADMIN, Role.MEMBER, Role.VIEWER]

def has_at_least_role(user_role: str, required_role: str) -> bool:
    try:
        return ROLE_HIERARCHY.index(user_role) <= ROLE_HIERARCHY.index(required_role)
    except ValueError:
        return False
```

---

## DRF Permission Classes

```python
# common/permissions.py
from rest_framework.permissions import BasePermission
from .roles import Role, has_at_least_role

class IsTenantMember(BasePermission):
    """Any authenticated member of the tenant."""
    def has_permission(self, request, view):
        return request.user.is_authenticated

class IsViewer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_at_least_role(request.user.role, Role.VIEWER)

class IsMember(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_at_least_role(request.user.role, Role.MEMBER)

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_at_least_role(request.user.role, Role.ADMIN)

class IsOwner(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == Role.OWNER

class IsObjectOwner(BasePermission):
    """Object must have been created by the requesting user."""
    def has_object_permission(self, request, view, obj):
        return hasattr(obj, "created_by_id") and obj.created_by_id == request.user.id

class IsTenantObject(BasePermission):
    """Object must belong to the user's tenant."""
    def has_object_permission(self, request, view, obj):
        return hasattr(obj, "tenant_id") and obj.tenant_id == request.user.tenant_id

class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in ("GET", "HEAD", "OPTIONS")
```

### Composing Permissions

```python
# DRF supports AND (&) and OR (|) composition
from rest_framework.permissions import IsAuthenticated

class ProjectViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            # Any authenticated member can read
            return [IsAuthenticated()]
        if self.action in ("create",):
            # Members and above can create
            return [IsMember()]
        if self.action in ("update", "partial_update"):
            # Admin OR the object creator
            return [IsAdmin() | IsObjectOwner()]
        if self.action == "destroy":
            return [IsAdmin()]
        return [IsAuthenticated()]
```

---

## ABAC — Attribute-Based Access Control

For complex rules that go beyond role checks.

```python
# common/abac.py
from dataclasses import dataclass
from typing import Any
from rest_framework.exceptions import PermissionDenied

@dataclass
class PermissionContext:
    user: Any
    action: str
    resource: Any | None = None

class PermissionChecker:
    """
    Central place for all permission checks.
    Keeps business logic out of views.
    """

    def __init__(self, ctx: PermissionContext):
        self.ctx = ctx

    def check(self) -> None:
        """Raise PermissionDenied if not allowed."""
        checker = self._get_checker()
        if not checker():
            raise PermissionDenied(f"Not allowed: {self.ctx.action}")

    def _get_checker(self):
        return {
            "order:create":  self._can_create_order,
            "order:delete":  self._can_delete_order,
            "order:export":  self._can_export_orders,
            "user:invite":   self._can_invite_user,
            "user:delete":   self._can_delete_user,
            "billing:manage": self._can_manage_billing,
        }.get(self.ctx.action, lambda: False)

    def _can_create_order(self) -> bool:
        return has_at_least_role(self.ctx.user.role, Role.MEMBER)

    def _can_delete_order(self) -> bool:
        order = self.ctx.resource
        # Admin can always delete; member can only delete own orders
        if has_at_least_role(self.ctx.user.role, Role.ADMIN):
            return True
        return order.created_by_id == self.ctx.user.id

    def _can_export_orders(self) -> bool:
        # Only available on Pro+ plans
        return (
            has_at_least_role(self.ctx.user.role, Role.MEMBER)
            and self.ctx.user.tenant.plan in ("pro", "enterprise")
        )

    def _can_invite_user(self) -> bool:
        return has_at_least_role(self.ctx.user.role, Role.ADMIN)

    def _can_delete_user(self) -> bool:
        target = self.ctx.resource
        # Can't delete yourself or someone with higher role
        if target.id == self.ctx.user.id:
            return False
        return ROLE_HIERARCHY.index(self.ctx.user.role) < ROLE_HIERARCHY.index(target.role)

    def _can_manage_billing(self) -> bool:
        return self.ctx.user.role == Role.OWNER
```

```python
# Usage in views / services
def check_permission(user, action, resource=None):
    ctx = PermissionContext(user=user, action=action, resource=resource)
    PermissionChecker(ctx).check()

# In a service
class OrderService:
    def delete(self, order_id: str, user) -> None:
        order = Order.objects.get(public_id=order_id, tenant=user.tenant)
        check_permission(user, "order:delete", resource=order)
        order.soft_delete()

# In a view
class OrderViewSet(viewsets.ModelViewSet):
    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        check_permission(request.user, "order:delete", resource=order)
        order.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```

---

## Field-Level Permissions

Return different fields based on the user's role.

```python
# apps/users/serializers.py
from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    """Fields vary by viewer's role."""

    class Meta:
        model = User
        fields = ["public_id", "name", "email", "role", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if not request:
            return

        viewer = request.user

        # Viewers cannot see email addresses
        if viewer.role == Role.VIEWER:
            self.fields.pop("email", None)

        # Only admins+ see role field
        if not has_at_least_role(viewer.role, Role.ADMIN):
            self.fields.pop("role", None)

class UserAdminSerializer(UserSerializer):
    """Full detail — only for admin views."""
    stripe_customer_id = serializers.CharField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["stripe_customer_id", "last_login", "mfa_enabled"]
```

---

## Permissions in the Bootstrap Response

Return what the current user can do — frontend drives UI from this.

```python
# apps/core/serializers.py
class PermissionSetSerializer(serializers.Serializer):
    can_invite_users   = serializers.SerializerMethodField()
    can_manage_billing = serializers.SerializerMethodField()
    can_export_data    = serializers.SerializerMethodField()
    can_delete_users   = serializers.SerializerMethodField()
    can_manage_roles   = serializers.SerializerMethodField()

    def get_can_invite_users(self, user):
        return has_at_least_role(user.role, Role.ADMIN)

    def get_can_manage_billing(self, user):
        return user.role == Role.OWNER

    def get_can_export_data(self, user):
        return (
            has_at_least_role(user.role, Role.MEMBER)
            and user.tenant.plan in ("pro", "enterprise")
        )

    def get_can_delete_users(self, user):
        return has_at_least_role(user.role, Role.ADMIN)

    def get_can_manage_roles(self, user):
        return has_at_least_role(user.role, Role.ADMIN)

# Bootstrap endpoint includes permissions
class BootstrapView(APIView):
    def get(self, request):
        return Response({
            "user":        UserSerializer(request.user).data,
            "permissions": PermissionSetSerializer(request.user).data,
            # ...
        })
```

```tsx
// React — read permissions from bootstrap, never hardcode role checks
const { permissions } = useBootstrap();

{permissions.can_invite_users && <InviteButton />}
{permissions.can_manage_billing && <BillingLink />}
{permissions.can_export_data && <ExportButton />}
```

---

## Object-Level Permission Tests

```python
# apps/orders/tests/test_permissions.py
import pytest
from rest_framework import status
from apps.orders.tests.factories import OrderFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

class TestOrderDeletePermissions:
    def test_member_can_delete_own_order(self, auth_client, user):
        order = OrderFactory(tenant=user.tenant, created_by=user)
        response = auth_client.delete(f"/api/v1/orders/{order.public_id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_member_cannot_delete_others_order(self, auth_client, user):
        other_user = UserFactory(tenant=user.tenant)
        order = OrderFactory(tenant=user.tenant, created_by=other_user)
        response = auth_client.delete(f"/api/v1/orders/{order.public_id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_delete_any_order(self, admin_client, user):
        order = OrderFactory(tenant=user.tenant)
        response = admin_client.delete(f"/api/v1/orders/{order.public_id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_viewer_cannot_see_email_in_user_list(self, client, tenant):
        viewer = UserFactory(tenant=tenant, role="viewer")
        token = get_token_for(viewer)
        client.cookies["access_token"] = token
        response = client.get("/api/v1/users/")
        assert "email" not in response.data["data"][0]
```

---

## Permission Checklist

- [ ] Role hierarchy enforced — owner > admin > member > viewer
- [ ] `PermissionChecker` used for all business logic checks — not inline `if user.role ==`
- [ ] Field-level permissions on serializers — viewers get fewer fields
- [ ] Permissions returned in bootstrap response — frontend never hardcodes role checks
- [ ] Object-level permissions tested for each role × action combination
- [ ] Cross-tenant access returns 404 — not 403
- [ ] Plan-gated features checked in `PermissionChecker` — not in views
- [ ] `get_permissions()` on ViewSets returns appropriate class per action
