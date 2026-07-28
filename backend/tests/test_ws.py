from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import register_and_login


def test_ui_ws_requires_auth_and_pongs(client):
    # Unauthenticated: the socket is closed before accept.
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/ui") as ws:
            ws.receive_json()

    register_and_login(client, "wsui@example.com")
    with client.websocket_connect("/ws/ui") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ext_ws_requires_token(client):
    # No device token -> rejected.
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/ext") as ws:
            ws.receive_json()

    # Pair a device, then connect with its token.
    headers = register_and_login(client, "wsext@example.com")
    code = client.post("/api/devices/pairing-code", headers=headers).json()["code"]
    token = client.post(
        "/api/ext/pair", json={"code": code, "name": "L", "browser": "chrome"}
    ).json()["token"]
    with client.websocket_connect(f"/ws/ext?token={token}") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
