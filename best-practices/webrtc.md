# WebRTC — Real-Time Peer-to-Peer Communication

WebRTC enables direct browser-to-browser audio, video, and data transfer. The server only helps peers find each other (signaling) — media flows directly between clients.

## How It Works

```
1. Peer A creates an "offer" (SDP — session description)
2. Offer sent to Peer B via your signaling server (WebSocket)
3. Peer B creates an "answer", sends back via signaling
4. Both peers exchange ICE candidates (network path discovery)
5. Direct peer connection established — media/data flows P2P
6. TURN server relays if direct connection is blocked by NAT/firewall
```

---

## Signaling Server — Django Channels

```python
# apps/rtc/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class SignalingConsumer(AsyncWebsocketConsumer):
    """
    Relay WebRTC signaling messages between peers.
    Never touches media — only SDP offers/answers and ICE candidates.
    """

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4001)
            return

        self.user_id = user.id
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group = f"rtc_room_{self.room_id}"

        # Verify user has access to this room
        if not await self.can_join_room(self.room_id, user):
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        # Notify others a new peer joined
        await self.channel_layer.group_send(self.room_group, {
            "type":    "peer_joined",
            "user_id": self.user_id,
            "channel": self.channel_name,
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group, self.channel_name)
        await self.channel_layer.group_send(self.room_group, {
            "type":    "peer_left",
            "user_id": self.user_id,
        })

    async def receive(self, text_data):
        msg = json.loads(text_data)
        msg_type = msg.get("type")

        if msg_type == "offer":
            # Forward offer to specific peer
            await self.channel_layer.send(msg["to_channel"], {
                "type":        "rtc_offer",
                "sdp":         msg["sdp"],
                "from_user":   self.user_id,
                "from_channel": self.channel_name,
            })

        elif msg_type == "answer":
            await self.channel_layer.send(msg["to_channel"], {
                "type":      "rtc_answer",
                "sdp":       msg["sdp"],
                "from_user": self.user_id,
            })

        elif msg_type == "ice_candidate":
            await self.channel_layer.send(msg["to_channel"], {
                "type":      "ice_candidate",
                "candidate": msg["candidate"],
                "from_user": self.user_id,
            })

    # Channel layer event handlers — forward to WebSocket client
    async def peer_joined(self, event):
        await self.send(json.dumps({
            "type":    "peer_joined",
            "user_id": event["user_id"],
            "channel": event["channel"],
        }))

    async def peer_left(self, event):
        await self.send(json.dumps({
            "type":    "peer_left",
            "user_id": event["user_id"],
        }))

    async def rtc_offer(self, event):
        await self.send(json.dumps({
            "type":         "offer",
            "sdp":          event["sdp"],
            "from_user":    event["from_user"],
            "from_channel": event["from_channel"],
        }))

    async def rtc_answer(self, event):
        await self.send(json.dumps({
            "type":      "answer",
            "sdp":       event["sdp"],
            "from_user": event["from_user"],
        }))

    async def ice_candidate(self, event):
        await self.send(json.dumps({
            "type":      "ice_candidate",
            "candidate": event["candidate"],
            "from_user": event["from_user"],
        }))

    @database_sync_to_async
    def can_join_room(self, room_id: str, user) -> bool:
        from .models import Room
        return Room.objects.filter(
            public_id=room_id,
            tenant=user.tenant,
        ).exists()
```

```python
# apps/rtc/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/rtc/(?P<room_id>[^/]+)/$", consumers.SignalingConsumer.as_asgi()),
]
```

---

## Signaling Server — FastAPI

