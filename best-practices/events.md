# Event-Driven Architecture & Notifications

## Domain Events

Decouple services — when something happens, publish an event. Other services react independently. No tight coupling.

```
UserCreated → send welcome email
            → create default workspace
            → track analytics
            → notify Slack

All triggered by one event — services don't know about each other.
```

### Domain Event Base

```python
# core/events.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from ulid import ULID

@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]
    tenant_id: int
    user_id: int | None = None
    event_id: str = field(default_factory=lambda: str(ULID()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### Event Publisher — Redis Pub/Sub

```python
# core/event_bus.py
import json
import redis.asyncio as redis
from app.core.events import DomainEvent
from dataclasses import asdict

class EventBus:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def publish(self, event: DomainEvent):
        channel = f"events:{event.tenant_id}:{event.event_type}"
        await self.redis.publish(channel, json.dumps(asdict(event), default=str))

# Dependency
async def get_event_bus(redis=Depends(get_redis)) -> EventBus:
    return EventBus(redis)
```

### Publishing Events from Services

```python
# services/user_service.py
class UserService:
    def __init__(self, repo: UserRepository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus

    async def create_user(self, data: UserCreate) -> UserResponse:
        user = await self.repo.create(User(
            email=data.email,
            hashed_password=hash_password(data.password),
        ))

        # Publish event — subscribers react independently
        await self.event_bus.publish(DomainEvent(
            event_type="user.created",
            payload={"user_id": user.id, "email": user.email},
            tenant_id=user.tenant_id,
        ))

        return UserResponse.model_validate(user)
```

### Event Subscribers (ARQ workers)

```python
# workers/user_events.py
import json
import redis.asyncio as redis
from app.services.email_service import EmailService
from app.services.workspace_service import WorkspaceService

async def subscribe_user_events(redis_client: redis.Redis):
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("events:*:user.created")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        event = json.loads(message["data"])
        await handle_user_created(event)

async def handle_user_created(event: dict):
    # Each handler is independent — one failure doesn't affect others
    await EmailService().send_welcome(event["payload"]["email"])
    await WorkspaceService().create_default(event["payload"]["user_id"])
```

---

## Email / Notifications

### Transactional Emails — ARQ + SMTP/SES

```python
# services/email_service.py
from jinja2 import Environment, FileSystemLoader
import httpx

jinja = Environment(loader=FileSystemLoader("templates/email"))

class EmailService:
    async def send(self, to: str, subject: str, template: str, context: dict):
        html = jinja.get_template(f"{template}.html").render(**context)

        # Use SES, SendGrid, Postmark — not raw SMTP in production
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                json={
                    "to": [{"email": to}],
                    "from": {"email": settings.FROM_EMAIL},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html}],
                },
            )

    async def send_welcome(self, to: str, name: str):
        await self.send(to, "Welcome!", "welcome", {"name": name})

    async def send_password_reset(self, to: str, reset_url: str):
        await self.send(to, "Reset your password", "password_reset", {"reset_url": reset_url})
```

### In-App Notifications

```python
# models/notification.py
class Notification(Base, SoftDeleteMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(26), default=lambda: str(ULID()), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(50))       # info, warning, success, error
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "read_at",
              postgresql_where="read_at IS NULL"),
    )
```

```python
# services/notification_service.py
class NotificationService:
    async def create(self, user_id: int, tenant_id: int, type: str,
                     title: str, body: str | None = None, action_url: str | None = None):
        notif = await self.repo.create(Notification(
            user_id=user_id,
            tenant_id=tenant_id,
            type=type,
            title=title,
            body=body,
            action_url=action_url,
        ))

        # Push to client immediately via SSE (see realtime.md)
        await self.event_bus.publish(DomainEvent(
            event_type="notification.created",
            payload=NotificationResponse.model_validate(notif).model_dump(),
            tenant_id=tenant_id,
            user_id=user_id,
        ))

        return notif

    async def mark_read(self, notification_id: int, user_id: int):
        await self.repo.mark_read(notification_id, user_id)

    async def get_unread_count(self, user_id: int) -> int:
        return await self.repo.count_unread(user_id)
```

### React — Notifications via SSE

```tsx
// Already handled in realtime.md SSE setup:
source.addEventListener('notification.created', (e) => {
  const notification = JSON.parse(e.data);
  queryClient.setQueryData(['notifications'], (old: any[] = []) =>
    [notification, ...old]
  );
  queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] });
});

// hooks/useNotifications.ts
export function useNotifications() {
  return useQuery({
    queryKey: ['notifications'],
    queryFn: () =>
      fetch('/api/v1/notifications', { credentials: 'include' }).then(r => r.json()),
    staleTime: 1000 * 60,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () =>
      fetch('/api/v1/notifications/unread-count', { credentials: 'include' })
        .then(r => r.json()),
    staleTime: 0,  // always fresh
  });
}

// NotificationBell.tsx
function NotificationBell() {
  const { data: count } = useUnreadCount();
  const { data: notifications } = useNotifications();

  return (
    <Popover>
      <PopoverTrigger>
        <BellIcon />
        {count > 0 && <Badge>{count}</Badge>}
      </PopoverTrigger>
      <PopoverContent>
        {notifications?.map(n => <NotificationItem key={n.public_id} notification={n} />)}
      </PopoverContent>
    </Popover>
  );
}
```

---

## Notification Preferences

Let users control what they receive — never hardcode notification types.

```python
# models/notification_preference.py
class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    tenant_id: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(50))      # e.g. "order.completed"
    email: Mapped[bool] = mapped_column(default=True)
    in_app: Mapped[bool] = mapped_column(default=True)

# services/notification_service.py
async def should_notify(self, user_id: int, type: str, channel: str) -> bool:
    pref = await self.repo.get_preference(user_id, type)
    if not pref:
        return True  # default: notify
    return getattr(pref, channel, True)
```
