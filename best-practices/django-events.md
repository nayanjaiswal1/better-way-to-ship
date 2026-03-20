# Django Events — Signals + Celery

Django equivalent of `events.md` (FastAPI uses Redis pub/sub + ARQ).
Django uses **signals** for in-process events and **Celery tasks** for async side effects.

## Domain Events via Django Signals

```python
# common/signals.py — define domain events as signals
from django.dispatch import Signal

# User events
user_invited      = Signal()   # provides: user, tenant, invited_by
user_role_changed = Signal()   # provides: user, old_role, new_role

# Order events
order_created   = Signal()     # provides: order
order_completed = Signal()     # provides: order
order_cancelled = Signal()     # provides: order, reason

# Billing events
subscription_created  = Signal()   # provides: tenant, plan
subscription_cancelled = Signal()  # provides: tenant
payment_failed        = Signal()   # provides: tenant, invoice
```

```python
# apps/orders/services.py — fire events from services, not models
from common.signals import order_created, order_completed

class OrderService:
    def create(self, data: dict, user) -> Order:
        order = Order.objects.create(
            tenant=user.tenant,
            created_by=user,
            **data,
        )
        # Fire domain event — decoupled from what handles it
        order_created.send(sender=Order, order=order)
        return order

    def complete(self, order: Order) -> None:
        order.status = "completed"
        order.save(update_fields=["status", "updated_at"])
        order_completed.send(sender=Order, order=order)
```

---

## Signal Handlers — Connect Side Effects

```python
# apps/orders/handlers.py
from django.dispatch import receiver
from common.signals import order_created, order_completed, order_cancelled
from .tasks import (
    send_order_confirmation_email,
    notify_slack_new_order,
    generate_invoice,
    send_cancellation_email,
)

@receiver(order_created)
def on_order_created(sender, order, **kwargs):
    """Async side effects — all via Celery tasks."""
    send_order_confirmation_email.delay(order.id)
    notify_slack_new_order.delay(order.id)

@receiver(order_completed)
def on_order_completed(sender, order, **kwargs):
    generate_invoice.delay(order.id)

@receiver(order_cancelled)
def on_order_cancelled(sender, order, reason, **kwargs):
    send_cancellation_email.delay(order.id, reason)
```

```python
# apps/orders/apps.py — register handlers on app ready
from django.apps import AppConfig

class OrdersConfig(AppConfig):
    name = "apps.orders"

    def ready(self):
        import apps.orders.handlers  # noqa — registers signal receivers
```

---

## Transactional Events — Fire After Commit

Signals fire immediately — but the DB transaction may roll back. Use `on_commit` to fire tasks only after the transaction succeeds.

```python
# apps/orders/services.py
from django.db import transaction

class OrderService:
    def create(self, data: dict, user) -> Order:
        with transaction.atomic():
            order = Order.objects.create(tenant=user.tenant, created_by=user, **data)

            # ✅ Only fires if transaction commits — safe for Celery
            transaction.on_commit(lambda: order_created.send(sender=Order, order=order))

        return order
```

```python
# Alternative — on_commit directly in handler
@receiver(order_created)
def on_order_created(sender, order, **kwargs):
    # Defer to after commit — avoids task starting before DB row is visible
    transaction.on_commit(
        lambda: send_order_confirmation_email.delay(order.id)
    )
```

---

## Notification System

```python
# apps/notifications/models.py
from django.db import models
from common.models import TenantScopedModel

class Notification(TenantScopedModel):
    user    = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="notifications")
    type    = models.CharField(max_length=50)
    title   = models.CharField(max_length=255)
    body    = models.TextField(blank=True)
    data    = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        indexes  = [models.Index(fields=["user", "read_at", "-created_at"])]

    @property
    def is_read(self):
        return self.read_at is not None
```

```python
# apps/notifications/services.py
from django.utils import timezone
from .models import Notification

class NotificationService:
    @staticmethod
    def create(user, type: str, title: str, body: str = "", data: dict = {}) -> Notification:
        n = Notification.objects.create(
            user=user,
            tenant=user.tenant,
            type=type,
            title=title,
            body=body,
            data=data,
        )
        # Push to SSE / WebSocket channel
        from .tasks import push_notification_to_user
        transaction.on_commit(lambda: push_notification_to_user.delay(n.id))
        return n

    @staticmethod
    def mark_read(user, notification_ids: list[int]) -> int:
        return Notification.objects.filter(
            user=user,
            id__in=notification_ids,
            read_at__isnull=True,
        ).update(read_at=timezone.now())
```

---

## Notification Preferences

```python
# apps/notifications/models.py
class NotificationPreference(models.Model):
    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="notification_prefs")

    # In-app
    order_updates_inapp   = models.BooleanField(default=True)
    billing_alerts_inapp  = models.BooleanField(default=True)

    # Email
    order_updates_email   = models.BooleanField(default=True)
    billing_alerts_email  = models.BooleanField(default=True)
    weekly_digest_email   = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_preferences"
```

```python
# Respect preferences before sending
@receiver(order_completed)
def on_order_completed(sender, order, **kwargs):
    prefs = NotificationPreference.objects.get(user=order.created_by)

    if prefs.order_updates_inapp:
        NotificationService.create(
            user=order.created_by,
            type="order.completed",
            title=f"Order {order.reference} completed",
        )

    if prefs.order_updates_email:
        transaction.on_commit(
            lambda: send_order_completion_email.delay(order.id)
        )
```

