# Audit Logging

Immutable record of who did what, when, and to what. Required for SOC2, GDPR, HIPAA, and incident investigation.

## Audit Log Model

```python
# apps/audit/models.py
from django.db import models
from django.contrib.postgres.fields import ArrayField

class AuditLog(models.Model):
    """
    Append-only. Never update or delete rows.
    Partition by created_at for performance at scale.
    """
    # Who
    tenant_id    = models.IntegerField(db_index=True)
    user_id      = models.IntegerField(null=True, db_index=True)    # null = system action
    user_email   = models.EmailField()                               # snapshot — don't FK
    user_role    = models.CharField(max_length=20)                   # snapshot at time of action
    ip_address   = models.GenericIPAddressField(null=True)
    user_agent   = models.TextField(blank=True)

    # What
    action       = models.CharField(max_length=100, db_index=True)  # "user.invite", "order.delete"
    resource     = models.CharField(max_length=50)                   # "user", "order", "invoice"
    resource_id  = models.CharField(max_length=26)                   # public_id of the resource

    # Context
    correlation_id = models.CharField(max_length=36, blank=True)     # ties to request logs
    changes        = models.JSONField(default=dict)                  # {field: [old, new]}
    metadata       = models.JSONField(default=dict)                  # extra context

    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        indexes  = [
            models.Index(fields=["tenant_id", "created_at"]),
            models.Index(fields=["tenant_id", "resource", "resource_id"]),
            models.Index(fields=["tenant_id", "user_id", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]
        # Prevent accidental updates/deletes
        default_permissions = ("add", "view")   # no change/delete permissions

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("AuditLog is immutable — never update a log entry")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog is immutable — never delete a log entry")
```

---

## Audit Logger

```python
# apps/audit/logger.py
import structlog
from django.db import transaction
from .models import AuditLog

logger = structlog.get_logger()

# Actions — define all upfront for consistency
class Action:
    # User
    USER_INVITED       = "user.invite"
    USER_DELETED       = "user.delete"
    USER_ROLE_CHANGED  = "user.role_change"
    USER_LOGIN         = "user.login"
    USER_LOGIN_FAILED  = "user.login_failed"
    USER_LOGOUT        = "user.logout"
    USER_MFA_ENABLED   = "user.mfa_enabled"
    USER_PASSWORD_RESET = "user.password_reset"

    # Data
    ORDER_CREATED  = "order.create"
    ORDER_UPDATED  = "order.update"
    ORDER_DELETED  = "order.delete"
    ORDER_EXPORTED = "order.export"

    # Billing
    PLAN_UPGRADED    = "billing.plan_upgrade"
    PLAN_DOWNGRADED  = "billing.plan_downgrade"
    PAYMENT_FAILED   = "billing.payment_failed"

    # Admin
    TENANT_SETTINGS_UPDATED = "tenant.settings_update"
    WEBHOOK_CREATED  = "integration.webhook_create"
    WEBHOOK_DELETED  = "integration.webhook_delete"

    # Data access (for GDPR/HIPAA)
    DATA_EXPORTED    = "data.export"
    DATA_DELETED     = "data.delete"

def log_action(
    action: str,
    resource: str,
    resource_id: str,
    user=None,
    tenant_id: int | None = None,
    request=None,
    changes: dict | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Write audit log entry.
    Always call via transaction.on_commit to avoid logging rolled-back actions.
    """
    entry_data = {
        "tenant_id":      tenant_id or (user.tenant_id if user else 0),
        "user_id":        user.id if user else None,
        "user_email":     user.email if user else "system",
        "user_role":      user.role if user else "system",
        "ip_address":     _get_ip(request) if request else None,
        "user_agent":     request.headers.get("user-agent", "") if request else "",
        "action":         action,
        "resource":       resource,
        "resource_id":    str(resource_id),
        "correlation_id": getattr(request, "correlation_id", "") if request else "",
        "changes":        changes or {},
        "metadata":       metadata or {},
    }

    # Write to DB
    def _write():
        AuditLog.objects.create(**entry_data)

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(_write)   # only write if transaction commits
    else:
        _write()

    # Also emit as structured log for SIEM / log aggregation
    logger.info("audit", **entry_data)

def _get_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
```

