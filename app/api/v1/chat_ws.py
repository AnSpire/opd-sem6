import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat")
async def ws_chat(
    websocket: WebSocket,
    user_id: int = Query(...),
    board_id: int = Query(...),
):
    await websocket.accept()
    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    channel = f"chat:user:{user_id}"
    await pubsub.subscribe(channel)
    try:
        async for raw in pubsub.listen():
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            if raw["type"] == "message":
                data = raw["data"]
                await websocket.send_text(data.decode() if isinstance(data, bytes) else data)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws_chat error user_id=%s: %s", user_id, e)
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()