---

## SSE — Real-Time Notification Delivery

Push notifications to browser without polling.

```python
# apps/notifications/views.py
import json
from django.http import StreamingHttpResponse
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
import time

class NotificationStreamView(APIView):
    """SSE endpoint — browser connects once, receives pushes."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.id

        def event_stream():
            # Send unread count on connect
            unread = Notification.objects.filter(user_id=user_id, read_at__isnull=True).count()
            yield f"data: {json.dumps({'type': 'connected', 'unread': unread})}\n\n"

            last_check = time.time()
            while True:
                # Poll Redis for new notification signal (set by push_notification_to_user task)
                key = f"notification:push:{user_id}"
                notification_id = cache.get(key)

                if notification_id:
                    cache.delete(key)
                    try:
                        n = Notification.objects.get(id=notification_id)
                        payload = {
                            "type": "notification",
                            "id": n.id,
                            "title": n.title,
                            "body": n.body,
                            "notification_type": n.type,
                        }
                        yield f"data: {json.dumps(payload)}\n\n"
                    except Notification.DoesNotExist:
                        pass

                # Heartbeat every 30s to keep connection alive
                if time.time() - last_check > 30:
                    yield "data: {\"type\": \"ping\"}\n\n"
                    last_check = time.time()

                time.sleep(1)

        return StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",   # disable nginx buffering
            },
        )
```

```python
# apps/notifications/tasks.py
from celery import shared_task
from django.core.cache import cache

@shared_task
def push_notification_to_user(notification_id: int) -> None:
    """Signal the SSE stream that a new notification is ready."""
    from apps.notifications.models import Notification
    n = Notification.objects.select_related("user").get(id=notification_id)
    # Set a short-lived key — SSE stream picks it up
    cache.set(f"notification:push:{n.user_id}", notification_id, timeout=60)
```

---

## Email — Transactional via Celery

```python
# apps/notifications/tasks.py
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

@shared_task(max_retries=3, retry_backoff=True, autoretry_for=(Exception,))
def send_order_confirmation_email(order_id: int) -> None:
    from apps.orders.models import Order
    order = Order.all_objects.select_related("created_by", "tenant").get(id=order_id)

    prefs = order.created_by.notification_prefs
    if not prefs.order_updates_email:
        return

    html = render_to_string("emails/order_confirmation.html", {"order": order})
    text = render_to_string("emails/order_confirmation.txt", {"order": order})

    msg = EmailMultiAlternatives(
        subject=f"Order {order.reference} confirmed",
        body=text,
        from_email="orders@example.com",
        to=[order.created_by.email],
        headers={
            "List-Unsubscribe": f"<https://app.example.com/unsubscribe?token={order.created_by.unsubscribe_token}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    msg.attach_alternative(html, "text/html")
    msg.send()
```

---

## Webhook Events (Outbound)

```python
# apps/integrations/tasks.py
from celery import shared_task
import httpx, hmac, hashlib, json

@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_backoff_max=3600)
def deliver_webhook(self, webhook_endpoint_id: int, event_type: str, payload: dict) -> None:
    from apps.integrations.models import WebhookEndpoint, WebhookDelivery

    endpoint = WebhookEndpoint.objects.get(id=webhook_endpoint_id)
    body = json.dumps(payload)

    # HMAC-SHA256 signature
    sig = hmac.new(endpoint.secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    try:
        response = httpx.post(
            endpoint.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
                "X-Event-Type": event_type,
            },
            timeout=10,
        )
        response.raise_for_status()
        WebhookDelivery.objects.create(
            endpoint=endpoint, event_type=event_type,
            status_code=response.status_code, success=True,
        )
    except Exception as exc:
        WebhookDelivery.objects.create(
            endpoint=endpoint, event_type=event_type, success=False,
        )
        raise self.retry(exc=exc)

# Fire from signal handlers
@receiver(order_completed)
def on_order_completed_webhook(sender, order, **kwargs):
    from apps.integrations.models import WebhookEndpoint
    endpoints = WebhookEndpoint.objects.filter(
        tenant=order.tenant,
        is_active=True,
        events__contains=["order.completed"],
    )
    for endpoint in endpoints:
        transaction.on_commit(
            lambda ep=endpoint: deliver_webhook.delay(ep.id, "order.completed", {
                "order_id": order.public_id,
                "reference": order.reference,
                "amount": str(order.amount),
            })
        )
```

---

## Events Checklist

- [ ] Domain events defined as Django signals (`common/signals.py`)
- [ ] Signals fired from services — not from models `.save()`
- [ ] All signal handlers use `transaction.on_commit()` — tasks only fire if DB commits
- [ ] Celery tasks handle all async side effects — not inline in signal handlers
- [ ] Notification preferences respected before sending email or in-app
- [ ] SSE endpoint for real-time notification delivery
- [ ] Outbound webhooks signed with HMAC-SHA256
- [ ] Webhook delivery logged — retried on failure
- [ ] `apps.py` `ready()` imports handlers — signals registered at startup