```python
# api/v1/rtc.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import json

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # room_id → {user_id: websocket}
        self.rooms: dict[str, dict[int, WebSocket]] = {}

    async def join(self, room_id: str, user_id: int, ws: WebSocket):
        self.rooms.setdefault(room_id, {})[user_id] = ws

    def leave(self, room_id: str, user_id: int):
        if room_id in self.rooms:
            self.rooms[room_id].pop(user_id, None)

    async def send_to(self, room_id: str, user_id: int, data: dict):
        ws = self.rooms.get(room_id, {}).get(user_id)
        if ws:
            await ws.send_text(json.dumps(data))

    async def broadcast(self, room_id: str, data: dict, exclude_user: int | None = None):
        for uid, ws in list(self.rooms.get(room_id, {}).items()):
            if uid != exclude_user:
                await ws.send_text(json.dumps(data))

manager = ConnectionManager()

@router.websocket("/ws/rtc/{room_id}")
async def rtc_signaling(
    websocket: WebSocket,
    room_id: str,
    current_user = Depends(get_current_user_ws),
):
    await websocket.accept()
    await manager.join(room_id, current_user.id, websocket)

    # Notify others
    await manager.broadcast(room_id, {
        "type": "peer_joined", "user_id": current_user.id
    }, exclude_user=current_user.id)

    try:
        while True:
            data = json.loads(await websocket.receive_text())

            if data["type"] in ("offer", "answer", "ice_candidate"):
                await manager.send_to(room_id, data["to_user"], {
                    **data, "from_user": current_user.id
                })

    except WebSocketDisconnect:
        manager.leave(room_id, current_user.id)
        await manager.broadcast(room_id, {
            "type": "peer_left", "user_id": current_user.id
        })
```

---

## STUN / TURN Server

STUN: helps peers discover their public IP.
TURN: relays media when P2P is blocked (corporate firewalls, symmetric NAT). ~15-20% of connections need TURN.

```bash
# Self-hosted TURN with coturn
docker run -d \
  --name coturn \
  --network=host \
  coturn/coturn \
  -n \
  --lt-cred-mech \
  --fingerprint \
  --use-auth-secret \
  --static-auth-secret=your-secret-here \
  --realm=turn.example.com \
  --total-quota=100 \
  --bps-capacity=0 \
  --stale-nonce \
  --log-file=stdout
```

```python
# api/v1/rtc.py — generate short-lived TURN credentials
import hmac, hashlib, base64, time

def generate_turn_credentials(ttl: int = 86400) -> dict:
    """
    Time-limited TURN credentials — rotate every 24h.
    Client can't use stale credentials.
    """
    timestamp = int(time.time()) + ttl
    username  = f"{timestamp}:webrtc"
    password  = base64.b64encode(
        hmac.new(
            settings.TURN_SECRET.encode(),
            username.encode(),
            hashlib.sha1,
        ).digest()
    ).decode()

    return {
        "username":   username,
        "credential": password,
        "ttl":        ttl,
        "uris": [
            f"stun:turn.example.com:3478",
            f"turn:turn.example.com:3478?transport=udp",
            f"turn:turn.example.com:3478?transport=tcp",
            f"turns:turn.example.com:5349?transport=tcp",  # TLS TURN
        ],
    }

@router.get("/rtc/turn-credentials")
async def get_turn_credentials(current_user: User = Depends(get_current_user)):
    return generate_turn_credentials()
```

---

## React — WebRTC Hook

