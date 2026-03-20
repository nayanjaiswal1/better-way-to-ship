# Admin Panel — Internal Tools

Every SaaS needs an internal admin UI: impersonate users, manage tenants, view audit logs, handle support tickets.

## Architecture Decision

| Option | When to use |
|--------|------------|
| **Django Admin** (built-in) | Django backend, simple CRUD, internal team only |
| **react-admin** | Custom UI needed, complex workflows, FastAPI or Django |
| **Custom React + DRF/FastAPI** | Full control, matches your design system |

---

## Django Admin — Enhanced

Django admin is production-ready with a few additions.

```python
# apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display   = ["email", "name", "tenant_link", "role", "is_active", "created_at"]
    list_filter    = ["role", "is_active", "tenant__plan"]
    search_fields  = ["email", "name", "tenant__name"]
    ordering       = ["-created_at"]
    readonly_fields = ["public_id", "created_at", "updated_at", "last_login"]
    list_per_page  = 50
    list_select_related = ["tenant"]

    fieldsets = (
        (None,      {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "public_id", "tenant", "role")}),
        ("Flags",   {"fields": ("is_active", "is_staff", "mfa_enabled")}),
        ("Dates",   {"fields": ("created_at", "updated_at", "last_login")}),
    )
    exclude = ["mfa_secret"]

    def tenant_link(self, obj):
        url = f"/admin/tenants/tenant/{obj.tenant_id}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.tenant.name)
    tenant_link.short_description = "Tenant"

    # Custom action — impersonate user
    actions = ["impersonate"]

    def impersonate(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one user to impersonate.", level="error")
            return
        user = queryset.first()
        # Log impersonation in audit log
        from apps.audit.logger import log_action, Action
        log_action(
            action=Action.USER_IMPERSONATED,
            resource="user",
            resource_id=user.public_id,
            user=request.user,
            request=request,
            metadata={"impersonated_user": user.email},
        )
        from django.contrib.auth import login
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        from django.shortcuts import redirect
        return redirect("/")
    impersonate.short_description = "Impersonate selected user"
```

```python
# apps/tenants/admin.py
from django.contrib import admin
from django.db.models import Count
from .models import Tenant

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display  = ["name", "slug", "plan", "user_count", "is_active", "created_at"]
    list_filter   = ["plan", "is_active"]
    search_fields = ["name", "slug"]
    readonly_fields = ["public_id", "created_at", "updated_at"]
    ordering      = ["-created_at"]
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(user_count=Count("users"))

    def user_count(self, obj):
        return obj.user_count
    user_count.admin_order_field = "user_count"

    actions = ["upgrade_to_pro", "suspend"]

    def upgrade_to_pro(self, request, queryset):
        queryset.update(plan="pro")
        self.message_user(request, f"Upgraded {queryset.count()} tenants to Pro.")
    upgrade_to_pro.short_description = "Upgrade to Pro plan"

    def suspend(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"Suspended {queryset.count()} tenants.")
    suspend.short_description = "Suspend tenants"
```

### Secure Django Admin

```python
# config/settings/production.py
ADMIN_URL = env("ADMIN_URL", default="admin/")   # obscure the URL

# config/urls.py
urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    ...
]
```

```nginx
# Allow admin only from internal IPs
location /secret-admin-path/ {
    allow 10.0.0.0/8;     # internal VPN
    allow 192.168.0.0/16;
    deny all;
    proxy_pass http://api:8000;
}
```

---

## react-admin — Custom Admin UI

When you need a polished admin beyond Django admin, or you're using FastAPI.

```bash
npm create vite@latest admin -- --template react-ts
cd admin
npm install react-admin ra-data-json-server @mui/material @emotion/react @emotion/styled
```

### Data Provider — connects react-admin to your API

```tsx
// admin/src/dataProvider.ts
import { fetchUtils } from "react-admin";
import simpleRestProvider from "ra-data-simple-rest";

const httpClient = (url: string, options: RequestInit = {}) => {
  options.credentials = "include";   // send httpOnly cookies
  return fetchUtils.fetchJson(url, options);
};

export const dataProvider = simpleRestProvider(
  import.meta.env.VITE_API_URL + "/admin",
  httpClient,
);
```

