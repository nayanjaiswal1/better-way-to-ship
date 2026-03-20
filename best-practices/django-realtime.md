# Django Realtime — Channels + SSE

## Decision Guide

| Need | Solution |
|------|----------|
| Server pushes updates to client | SSE (simple, HTTP) |
| Client and server send messages | WebSocket (Django Channels) |
| Simple notifications | SSE via `StreamingHttpResponse` — no extra infra |
| Chat, collaboration, games | Django Channels + WebSocket |
| Background job progress | SSE |
| Live dashboard metrics | SSE with polling fallback |

---

## SSE — Server-Sent Events (No Extra Infra)

Works with standard Django. No Channels needed for one-way pushes.

```bash
pip install django-eventstream   # optional helper, or DIY below
```

### DIY SSE

```python
# apps/core/views.py
import json
import time
from django.http import StreamingHttpResponse
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

class EventStreamView(APIView):
    """
    Generic SSE stream.
    Client subscribes once — server pushes events.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.id
        tenant_id = request.user.tenant_id

        def stream():
            # Initial state on connect
            yield self._event("connected", {"user_id": user_id})

            last_id = 0
            while True:
                # Check Redis for queued events
                events = cache.get(f"sse:{user_id}:events", [])
                new_events = [e for e in events if e["id"] > last_id]

                for event in new_events:
                    last_id = event["id"]
                    yield self._event(event["type"], event["data"], event_id=last_id)

                if not new_events:
                    # Heartbeat — keeps connection alive through proxies
                    yield ": heartbeat\n\n"

                time.sleep(1)

        response = StreamingHttpResponse(stream(), content_type="text/event-stream")
        response["Cache-Control"]    = "no-cache"
        response["X-Accel-Buffering"] = "no"   # disable nginx buffering
        return response

    @staticmethod
    def _event(event_type: str, data: dict, event_id: int | None = None) -> str:
        lines = []
        if event_id is not None:
            lines.append(f"id: {event_id}")
        lines.append(f"event: {event_type}")
        lines.append(f"data: {json.dumps(data)}")
        lines.append("\n")
        return "\n".join(lines)
```

```python
# Push event to user from anywhere (Celery task, signal handler, etc.)
import time
from django.core.cache import cache

def push_sse_event(user_id: int, event_type: str, data: dict) -> None:
    key = f"sse:{user_id}:events"
    events = cache.get(key, [])
    events.append({
        "id": int(time.time() * 1000),
        "type": event_type,
        "data": data,
    })
    # Keep last 50 events, expire after 5 minutes
    cache.set(key, events[-50:], timeout=300)
```

```tsx
// React — SSE hook
export function useSSE(url: string) {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    const es = new EventSource(url, { withCredentials: true });

    es.addEventListener('notification', (e) => {
      setEvents(prev => [...prev, JSON.parse(e.data)]);
    });

    es.addEventListener('order_update', (e) => {
      // Handle order update
    });

    es.onerror = () => {
      // Browser auto-reconnects after error
    };

    return () => es.close();
  }, [url]);

  return events;
}
```

---

## Django Channels — WebSocket

For bidirectional communication: chat, collaboration, live cursors.

```bash
pip install channels channels-redis daphne
```

```python
# config/settings/base.py
INSTALLED_APPS += ["channels", "daphne"]

ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL")]},
    }
}
```

```python
# config/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from apps.realtime.middleware import JWTWebSocketMiddleware
from apps.realtime.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        JWTWebSocketMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
```

### JWT Auth Middleware for WebSocket

```python
# apps/realtime/middleware.py
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

@database_sync_to_async
def get_user_from_token(token_str):
    try:
        token = AccessToken(token_str)
        from apps.users.models import User
        return User.objects.get(id=token["user_id"])
    except Exception:
        return AnonymousUser()

class JWTWebSocketMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Extract token from cookie
        cookies = {}
        for header in scope.get("headers", []):
            if header[0] == b"cookie":
                for part in header[1].decode().split("; "):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

        token = cookies.get("access_token")
        scope["user"] = await get_user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
```

### WebSocket Consumer