---

## Track Changes — Diff Helper

```python
# apps/audit/diff.py
from typing import Any

def diff_model(old_instance, new_instance, fields: list[str]) -> dict:
    """
    Return dict of changed fields: {field: [old_value, new_value]}.
    Only includes fields that actually changed.
    """
    changes = {}
    for field in fields:
        old = getattr(old_instance, field, None)
        new = getattr(new_instance, field, None)
        if old != new:
            changes[field] = [_serialize(old), _serialize(new)]
    return changes

def _serialize(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "public_id"):
        return value.public_id
    return value

# Usage in service
class UserService:
    def update_role(self, user, new_role: str, updated_by) -> None:
        old_role = user.role
        user.role = new_role
        user.save(update_fields=["role", "updated_at"])

        log_action(
            action=Action.USER_ROLE_CHANGED,
            resource="user",
            resource_id=user.public_id,
            user=updated_by,
            changes={"role": [old_role, new_role]},
            metadata={"target_user_id": user.public_id},
        )
```

---

## FastAPI Equivalent

```python
# audit/logger.py
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from .models import AuditLog

logger = structlog.get_logger()

async def log_action(
    session: AsyncSession,
    action: str,
    resource: str,
    resource_id: str,
    user=None,
    request=None,
    changes: dict | None = None,
    metadata: dict | None = None,
) -> None:
    entry = AuditLog(
        tenant_id     = user.tenant_id if user else 0,
        user_id       = user.id if user else None,
        user_email    = user.email if user else "system",
        user_role     = user.role if user else "system",
        ip_address    = request.client.host if request else None,
        user_agent    = request.headers.get("user-agent", "") if request else "",
        action        = action,
        resource      = resource,
        resource_id   = str(resource_id),
        correlation_id = request.state.correlation_id if request else "",
        changes       = changes or {},
        metadata      = metadata or {},
    )
    session.add(entry)
    # Don't call session.commit() here — let the caller's transaction commit it
    logger.info("audit", action=action, resource=resource, resource_id=resource_id,
                user_id=user.id if user else None, tenant_id=entry.tenant_id)
```

---

## Middleware — Auto-Log Auth Events

```python
# apps/audit/middleware.py — log all auth events automatically
from django.utils.deprecation import MiddlewareMixin
from .logger import log_action, Action

class AuditAuthMiddleware(MiddlewareMixin):
    """
    Automatically log login / logout events.
    Business actions (create, update, delete) are logged in services.
    """
    def process_response(self, request, response):
        # Login
        if request.path == "/api/v1/auth/login" and request.method == "POST":
            if response.status_code == 200:
                log_action(
                    action=Action.USER_LOGIN,
                    resource="user",
                    resource_id=response.data.get("user", {}).get("public_id", ""),
                    user=getattr(request, "user", None),
                    request=request,
                )
            elif response.status_code == 401:
                log_action(
                    action=Action.USER_LOGIN_FAILED,
                    resource="user",
                    resource_id="unknown",
                    request=request,
                    metadata={"email": request.data.get("email", "")},
                )
        return response
```

---

## Querying Audit Logs

```python
# apps/audit/views.py — expose audit log to admins
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from common.permissions import IsAdmin
from .models import AuditLog
from .serializers import AuditLogSerializer

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class   = AuditLogSerializer
    filterset_fields   = ["action", "resource", "user_id"]
    ordering           = ["-created_at"]

    def get_queryset(self):
        return AuditLog.objects.filter(
            tenant_id=self.request.user.tenant_id
        ).order_by("-created_at")

# GET /api/v1/audit?action=user.invite&resource=user
# GET /api/v1/audit?resource_id=01ARZ3NDEKTSV4RRFFQ69G5FAV
# GET /api/v1/audit?user_id=42
```