### Auth Provider

```tsx
// admin/src/authProvider.ts
import { AuthProvider } from "react-admin";

export const authProvider: AuthProvider = {
  login: async ({ username, password }) => {
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: username, password }),
    });
    if (!res.ok) throw new Error("Invalid credentials");
    const data = await res.json();
    if (data.user.role !== "staff") throw new Error("Admin access required");
    localStorage.setItem("admin_user", JSON.stringify(data.user));
  },

  logout: async () => {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
    localStorage.removeItem("admin_user");
  },

  checkAuth: async () => {
    const user = localStorage.getItem("admin_user");
    if (!user) throw new Error("Not authenticated");
  },

  checkError: async ({ status }) => {
    if (status === 401 || status === 403) {
      localStorage.removeItem("admin_user");
      throw new Error("Session expired");
    }
  },

  getIdentity: async () => {
    const user = JSON.parse(localStorage.getItem("admin_user") || "{}");
    return { id: user.public_id, fullName: user.name, avatar: user.avatar };
  },

  getPermissions: async () => {
    const user = JSON.parse(localStorage.getItem("admin_user") || "{}");
    return user.role;
  },
};
```

### App Setup

```tsx
// admin/src/App.tsx
import { Admin, Resource, ListGuesser, EditGuesser } from "react-admin";
import { dataProvider } from "./dataProvider";
import { authProvider } from "./authProvider";
import { TenantList, TenantEdit } from "./resources/tenants";
import { UserList, UserEdit }     from "./resources/users";
import { AuditLogList }           from "./resources/auditLogs";

export default function App() {
  return (
    <Admin
      dataProvider={dataProvider}
      authProvider={authProvider}
      title="MyApp Admin"
      requireAuth
    >
      <Resource name="tenants"   list={TenantList}   edit={TenantEdit} />
      <Resource name="users"     list={UserList}     edit={UserEdit} />
      <Resource name="audit-logs" list={AuditLogList} />
    </Admin>
  );
}
```

### Resource — Tenants

```tsx
// admin/src/resources/tenants.tsx
import {
  List, Datagrid, TextField, DateField, SelectField,
  Edit, SimpleForm, TextInput, SelectInput,
  useRecordContext, useUpdate, useNotify,
  ChipField, BooleanField, NumberField,
  FilterButton, SearchInput, SelectArrayInput,
} from "react-admin";

const planChoices = [
  { id: "free",       name: "Free" },
  { id: "pro",        name: "Pro" },
  { id: "enterprise", name: "Enterprise" },
];

const tenantFilters = [
  <SearchInput source="q" alwaysOn />,
  <SelectInput source="plan" choices={planChoices} />,
  <SelectInput source="is_active" choices={[
    { id: true, name: "Active" },
    { id: false, name: "Suspended" },
  ]} />,
];

export function TenantList() {
  return (
    <List filters={tenantFilters} sort={{ field: "created_at", order: "DESC" }}>
      <Datagrid rowClick="edit" bulkActionButtons={false}>
        <TextField    source="name" />
        <TextField    source="slug" />
        <ChipField    source="plan" />
        <NumberField  source="user_count" label="Users" />
        <BooleanField source="is_active" label="Active" />
        <DateField    source="created_at" showTime />
      </Datagrid>
    </List>
  );
}

export function TenantEdit() {
  return (
    <Edit>
      <SimpleForm>
        <TextInput   source="name" />
        <SelectInput source="plan" choices={planChoices} />
        <SelectInput source="is_active" label="Status" choices={[
          { id: true, name: "Active" },
          { id: false, name: "Suspended" },
        ]} />
      </SimpleForm>
    </Edit>
  );
}
```

### Resource — Audit Logs (read-only)

```tsx
// admin/src/resources/auditLogs.tsx
import { List, Datagrid, TextField, DateField, JsonField } from "react-admin";

export function AuditLogList() {
  return (
    <List sort={{ field: "created_at", order: "DESC" }} perPage={50}>
      <Datagrid bulkActionButtons={false} rowClick={false}>
        <DateField    source="created_at" showTime />
        <TextField    source="user_email" />
        <TextField    source="action" />
        <TextField    source="resource" />
        <TextField    source="resource_id" />
        <TextField    source="ip_address" />
      </Datagrid>
    </List>
  );
}
```