```python
# apps/realtime/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4001)
            return

        self.user_id   = user.id
        self.tenant_id = user.tenant_id
        self.user_group = f"user_{user.id}"
        self.tenant_group = f"tenant_{user.tenant_id}"

        # Join personal and tenant groups
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.channel_layer.group_add(self.tenant_group, self.channel_name)
        await self.accept()

        # Send unread count on connect
        unread = await self.get_unread_count()
        await self.send(json.dumps({"type": "connected", "unread": unread}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.user_group, self.channel_name)
        await self.channel_layer.group_discard(self.tenant_group, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data["type"] == "mark_read":
            await self.mark_notifications_read(data.get("ids", []))
            await self.send(json.dumps({"type": "marked_read", "ids": data["ids"]}))

    # Handler — called when group_send delivers this event type
    async def notification(self, event):
        await self.send(json.dumps({
            "type": "notification",
            "title": event["title"],
            "body":  event.get("body", ""),
            "notification_type": event["notification_type"],
        }))

    async def order_update(self, event):
        await self.send(json.dumps({
            "type": "order_update",
            "order_id": event["order_id"],
            "status": event["status"],
        }))

    @database_sync_to_async
    def get_unread_count(self):
        from apps.notifications.models import Notification
        return Notification.objects.filter(user_id=self.user_id, read_at__isnull=True).count()

    @database_sync_to_async
    def mark_notifications_read(self, ids: list[int]):
        from apps.notifications.models import Notification
        from django.utils import timezone
        Notification.objects.filter(
            user_id=self.user_id, id__in=ids
        ).update(read_at=timezone.now())
```

### URL Routing

```python
# apps/realtime/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/notifications/$", consumers.NotificationConsumer.as_asgi()),
    re_path(r"ws/orders/(?P<order_id>[^/]+)/$", consumers.OrderConsumer.as_asgi()),
]
```

### Push from Celery Task

```python
# apps/notifications/tasks.py
from celery import shared_task
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

@shared_task
def push_notification_to_user(notification_id: int) -> None:
    from apps.notifications.models import Notification
    n = Notification.objects.select_related("user").get(id=notification_id)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{n.user_id}",
        {
            "type": "notification",        # maps to consumer method
            "title": n.title,
            "body": n.body,
            "notification_type": n.type,
        },
    )

@shared_task
def broadcast_to_tenant(tenant_id: int, event_type: str, data: dict) -> None:
    """Broadcast to all connected users in a tenant."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"tenant_{tenant_id}",
        {"type": event_type, **data},
    )
```

---

## React WebSocket Hook

```tsx
// hooks/useWebSocket.ts
export function useWebSocket(path: string) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const handlers = useRef<Record<string, (data: unknown) => void>>({});

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}${path}`);
    wsRef.current = ws;

    ws.onopen  = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 3s
      setTimeout(() => wsRef.current = null, 3000);
    };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      handlers.current[msg.type]?.(msg);
    };

    return () => ws.close();
  }, [path]);

  const on = useCallback((type: string, handler: (data: unknown) => void) => {
    handlers.current[type] = handler;
  }, []);

  const send = useCallback((data: Record<string, unknown>) => {
    wsRef.current?.send(JSON.stringify(data));
  }, []);

  return { connected, on, send };
}

// Usage
function NotificationBell() {
  const [unread, setUnread] = useState(0);
  const { on } = useWebSocket('/ws/notifications/');

  useEffect(() => {
    on('connected',    (d: any) => setUnread(d.unread));
    on('notification', (d: any) => setUnread(c => c + 1));
  }, [on]);

  return <Bell count={unread} />;
}
```

---

## Deployment — Daphne (ASGI)

```dockerfile
# Dockerfile
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
```

```yaml
# docker-compose.yml
api:
  command: daphne -b 0.0.0.0 -p 8000 config.asgi:application
  depends_on:
    - redis
    - postgres

# Separate worker for Celery
worker:
  command: celery -A config worker -Q default,emails --concurrency=4
```

```yaml
# nginx — WebSocket upgrade
location /ws/ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "Upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;  # keep WS alive for 24h
}

location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header X-Real-IP $remote_addr;
}

# SSE — disable buffering
location /api/v1/events/ {
    proxy_pass http://api:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header X-Accel-Buffering no;
}
```

---

## Realtime Checklist

- [ ] SSE used for one-way server pushes (notifications, job progress)
- [ ] WebSocket (Channels) only for bidirectional needs (chat, collaboration)
- [ ] JWT auth middleware for WebSocket connections
- [ ] Channel groups for user-level and tenant-level broadcasts
- [ ] `async_to_sync` used in Celery tasks to push via channel layer
- [ ] Nginx configured with WebSocket upgrade headers
- [ ] SSE nginx buffering disabled (`proxy_buffering off`)
- [ ] Daphne (or Uvicorn) serving ASGI — not Gunicorn (WSGI)
- [ ] Redis channel layer — not in-memory (doesn't work multi-process)
- [ ] React auto-reconnects on WebSocket close