---

## Retention & Archival

```python
# apps/audit/tasks.py
from celery import shared_task

@shared_task
def archive_old_audit_logs() -> dict:
    """
    Move logs older than 1 year to S3.
    Never delete — audit logs must be kept for compliance.
    """
    import json
    import boto3
    from datetime import date, timedelta

    cutoff = date.today() - timedelta(days=365)
    old_logs = AuditLog.objects.filter(created_at__date__lt=cutoff)

    if not old_logs.exists():
        return {"archived": 0}

    s3 = boto3.client("s3")
    month = cutoff.strftime("%Y-%m")
    key  = f"audit-archive/{month}.jsonl"

    lines = "\n".join(
        json.dumps({
            "id":           log.id,
            "tenant_id":    log.tenant_id,
            "user_email":   log.user_email,
            "action":       log.action,
            "resource":     log.resource,
            "resource_id":  log.resource_id,
            "changes":      log.changes,
            "ip_address":   log.ip_address,
            "created_at":   log.created_at.isoformat(),
        })
        for log in old_logs.iterator(chunk_size=1000)
    )

    s3.put_object(
        Bucket=settings.AUDIT_ARCHIVE_BUCKET,
        Key=key,
        Body=lines.encode(),
        ContentType="application/x-jsonlines",
        ServerSideEncryption="AES256",
    )

    count = old_logs.count()
    # After successful archive — delete from DB to reclaim space
    old_logs.delete()
    return {"archived": count, "key": key}
```

---

## PostgreSQL — Prevent Tampering

```sql
-- Revoke UPDATE and DELETE on audit_logs from application role
-- Application can only INSERT and SELECT
REVOKE UPDATE, DELETE ON audit_logs FROM app_user;

-- Optional: use PostgreSQL row security to prevent even superuser deletes
-- (requires a separate DBA role)
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_insert_only ON audit_logs
    FOR INSERT WITH CHECK (true);
CREATE POLICY audit_select_own ON audit_logs
    FOR SELECT USING (tenant_id = current_setting('app.current_tenant_id')::int);
```

---

## What to Audit

| Category | Events |
|----------|--------|
| **Auth** | Login, failed login, logout, MFA enabled/disabled, password reset |
| **Users** | Invite, role change, deactivate, delete |
| **Data mutations** | Create, update, delete on sensitive resources (orders, invoices, patients) |
| **Data access** | Export, bulk download, report generation |
| **Settings** | Tenant settings changed, webhook added/removed |
| **Billing** | Plan change, payment method updated |
| **Admin** | Any action by support/admin staff on behalf of tenant |

## What NOT to Audit

- Read (GET) requests on non-sensitive data — too noisy
- Health checks, metrics scrapes
- Static asset requests

---

## Audit Log Checklist

- [ ] `AuditLog` model is append-only — `save()` raises if `pk` exists, `delete()` always raises
- [ ] DB permissions revoke `UPDATE` and `DELETE` on `audit_logs` from app role
- [ ] `transaction.on_commit` — never log actions from rolled-back transactions
- [ ] Changes captured as `[old, new]` diffs — not just "updated"
- [ ] IP address and User-Agent captured on every entry
- [ ] Correlation ID links audit log to request/trace log
- [ ] User email + role snapshotted at time of action — not FK to users table
- [ ] Auth events (login, logout, failed login) logged automatically via middleware
- [ ] Business actions (create, update, delete) logged in service layer
- [ ] Audit logs exposed to admins via read-only API
- [ ] Archival job moves logs > 1yr to S3 — never delete permanently
- [ ] Retention policy documented and meets compliance requirements (SOC2: 1yr, HIPAA: 6yr)