```tsx
// hooks/useWebRTC.ts
interface UseWebRTCOptions {
  roomId: string;
  onRemoteStream?: (userId: number, stream: MediaStream) => void;
  onPeerLeft?: (userId: number) => void;
}

export function useWebRTC({ roomId, onRemoteStream, onPeerLeft }: UseWebRTCOptions) {
  const wsRef          = useRef<WebSocket | null>(null);
  const peersRef       = useRef<Record<number, RTCPeerConnection>>({});
  const localStreamRef = useRef<MediaStream | null>(null);
  const [connected, setConnected] = useState(false);
  const [peers, setPeers]         = useState<number[]>([]);

  const getIceServers = useCallback(async () => {
    const res = await fetch("/api/v1/rtc/turn-credentials", { credentials: "include" });
    const creds = await res.json();
    return [
      { urls: "stun:stun.l.google.com:19302" },   // public STUN fallback
      {
        urls:       creds.uris,
        username:   creds.username,
        credential: creds.credential,
      },
    ];
  }, []);

  const createPeerConnection = useCallback(async (userId: number, isInitiator: boolean) => {
    const iceServers = await getIceServers();
    const pc = new RTCPeerConnection({ iceServers });

    // Add local tracks to the connection
    localStreamRef.current?.getTracks().forEach(track => {
      pc.addTrack(track, localStreamRef.current!);
    });

    // When we get remote tracks
    pc.ontrack = (event) => {
      onRemoteStream?.(userId, event.streams[0]);
    };

    // Send ICE candidates via signaling
    pc.onicecandidate = (event) => {
      if (event.candidate) {
        wsRef.current?.send(JSON.stringify({
          type:      "ice_candidate",
          to_user:   userId,
          candidate: event.candidate,
        }));
      }
    };

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "failed") {
        pc.restartIce();  // auto-recover
      }
    };

    peersRef.current[userId] = pc;

    // Initiator creates and sends offer
    if (isInitiator) {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(JSON.stringify({
        type:    "offer",
        to_user: userId,
        sdp:     offer,
      }));
    }

    return pc;
  }, [getIceServers, onRemoteStream]);

  const handleSignalingMessage = useCallback(async (msg: Record<string, unknown>) => {
    switch (msg.type) {
      case "peer_joined": {
        const userId = msg.user_id as number;
        setPeers(p => [...p, userId]);
        // Existing peers initiate offer to newcomer
        await createPeerConnection(userId, true);
        break;
      }

      case "peer_left": {
        const userId = msg.user_id as number;
        peersRef.current[userId]?.close();
        delete peersRef.current[userId];
        setPeers(p => p.filter(id => id !== userId));
        onPeerLeft?.(userId);
        break;
      }

      case "offer": {
        const userId = msg.from_user as number;
        const pc = await createPeerConnection(userId, false);
        await pc.setRemoteDescription(msg.sdp as RTCSessionDescriptionInit);
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        wsRef.current?.send(JSON.stringify({
          type:    "answer",
          to_user: userId,
          sdp:     answer,
        }));
        break;
      }

      case "answer": {
        const pc = peersRef.current[msg.from_user as number];
        if (pc) await pc.setRemoteDescription(msg.sdp as RTCSessionDescriptionInit);
        break;
      }

      case "ice_candidate": {
        const pc = peersRef.current[msg.from_user as number];
        if (pc) await pc.addIceCandidate(msg.candidate as RTCIceCandidateInit);
        break;
      }
    }
  }, [createPeerConnection, onPeerLeft]);

  const join = useCallback(async (withVideo = true, withAudio = true) => {
    // Get local media
    localStreamRef.current = await navigator.mediaDevices.getUserMedia({
      video: withVideo,
      audio: withAudio,
    });

    // Connect signaling
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws    = new WebSocket(`${proto}//${location.host}/ws/rtc/${roomId}`);
    wsRef.current = ws;

    ws.onopen  = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => handleSignalingMessage(JSON.parse(e.data));
  }, [roomId, handleSignalingMessage]);

  const leave = useCallback(() => {
    Object.values(peersRef.current).forEach(pc => pc.close());
    peersRef.current = {};
    localStreamRef.current?.getTracks().forEach(t => t.stop());
    wsRef.current?.close();
    setPeers([]);
    setConnected(false);
  }, []);

  const toggleAudio = useCallback((enabled: boolean) => {
    localStreamRef.current?.getAudioTracks().forEach(t => { t.enabled = enabled; });
  }, []);

  const toggleVideo = useCallback((enabled: boolean) => {
    localStreamRef.current?.getVideoTracks().forEach(t => { t.enabled = enabled; });
  }, []);

  useEffect(() => () => { leave(); }, [leave]);

  return {
    localStream: localStreamRef.current,
    connected, peers, join, leave, toggleAudio, toggleVideo,
  };
}
```

---

## Video Call UI

```tsx
// components/VideoCall.tsx
function VideoCall({ roomId }: { roomId: string }) {
  const localVideoRef  = useRef<HTMLVideoElement>(null);
  const [remoteStreams, setRemoteStreams] = useState<Record<number, MediaStream>>({});

  const { localStream, connected, peers, join, leave, toggleAudio, toggleVideo } = useWebRTC({
    roomId,
    onRemoteStream: (userId, stream) => {
      setRemoteStreams(s => ({ ...s, [userId]: stream }));
    },
    onPeerLeft: (userId) => {
      setRemoteStreams(s => { const n = {...s}; delete n[userId]; return n; });
    },
  });

  const [muted,   setMuted]   = useState(false);
  const [cameraOff, setCameraOff] = useState(false);

  // Attach local stream to video element
  useEffect(() => {
    if (localVideoRef.current && localStream) {
      localVideoRef.current.srcObject = localStream;
    }
  }, [localStream]);

  return (
    <div className="video-grid">
      {/* Local video */}
      <div className="video-tile local">
        <video ref={localVideoRef} autoPlay muted playsInline />
        <span>You</span>
      </div>

      {/* Remote videos */}
      {Object.entries(remoteStreams).map(([userId, stream]) => (
        <RemoteVideo key={userId} userId={Number(userId)} stream={stream} />
      ))}

      {/* Controls */}
      <div className="controls">
        {!connected ? (
          <button onClick={() => join()}>Join Call</button>
        ) : (
          <>
            <button onClick={() => { toggleAudio(muted); setMuted(!muted); }}>
              {muted ? "Unmute" : "Mute"}
            </button>
            <button onClick={() => { toggleVideo(cameraOff); setCameraOff(!cameraOff); }}>
              {cameraOff ? "Start Camera" : "Stop Camera"}
            </button>
            <button onClick={leave} className="danger">Leave</button>
          </>
        )}
      </div>
    </div>
  );
}

