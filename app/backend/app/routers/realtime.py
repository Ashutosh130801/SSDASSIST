"""In-process WebSocket hub for live sheet updates and web→phone case handoff.

Single-instance broadcaster: fine for the current Cloud Run deployment. For multiple
instances, put a Redis (or Cloud Pub/Sub) fan-out behind `broadcast`/`send_to_user`.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from ..security import decode_token

router = APIRouter()

# The main event loop, captured at startup so sync endpoints can schedule broadcasts.
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def notify_data_changed(bank: str | None = None, product: str | None = None) -> None:
    """Sync-safe fan-out: tell every client that data changed (a log/payment/edit landed),
    so live views (MIS, dashboards, sheet) can refresh instantly."""
    payload = {"type": "data_changed"}
    if bank:
        payload["bank"] = bank
    if product:
        payload["product"] = product
    loop = _loop
    try:
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)
        else:
            asyncio.run(manager.broadcast(payload))
    except Exception:
        pass


def notify_user(user_id: int, payload: dict) -> None:
    """Sync-safe targeted push to one user's live sockets (web + phone). Used to alert an
    assigned FOS the instant a caller/head-office updates a customer's new address/phone."""
    if not user_id:
        return
    loop = _loop
    try:
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.send_to_user(user_id, payload), loop)
        else:
            asyncio.run(manager.send_to_user(user_id, payload))
    except Exception:
        pass


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> set of live sockets (a user may have web + phone open at once)
        self._by_user: dict[int, set[WebSocket]] = {}
        # case_id -> { user_id: {"name","role","field"} } — who is editing a row right now
        self._editing: dict[int, dict[int, dict]] = {}

    async def connect(self, ws: WebSocket, user_id: int) -> None:
        await ws.accept()
        self._by_user.setdefault(user_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        conns = self._by_user.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self._by_user.pop(user_id, None)
                # user fully gone → drop them from every row they were editing
                for cid in [c for c, e in self._editing.items() if user_id in e]:
                    self._editing[cid].pop(user_id, None)
                    if not self._editing[cid]:
                        self._editing.pop(cid, None)

    def _editors(self, case_id: int) -> list[dict]:
        return [{"id": uid, **info} for uid, info in self._editing.get(case_id, {}).items()]

    async def set_editing(self, case_id: int, user_id: int, name: str, role: str,
                          field: str | None, editing: bool) -> None:
        """Record/clear that a user is editing a case row, then broadcast the row's
        current editor list so everyone sees the live 'X is editing' badge."""
        slot = self._editing.setdefault(case_id, {})
        if editing:
            slot[user_id] = {"name": name, "role": role, "field": field}
        else:
            slot.pop(user_id, None)
            if not slot:
                self._editing.pop(case_id, None)
        await self.broadcast({"type": "presence", "case_id": case_id,
                              "editors": self._editors(case_id)})

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
        uname = payload.get("name") or "Someone"
        urole = payload.get("role") or ""
    except (JWTError, TypeError, ValueError):
        await ws.close(code=1008)
        return

    await manager.connect(ws, user_id)
    try:
        while True:
            # Clients may send presence frames as they focus/blur a row or cell:
            #   {"type":"editing","case_id":N,"field":"remarks"}
            #   {"type":"editing_stop","case_id":N}
            import json
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            t = msg.get("type")
            cid = msg.get("case_id")
            if t in ("editing", "editing_stop") and cid:
                await manager.set_editing(int(cid), user_id, uname, urole,
                                          msg.get("field"), editing=(t == "editing"))
            elif t == "call":
                # WebRTC voice-call signaling relay (staff↔staff). Forward the frame to the
                # target user's sockets, stamped with who it's from. sub: invite|answer|ice|reject|end
                to_id = msg.get("to_id")
                if to_id:
                    await manager.send_to_user(int(to_id), {
                        "type": "call", "sub": msg.get("sub"), "from_id": user_id,
                        "from_name": uname, "data": msg.get("data"),
                    })
    except WebSocketDisconnect:
        manager.disconnect(ws, user_id)
    except Exception:
        manager.disconnect(ws, user_id)