---

## Admin API Endpoints

Separate admin endpoints from regular API — different auth, different permissions.

```python
# Django — admin-only DRF viewsets
# apps/admin_api/views.py
from rest_framework import viewsets
from common.permissions import IsStaff

class AdminTenantViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaff]   # staff flag, not tenant role
    queryset = Tenant.objects.annotate(user_count=Count("users")).order_by("-created_at")
    serializer_class = AdminTenantSerializer
    search_fields    = ["name", "slug"]
    filterset_fields = ["plan", "is_active"]

    def partial_update(self, request, *args, **kwargs):
        # Audit every admin change
        instance = self.get_object()
        old_data = AdminTenantSerializer(instance).data
        response = super().partial_update(request, *args, **kwargs)
        new_data = AdminTenantSerializer(instance).data
        log_action(
            action="admin.tenant_update",
            resource="tenant",
            resource_id=instance.public_id,
            user=request.user,
            request=request,
            changes=diff_dicts(old_data, new_data),
        )
        return response

class AdminUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaff]
    queryset = User.objects.select_related("tenant").order_by("-created_at")
    serializer_class = AdminUserSerializer

    @action(detail=True, methods=["post"])
    def impersonate(self, request, pk=None):
        """Generate a short-lived impersonation token."""
        user = self.get_object()
        token = generate_impersonation_token(user)
        log_action(
            action="admin.impersonate",
            resource="user",
            resource_id=user.public_id,
            user=request.user,
            request=request,
        )
        return Response({"token": token, "redirect": "/"})
```

```python
# config/urls.py — admin API under separate prefix
urlpatterns += [
    path("api/admin/", include("apps.admin_api.urls")),
]
```

```python
# common/permissions.py
class IsStaff(BasePermission):
    """Django staff flag — separate from tenant roles."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff
```

---

## Impersonation — Safe Pattern

```python
# apps/admin_api/impersonation.py
import secrets
from django.core.cache import cache
from rest_framework_simplejwt.tokens import RefreshToken

def generate_impersonation_token(target_user, admin_user) -> str:
    """
    Short-lived token — expires in 1 hour.
    Stored in Redis so it can be revoked.
    """
    token = secrets.token_urlsafe(32)
    cache.set(
        f"impersonation:{token}",
        {"user_id": target_user.id, "admin_id": admin_user.id},
        timeout=3600,   # 1 hour
    )
    return token

# apps/users/views.py — redeem impersonation token
class ImpersonateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token")
        data  = cache.get(f"impersonation:{token}")
        if not data:
            return Response(status=401)

        cache.delete(f"impersonation:{token}")   # one-time use

        from apps.users.models import User
        user = User.objects.get(id=data["user_id"])

        refresh  = RefreshToken.for_user(user)
        response = Response({"impersonating": user.email})
        response.set_cookie("access_token",  str(refresh.access_token), httponly=True, samesite="Strict")
        response.set_cookie("refresh_token", str(refresh),              httponly=True, samesite="Strict")
        # Store admin_id in session so the UI can show "impersonating as X"
        response.set_cookie("impersonating_as", user.email, httponly=False, samesite="Strict")
        return response
```

---

## Admin Panel Checklist

- [ ] Admin accessible only from internal IPs or VPN — not public internet
- [ ] Separate URL (`/secret-admin-path/`) — obscure but not sole protection
- [ ] Staff flag (`is_staff`) distinct from tenant roles — different permission class
- [ ] All admin actions logged in audit log with admin user's identity
- [ ] Impersonation tokens are short-lived (1hr), one-time use, logged
- [ ] UI shows "Impersonating as X" banner — never hidden from admin
- [ ] Django Admin excludes sensitive fields (`mfa_secret`, raw password)
- [ ] react-admin uses `credentials: include` — cookies, not localStorage tokens
- [ ] Bulk actions (suspend, upgrade plan) require confirmation dialog
- [ ] Read-only views for audit logs — no delete/edit in admin
