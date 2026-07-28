"""WebSocket endpoints.

/ws/ui  — the web UI, authenticated by the session cookie.
/ws/ext — paired extensions, authenticated by device token (query param,
          since browser WebSocket clients cannot set Authorization headers).
"""
from __future__ import annotations

import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import get_sessionmaker
from app.deps import ws_device_from_token, ws_user_from_cookie
from app.logging_conf import get_logger
from app.ws import hub

log = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/ui")
async def ws_ui(websocket: WebSocket) -> None:
    db = get_sessionmaker()()
    try:
        user = await ws_user_from_cookie(websocket, db)
        db.commit()
    finally:
        db.close()
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await hub.connect_ui(user.id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - client sent junk
        with contextlib.suppress(Exception):
            await websocket.close()
    finally:
        await hub.disconnect_ui(user.id, websocket)


@router.websocket("/ws/ext")
async def ws_ext(websocket: WebSocket, token: str = "") -> None:
    if not token:
        await websocket.close(code=4401)
        return
    db = get_sessionmaker()()
    try:
        device = await ws_device_from_token(websocket, db, token)
        db.commit()
    finally:
        db.close()
    if device is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await hub.connect_ext(device.user_id, device.id, websocket)
    log.info("ws.ext_connected", device_id=device.id, user_id=device.user_id)
    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if kind == "ping":
                await websocket.send_json({"type": "pong"})
            elif kind == "response" and message.get("id"):
                # Reply to a server-initiated request (e.g. relay control).
                hub.resolve_pending(str(message["id"]), message)
            elif kind == "relay.frame" or kind == "relay.event":
                # Screencast frames / status from the opt-in remote-hand
                # relay: forward to the user's UI sockets untouched. The
                # relay transports human input; it never generates any.
                await hub.send_ui(device.user_id, message)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover
        with contextlib.suppress(Exception):
            await websocket.close()
    finally:
        await hub.disconnect_ext(device.user_id, device.id, websocket)
        log.info("ws.ext_disconnected", device_id=device.id)
