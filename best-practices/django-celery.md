# Django + Celery — Background Jobs

Celery is the Django equivalent of ARQ. Use Redis as the broker.

## Setup

```bash
pip install celery redis django-celery-beat django-celery-results flower
```

```python
# config/celery.py
import os
from celery import Celery
from celery.utils.log import get_task_logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("myapp")

# Load config from Django settings, namespace CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

logger = get_task_logger(__name__)
```

```python
# config/__init__.py — ensure Celery loads with Django
from .celery import app as celery_app

__all__ = ("celery_app",)
```

```python
# config/settings/base.py
CELERY_BROKER_URL               = env("REDIS_URL")
CELERY_RESULT_BACKEND           = "django-db"  # store results in DB via django-celery-results
CELERY_TASK_SERIALIZER          = "json"
CELERY_ACCEPT_CONTENT           = ["json"]
CELERY_TASK_TRACK_STARTED       = True
CELERY_TASK_TIME_LIMIT          = 5 * 60      # hard kill after 5 min
CELERY_TASK_SOFT_TIME_LIMIT     = 4 * 60      # raises SoftTimeLimitExceeded first
CELERY_WORKER_PREFETCH_MULTIPLIER = 1         # fair dispatch — 1 task per worker at a time
CELERY_ACKS_LATE                = True        # only ack after task completes
CELERY_TASK_REJECT_ON_WORKER_LOST = True      # re-queue if worker dies

# Celery Beat — scheduled tasks
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
```

---

## Defining Tasks

```python
# apps/users/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = get_task_logger(__name__)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,      # retry after 60s
    autoretry_for=(Exception,),  # auto retry on any exception
    retry_backoff=True,          # exponential backoff
    retry_backoff_max=600,       # max 10 min between retries
)
def send_invite_email(self, user_id: int) -> None:
    from apps.users.models import User
    try:
        user = User.objects.select_related("tenant").get(id=user_id)
        html = render_to_string("emails/invite.html", {"user": user})
        send_mail(
            subject=f"You're invited to {user.tenant.name}",
            message="",
            html_message=html,
            from_email="noreply@example.com",
            recipient_list=[user.email],
        )
        logger.info("Invite email sent", extra={"user_id": user_id})
    except User.DoesNotExist:
        logger.warning("User not found — skipping email", extra={"user_id": user_id})
        # Don't retry — user doesn't exist
        return

@shared_task(bind=True, max_retries=5, retry_backoff=True)
def process_webhook(self, payload: dict, webhook_id: int) -> None:
    """Process inbound webhook — idempotent."""
    from apps.integrations.models import WebhookDelivery
    from apps.integrations.services import WebhookService
    try:
        WebhookService().process(payload, webhook_id)
    except Exception as exc:
        logger.error("Webhook processing failed", extra={"webhook_id": webhook_id, "error": str(exc)})
        raise self.retry(exc=exc)
```

---

## Task Queues — Priority

Route different task types to different queues.

```python
# config/settings/base.py
CELERY_TASK_ROUTES = {
    "apps.users.tasks.send_invite_email":   {"queue": "emails"},
    "apps.billing.tasks.*":                 {"queue": "billing"},
    "apps.exports.tasks.*":                 {"queue": "exports"},
}

CELERY_TASK_DEFAULT_QUEUE = "default"
```

```bash
# Start workers per queue with appropriate concurrency
celery -A config worker -Q default   --concurrency=4 --loglevel=info
celery -A config worker -Q emails    --concurrency=8 --loglevel=info  # IO bound
celery -A config worker -Q billing   --concurrency=2 --loglevel=info  # critical
celery -A config worker -Q exports   --concurrency=2 --loglevel=info  # memory heavy
```

---

## Scheduled Tasks — Celery Beat

```python
# config/settings/base.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Run daily at 2am UTC
    "daily-data-cleanup": {
        "task": "apps.core.tasks.cleanup_expired_data",
        "schedule": crontab(hour=2, minute=0),
    },
    # Every 15 minutes
    "sync-stripe-subscriptions": {
        "task": "apps.billing.tasks.sync_stripe_subscriptions",
        "schedule": crontab(minute="*/15"),
    },
    # Weekly Sunday 3am
    "weekly-report": {
        "task": "apps.reporting.tasks.send_weekly_report",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
    },
}
```

```python
# apps/core/tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

@shared_task
def cleanup_expired_data() -> dict:
    """Soft-delete expired sessions and old temp files."""
    from apps.users.models import UserSession
    from apps.uploads.models import TempUpload

    cutoff = timezone.now() - timedelta(days=30)

    expired_sessions = UserSession.objects.filter(expires_at__lt=timezone.now()).delete()
    old_uploads = TempUpload.objects.filter(created_at__lt=cutoff).delete()

    return {
        "expired_sessions": expired_sessions[0],
        "old_uploads":      old_uploads[0],
    }
```

---

## Calling Tasks

