# Permissions (RBAC + ABAC)

## RBAC vs ABAC

| | RBAC | ABAC |
|--|------|------|
| Based on | User roles | User + resource + action attributes |
| Example | `admin` can delete users | User can edit **their own** posts only |
| Complexity | Low | Higher |
| Flexibility | Limited | High |

**Use both:** RBAC for coarse-grained access (admin vs member), ABAC for fine-grained (own resource only).

---

## Backend — Permission System

### Models

```python
# models/permission.py
from sqlalchemy import String, BigInteger, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))          # admin, member, viewer
    tenant_id: Mapped[int] = mapped_column(BigInteger)

class RolePermission(Base):
    __tablename__ = "role_permissions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(BigInteger)
    resource: Mapped[str] = mapped_column(String(50))      # users, posts, orders
    action: Mapped[str] = mapped_column(String(50))        # create, read, update, delete

    __table_args__ = (
        UniqueConstraint("role_id", "resource", "action"),
    )
```

### Permission Checker

```python
# core/permissions.py
from app.core.exceptions import ForbiddenError

class PermissionChecker:
    def __init__(self, user_permissions: dict[str, list[str]]):
        # { "users": ["read", "create"], "posts": ["read"] }
        self.permissions = user_permissions

    def can(self, resource: str, action: str) -> bool:
        return action in self.permissions.get(resource, [])

    def require(self, resource: str, action: str):
        if not self.can(resource, action):
            raise ForbiddenError(f"Cannot {action} {resource}")

    def can_own(self, resource: str, action: str, owner_id: int, current_user_id: int) -> bool:
        """ABAC — allow if user owns the resource, regardless of role."""
        if owner_id == current_user_id:
            return True
        return self.can(resource, action)

    def require_own(self, resource: str, action: str, owner_id: int, current_user_id: int):
        if not self.can_own(resource, action, owner_id, current_user_id):
            raise ForbiddenError(f"Cannot {action} this {resource}")
```

### FastAPI Dependency

```python
# dependencies/permissions.py
from fastapi import Depends
from app.core.permissions import PermissionChecker
from app.dependencies.auth import get_current_user
from app.services.permission_service import PermissionService

async def get_permissions(
    current_user=Depends(get_current_user),
    service: PermissionService = Depends(get_permission_service),
) -> PermissionChecker:
    """Loads permissions for current user — cached per request."""
    user_permissions = await service.get_permissions_for_user(current_user.id)
    return PermissionChecker(user_permissions)


# Usage in endpoints
@router.delete("/{public_id}")
async def delete_user(
    public_id: str,
    permissions: PermissionChecker = Depends(get_permissions),
    service: UserService = Depends(get_user_service),
):
    permissions.require("users", "delete")  # raises 403 if not allowed
    return await service.delete_user_by_public_id(public_id)


@router.patch("/posts/{public_id}")
async def update_post(
    public_id: str,
    data: PostUpdate,
    current_user=Depends(get_current_user),
    permissions: PermissionChecker = Depends(get_permissions),
    service: PostService = Depends(get_post_service),
):
    post = await service.get_by_public_id(public_id)
    # ABAC — owner can always edit, others need "update" permission
    permissions.require_own("posts", "update", post.user_id, current_user.id)
    return await service.update_post(post.id, data)
```

### Permission Service — cached per request

```python
# services/permission_service.py
class PermissionService:
    def __init__(self, repo: PermissionRepository):
        self.repo = repo
        self._cache: dict[int, dict] = {}

    async def get_permissions_for_user(self, user_id: int) -> dict[str, list[str]]:
        if user_id in self._cache:
            return self._cache[user_id]

        permissions = await self.repo.get_by_user(user_id)
        result = {}
        for p in permissions:
            result.setdefault(p.resource, []).append(p.action)

        self._cache[user_id] = result
        return result
```

---

## API Response — Permissions in Meta (SDUI)

Return resolved permissions in every response — UI reads from meta, never hardcodes.

```python
# api/v1/endpoints/users.py
@router.get("/", response_model=APIResponse[list[UserResponse]])
async def list_users(
    permissions: PermissionChecker = Depends(get_permissions),
    ...
):
    meta.permissions = [
        Permission(
            resource="users",
            actions=[a for a in ["create", "read", "update", "delete"]
                     if permissions.can("users", a)],
            fields={
                "email": {"visible": True, "editable": permissions.can("users", "update")},
                "role":  {"visible": permissions.can("users", "admin"), "editable": False},
            }
        )
    ]
    return APIResponse(data=users, meta=meta)
```

---

## React — Consume Permissions from Meta

```tsx
// hooks/usePermissions.ts
export function usePermissions(resource: string) {
  const { data } = useQuery({ queryKey: [resource, 'data'] });
  const perms = data?.meta?.permissions?.find((p: any) => p.resource === resource);

  return {
    can: (action: string) => perms?.actions?.includes(action) ?? false,
    fields: perms?.fields ?? {},
  };
}

// Usage — never hardcode role checks
function UsersPage() {
  const { can, fields } = usePermissions('users');

  return (
    <div>
      {can('create') && <CreateUserButton />}
      <DataTable
        columns={schema?.columns.filter(col =>
          fields[col.field]?.visible !== false  // field-level visibility
        )}
        rows={data}
        onEdit={can('update') ? handleEdit : undefined}
        onDelete={can('delete') ? handleDelete : undefined}
      />
    </div>
  );
}
```

---

## Checklist

- [ ] Roles and permissions stored in DB — not hardcoded
- [ ] `PermissionChecker` dependency injected in every mutating endpoint
- [ ] ABAC for own-resource checks
- [ ] Permissions returned in `meta.permissions` per response
- [ ] UI reads permissions from meta — never checks `user.role` directly
- [ ] Field-level permissions for sensitive fields (e.g. salary, role)
