"""WebSocket hub.

Two channels:
  /ws/ui   — the web UI (session-cookie auth): live run state, interventions,
             search progress, notifications.
  /ws/ext  — paired browser extensions (device-token auth): job assignments,
             field resolutions, intervention answers, badge counts.

The app process holds the sockets. Worker processes publish events through
Redis pub/sub (`jobpilot:events:{user_id}`); the app relays them to the
user's sockets. In tests and single-process dev, `publish` short-circuits to
the local hub when Redis is unavailable.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.config import get_settings
from app.logging_conf import get_logger

log = get_logger(__name__)

CHANNEL_PREFIX = "jobpilot:events:"


class Hub:
    def __init__(self) -> None:
        self._ui: dict[int, set[WebSocket]] = defaultdict(set)
        self._ext: dict[int, dict[int, WebSocket]] = defaultdict(dict)  # user -> device -> ws
        self._lock = asyncio.Lock()
        # Pending request/response exchanges with extensions, keyed by message id.
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    # --- connection management -------------------------------------------
    async def connect_ui(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._ui[user_id].add(ws)

    async def disconnect_ui(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._ui[user_id].discard(ws)

    async def connect_ext(self, user_id: int, device_id: int, ws: WebSocket) -> None:
        async with self._lock:
            old = self._ext[user_id].pop(device_id, None)
        if old is not None:
            with contextlib.suppress(Exception):
                await old.close()
        async with self._lock:
            self._ext[user_id][device_id] = ws

    async def disconnect_ext(self, user_id: int, device_id: int, ws: WebSocket) -> None:
        async with self._lock:
            if self._ext[user_id].get(device_id) is ws:
                del self._ext[user_id][device_id]

    def ext_devices_online(self, user_id: int) -> list[int]:
        return list(self._ext.get(user_id, {}).keys())

    # --- sending ----------------------------------------------------------
    async def send_ui(self, user_id: int, message: dict[str, Any]) -> None:
        for ws in list(self._ui.get(user_id, ())):
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect_ui(user_id, ws)

    async def send_ext(
        self, user_id: int, message: dict[str, Any], device_id: int | None = None
    ) -> bool:
        targets = self._ext.get(user_id, {})
        sent = False
        for did, ws in list(targets.items()):
            if device_id is not None and did != device_id:
                continue
            try:
                await ws.send_json(message)
                sent = True
            except Exception:
                await self.disconnect_ext(user_id, did, ws)
        return sent

    # --- request/response with extension ---------------------------------
    def register_pending(self, message_id: str) -> asyncio.Future[dict[str, Any]]:
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[message_id] = fut
        return fut

    def resolve_pending(self, message_id: str, payload: dict[str, Any]) -> bool:
        fut = self._pending.pop(message_id, None)
        if fut is not None and not fut.done():
            fut.set_result(payload)
            return True
        return False


hub = Hub()


async def publish(user_id: int, message: dict[str, Any]) -> None:
    """Publish an event to a user's UI sockets, via Redis when available so
    worker processes reach sockets held by the app process."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(get_settings().redis_url)
        try:
            await client.publish(CHANNEL_PREFIX + str(user_id), json.dumps(message))
        finally:
            await client.aclose()
    except Exception:
        # No Redis (tests / single-process dev): deliver locally.
        await hub.send_ui(user_id, message)


def publish_sync(user_id: int, message: dict[str, Any]) -> None:
    """Publish from synchronous code (API endpoints, services)."""
    try:
        import redis as redis_sync

        client = redis_sync.from_url(get_settings().redis_url)
        try:
            client.publish(CHANNEL_PREFIX + str(user_id), json.dumps(message))
            return
        finally:
            client.close()
    except Exception:
        pass
    # Local fallback: schedule onto the running loop if there is one.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(hub.send_ui(user_id, message))


async def redis_relay(stop: asyncio.Event) -> None:
    """Run in the app process: relay Redis-published events to sockets."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(get_settings().redis_url)
        pubsub = client.pubsub()
        await pubsub.psubscribe(CHANNEL_PREFIX + "*")
    except Exception as exc:
        log.info("ws.relay.no_redis", error=str(exc))
        return
    log.info("ws.relay.started")
    try:
        while not stop.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            try:
                user_id = int(message["channel"].decode().rsplit(":", 1)[-1])
                payload = json.loads(message["data"])
            except Exception:
                continue
            await hub.send_ui(user_id, payload)
            if payload.get("also_ext"):
                await hub.send_ext(user_id, payload)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.aclose()
            await client.aclose()
