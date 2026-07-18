"""In-process WebSocket hub for live sheet updates and web→phone case handoff.

Single-instance broadcaster: fine for the current Cloud Run deployment. For multiple
instances, put a Redis (or Cloud Pub/Sub) fan-out behind `broadcast`/`send_to_user`.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from ..security import decode_token

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> set of live sockets (a user may have web + phone open at once)
        self._by_user: dict[int, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, user_id: int) -> None:
        await ws.accept()
        self._by_user.setdefault(user_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        conns = self._by_user.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self._by_user.pop(user_id, None)

    async def send_to_user(self, user_id: int, data: dict) -> None:
        for ws in list(self._by_user.get(user_id, set())):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(ws, user_id)

    async def broadcast(self, data: dict) -> None:
        for user_id, conns in list(self._by_user.items()):
            for ws in list(conns):
                try:
                    await ws.send_json(data)
                except Exception:
                    self.disconnect(ws, user_id)


manager = ConnectionManager()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """Authenticate via ?token=<JWT>, then stream server→client events:
      { type: "case_update", case: {...} }   — a row changed (live sheet)
      { type: "open_case", case_id: N }       — web asked to open this case on the phone
    """
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=1008)
        return
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        await ws.close(code=1008)
        return

    await manager.connect(ws, user_id)
    try:
        while True:
            # We don't require client messages; receiving keeps the socket alive
            # and lets the client send lightweight "ping" frames.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, user_id)
    except Exception:
        manager.disconnect(ws, user_id)