function RemoteVideo({ userId, stream }: { userId: number; stream: MediaStream }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.srcObject = stream;
  }, [stream]);
  return (
    <div className="video-tile">
      <video ref={ref} autoPlay playsInline />
      <span>User {userId}</span>
    </div>
  );
}
```

---

## Data Channels — P2P File Transfer / Chat

```tsx
// For text chat or file transfer without going through your server
const pc = new RTCPeerConnection({ iceServers });

// Initiator creates data channel
const channel = pc.createDataChannel("chat", {
  ordered: true,   // guaranteed delivery order
});

channel.onopen    = () => console.log("Data channel open");
channel.onmessage = (e) => console.log("Received:", e.data);
channel.send("Hello!");

// Receiver
pc.ondatachannel = (event) => {
  const channel = event.channel;
  channel.onmessage = (e) => console.log("Received:", e.data);
};

// File transfer
async function sendFile(file: File, channel: RTCDataChannel) {
  const CHUNK_SIZE = 16384;   // 16KB chunks
  const buffer = await file.arrayBuffer();
  let offset = 0;

  // Send metadata first
  channel.send(JSON.stringify({ type: "file-start", name: file.name, size: file.size }));

  while (offset < buffer.byteLength) {
    // Respect buffer limits — avoid overwhelming the channel
    if (channel.bufferedAmount > channel.bufferedAmountLowThreshold) {
      await new Promise(resolve => { channel.onbufferedamountlow = resolve; });
    }
    channel.send(buffer.slice(offset, offset + CHUNK_SIZE));
    offset += CHUNK_SIZE;
  }

  channel.send(JSON.stringify({ type: "file-end" }));
}
```

---

## Room Model

```python
# apps/rtc/models.py
from common.models import TenantScopedModel
from django.db import models

class Room(TenantScopedModel):
    name       = models.CharField(max_length=255)
    max_peers  = models.IntegerField(default=10)
    is_active  = models.BooleanField(default=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "rtc_rooms"
```

---

## WebRTC Checklist

- [ ] Signaling server via WebSocket (Django Channels or FastAPI) — relays SDP + ICE only
- [ ] STUN server configured — peer public IP discovery
- [ ] TURN server (coturn) for NAT traversal — ~15-20% of users need it
- [ ] TURN credentials are short-lived (24h) and HMAC-signed — never static
- [ ] `restartIce()` on connection failure — auto-recovery
- [ ] Room access verified server-side before WebSocket accept
- [ ] ICE candidates queued if remote description not yet set
- [ ] `muted` video element for local stream — no audio echo
- [ ] Data channels for P2P chat/file transfer — don't route through server
- [ ] Chunk file transfers — `bufferedAmountLowThreshold` to avoid overflow
- [ ] Room max_peers enforced — don't let unbounded peers join
- [ ] TURN server monitored — bandwidth and connection count
