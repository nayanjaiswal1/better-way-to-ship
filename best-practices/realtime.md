# Real-time Patterns

## When to Use What

| Pattern | When to use | Overhead |
|---------|-------------|----------|
| **Polling** | Simple, infrequent updates, works everywhere | High — constant requests |
| **SSE** | Server pushes to client, notifications, live feeds | Low — single HTTP connection |
| **WebSocket** | Bidirectional, chat, collaboration, gaming | Medium — persistent connection |

**Default choice: SSE** — simpler than WebSocket, works with HTTP/2, no special infrastructure needed.

---

## Polling (Simplest — Use Only as Last Resort)

```tsx
// React Query has built-in polling via refetchInterval
function LiveOrderStatus({ orderId }: { orderId: number }) {
  const { data } = useQuery({
    queryKey: ['orders', orderId],
    queryFn: () =>
      fetch(`/api/v1/orders/${orderId}`, { credentials: 'include' }).then(r => r.json()),
    refetchInterval: (data) =>
      // Stop polling once order is complete — smart polling
      data?.status === 'completed' ? false : 5000,  // poll every 5s until done
  });

  return <OrderStatus status={data?.status} />;
}
```

---

## Server-Sent Events (SSE) — Recommended

Server pushes updates over a single long-lived HTTP connection. No WebSocket infrastructure needed.

### Backend

```python
# api/v1/endpoints/events.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json

router = APIRouter()

@router.get("/events")
async def event_stream(current_user=Depends(get_current_user)):
    """SSE endpoint — client connects once, server pushes events."""

    async def generate():
        try:
            while True:
                # Fetch events for this user from Redis pub/sub or DB
                events = await get_pending_events(current_user.id)

                for event in events:
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event['payload'])}\n\n"

                await asyncio.sleep(1)  # check for new events every second
        except asyncio.CancelledError:
            pass  # client disconnected — clean up

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )

# Push events from anywhere in the app
async def push_event(user_id: int, event_type: str, payload: dict):
    await redis_client.lpush(
        f"events:{user_id}",
        json.dumps({"type": event_type, "payload": payload}),
    )
```

### React — useSSE hook, write once

```tsx
// hooks/useSSE.ts
import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export function useSSE() {
  const queryClient = useQueryClient();
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const source = new EventSource('/api/v1/events', { withCredentials: true });
    sourceRef.current = source;

    // Notification pushed from server
    source.addEventListener('notification', (e) => {
      const payload = JSON.parse(e.data);
      queryClient.setQueryData(['notifications'], (old: any[] = []) => [payload, ...old]);
    });

    // Data updated — invalidate relevant query cache
    source.addEventListener('user_updated', (e) => {
      const { id } = JSON.parse(e.data);
      queryClient.invalidateQueries({ queryKey: ['users', id] });
    });

    source.addEventListener('order_completed', (e) => {
      const { id } = JSON.parse(e.data);
      queryClient.invalidateQueries({ queryKey: ['orders', id] });
    });

    source.onerror = () => {
      // Auto-reconnect after 5s on error
      source.close();
      setTimeout(() => {
        sourceRef.current = new EventSource('/api/v1/events', { withCredentials: true });
      }, 5000);
    };

    return () => source.close();  // cleanup on unmount
  }, [queryClient]);
}

// App.tsx — connect once at root
function App() {
  useSSE();  // single connection for the entire app
  return <Router />;
}
```

---

## WebSocket — Bidirectional

Use only when you need client → server push (chat, collaboration, live cursors).

### Backend

```python
# api/v1/endpoints/ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.ws_manager import ConnectionManager

router = APIRouter()
manager = ConnectionManager()

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    current_user=Depends(get_current_user_ws),  # auth via query param or cookie
):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Broadcast to all clients in room
            await manager.broadcast(room_id, {
                "user": current_user.id,
                "message": data.get("message"),
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

# core/ws_manager.py
class ConnectionManager:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, room_id: str):
        await ws.accept()
        self.rooms.setdefault(room_id, []).append(ws)

    def disconnect(self, ws: WebSocket, room_id: str):
        self.rooms.get(room_id, []).remove(ws)

    async def broadcast(self, room_id: str, message: dict):
        for ws in self.rooms.get(room_id, []):
            await ws.send_json(message)
```

### React

```tsx
// hooks/useWebSocket.ts
import { useEffect, useRef, useCallback } from 'react';

export function useWebSocket(roomId: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  useEffect(() => {
    const ws = new WebSocket(`wss://api.example.com/ws/${roomId}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      setMessages(prev => [...prev, JSON.parse(e.data)]);
    };

    ws.onclose = () => {
      // Reconnect after 3s
      setTimeout(() => {
        wsRef.current = new WebSocket(`wss://api.example.com/ws/${roomId}`);
      }, 3000);
    };

    return () => ws.close();
  }, [roomId]);

  const send = useCallback((message: string) => {
    wsRef.current?.send(JSON.stringify({ message }));
  }, []);

  return { messages, send };
}
```

---

## Decision Guide

```
Does the client need to SEND data to server in real-time?
  YES → WebSocket (chat, collaboration, live cursors)
  NO  ↓

Is the update frequency > once per 30 seconds?
  YES → SSE (notifications, live feeds, order status)
  NO  ↓

Is simplicity more important than efficiency?
  YES → Polling with refetchInterval
  NO  → SSE
```
