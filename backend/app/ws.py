"""WebSocket endpoint for real-time project job progress.

GET ws /api/v1/ws/projects/{project_id}?token=<jwt>

Pushes JSON {project_id, stage, pct, message, ts} whenever progress changes.
Progress source: the in-memory registry in app.jobs (always updated), plus a
Redis pub/sub listener in celery mode (workers run in another process).
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from . import jobs
from .auth import decode_token
from .config import settings

logger = logging.getLogger("cutpilot.ws")

router = APIRouter()

# In-memory registry of connected sockets per project (for introspection).
_ws_registry: dict[str, set[WebSocket]] = {}


def _registry_add(project_id: str, ws: WebSocket) -> None:
    _ws_registry.setdefault(project_id, set()).add(ws)


def _registry_remove(project_id: str, ws: WebSocket) -> None:
    conns = _ws_registry.get(project_id)
    if conns:
        conns.discard(ws)
        if not conns:
            _ws_registry.pop(project_id, None)


async def _redis_listener(project_id: str, stop: asyncio.Event) -> None:
    """Forward Redis pub/sub progress into the in-memory dict (celery mode)."""
    try:
        import redis.asyncio as aioredis
    except Exception as e:
        logger.debug("redis.asyncio unavailable: %s", e)
        return
    channel = f"cutpilot:progress:{project_id}"
    try:
        client = aioredis.from_url(settings.redis_url, socket_timeout=5)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        try:
            while not stop.is_set():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                if msg and msg.get("type") == "message":
                    try:
                        data = json.loads(msg["data"])
                        with jobs._progress_lock:
                            jobs._progress[project_id] = data
                    except Exception:
                        pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await client.aclose()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug("redis listener for %s ended: %s", project_id, e)


@router.websocket("/ws/projects/{project_id}")
async def project_progress_ws(
    websocket: WebSocket,
    project_id: str,
    token: str | None = Query(None, description="JWT access token"),
):
    # ---- auth (close codes 4401/4403/4404 mirror HTTP semantics).
    # token is optional at the routing layer so we can close with a proper
    # WS code instead of failing the HTTP handshake.
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub") or 0)
    except Exception:
        await websocket.close(code=4401)
        return

    from . import models
    from .db import SessionLocal

    db = SessionLocal()
    try:
        user = db.get(models.User, user_id)
        project = db.get(models.Project, project_id)
        if not user or not user.is_active:
            await websocket.close(code=4401)
            return
        if project is None or (project.user_id != user.id and user.role != "admin"):
            await websocket.close(code=4404)
            return
    finally:
        db.close()

    await websocket.accept()
    _registry_add(project_id, websocket)

    stop = asyncio.Event()
    listener_task = None
    if jobs.redis_available():
        listener_task = asyncio.create_task(_redis_listener(project_id, stop))

    last_sent: dict | None = None
    try:
        # Send current state immediately so the UI never waits blind.
        current = jobs.get_progress(project_id)
        if current:
            await websocket.send_json(current)
            last_sent = current

        while True:
            await asyncio.sleep(0.5)
            current = jobs.get_progress(project_id)
            if current and current != last_sent:
                await websocket.send_json(current)
                last_sent = current
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("ws loop ended for %s: %s", project_id, e)
    finally:
        stop.set()
        if listener_task:
            listener_task.cancel()
        _registry_remove(project_id, websocket)
        try:
            await websocket.close()
        except Exception:
            pass