```python
# From a Django view / service
from apps.users.tasks import send_invite_email

# Fire and forget
send_invite_email.delay(user.id)

# With countdown (delay in seconds)
send_invite_email.apply_async(args=[user.id], countdown=30)

# With ETA
from datetime import datetime, timedelta
send_invite_email.apply_async(
    args=[user.id],
    eta=datetime.utcnow() + timedelta(hours=1),
)

# Synchronous (testing only — never in production views)
send_invite_email.apply(args=[user.id])
```

---

## Chaining & Groups

```python
from celery import chain, group, chord

# Chain — run tasks sequentially, pass result to next
pipeline = chain(
    validate_export.s(export_id),
    generate_csv.s(),
    upload_to_s3.s(),
    notify_user.s(user_id),
)
pipeline.delay()

# Group — run tasks in parallel
tasks = group(
    send_invoice_email.s(user_id)
    for user_id in user_ids
)
tasks.delay()

# Chord — group + callback when all complete
result = chord(
    group(process_item.s(item_id) for item_id in item_ids),
    finalize_batch.s(batch_id),
)
result.delay()
```

---

## Idempotency — Safe Retries

```python
# apps/billing/tasks.py
from celery import shared_task
from django.db import transaction

@shared_task(bind=True, max_retries=3, retry_backoff=True)
def charge_subscription(self, subscription_id: int) -> None:
    """Idempotent — safe to retry. Check if already charged first."""
    from apps.billing.models import Subscription, Payment

    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(id=subscription_id)

        # Idempotency check — don't double charge
        period_start = subscription.current_period_start
        if Payment.objects.filter(subscription=subscription, period_start=period_start).exists():
            return  # already charged this period

        try:
            payment = subscription.charge()
            Payment.objects.create(
                subscription=subscription,
                period_start=period_start,
                amount=subscription.amount,
                stripe_payment_id=payment.id,
            )
        except Exception as exc:
            raise self.retry(exc=exc)
```

---

## Monitoring — Flower

```bash
# Run Flower — Celery monitoring UI
celery -A config flower --port=5555 --basic-auth=admin:secret

# Docker Compose
flower:
  image: mher/flower
  command: celery --broker=redis://redis:6379/0 flower
  ports:
    - "5555:5555"
  environment:
    - FLOWER_BASIC_AUTH=admin:secret
```

```yaml
# prometheus — celery metrics via celery-exporter
celery-exporter:
  image: danihodovic/celery-exporter
  command: --broker-url=redis://redis:6379/0
  ports:
    - "9808:9808"
```

```yaml
# Prometheus alert — stale queue
- alert: CeleryQueueStale
  expr: celery_queue_length{queue="default"} > 100
  for: 5m
  annotations:
    summary: "Celery default queue has {{ $value }} pending tasks"

- alert: CeleryWorkerDown
  expr: celery_workers < 1
  for: 2m
  annotations:
    summary: "No Celery workers running"
```

---

## KEDA — Scale Workers by Queue Depth

Scale workers to zero when queue is empty (same as ARQ setup in `kubernetes.md`).

```yaml
# k8s/keda-celery-worker.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: celery-worker
  namespace: production
spec:
  scaleTargetRef:
    name: celery-worker
  minReplicaCount: 0     # scale to zero
  maxReplicaCount: 20
  pollingInterval: 10
  cooldownPeriod: 60

  triggers:
    - type: redis
      metadata:
        address: redis:6379
        listName: celery   # Celery default queue key
        listLength: "5"    # 1 worker per 5 queued tasks
```

```yaml
# k8s/celery-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: worker
          image: myapp/api:1.0.0
          command:
            - celery
            - -A
            - config
            - worker
            - -Q
            - default,emails
            - --concurrency=4
            - --loglevel=info
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "1Gi"
          lifecycle:
            preStop:
              exec:
                # Finish current task before shutdown
                command: ["celery", "-A", "config", "control", "shutdown"]
          terminationGracePeriodSeconds: 300  # 5 min for long tasks
```

---

## Celery Checklist

- [ ] `CELERY_ACKS_LATE = True` — tasks re-queued if worker dies
- [ ] `CELERY_TASK_REJECT_ON_WORKER_LOST = True` — safe re-queue on worker crash
- [ ] `autoretry_for` + `retry_backoff` on all tasks
- [ ] Soft time limit set (`CELERY_TASK_SOFT_TIME_LIMIT`) — raises exception gracefully
- [ ] Hard time limit set (`CELERY_TASK_TIME_LIMIT`) — kills stuck tasks
- [ ] `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` — fair dispatch
- [ ] Tasks are idempotent — safe to run twice
- [ ] Separate queues for emails, billing, exports
- [ ] Celery Beat for scheduled tasks (not cron jobs on the server)
- [ ] Flower monitoring in staging
- [ ] KEDA scales workers to zero when queue is empty
- [ ] Prometheus alerts on queue depth and worker count
