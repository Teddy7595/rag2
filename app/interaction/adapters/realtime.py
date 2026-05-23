from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect

from app.core.app_context import get_app_context_from_app, get_app_context_from_request
from app.interaction.application import InteractionService
from app.interaction.application.realtime import RealtimeChatService
from app.interaction.events import InteractionRealtimeInput


router = APIRouter()


def _get_realtime_service(app: FastAPI) -> RealtimeChatService:
    context = get_app_context_from_app(app)
    service = context.services.get("interaction_realtime")
    if not isinstance(service, RealtimeChatService):
        raise RuntimeError("Interaction realtime service not registered")
    return service


def _decode_payload(raw_message: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_message)
    except json.JSONDecodeError:
        return {"content": raw_message}

    if isinstance(parsed, dict):
        return parsed
    return {"content": str(parsed)}


def _build_input(payload: dict[str, Any]) -> InteractionRealtimeInput:
    content = str(payload.get("content") or payload.get("message") or "").strip()
    if not content:
        raise ValueError("content is required")

    return InteractionRealtimeInput(
        content=content,
        author=str(payload.get("author") or "user"),
        channel=str(payload.get("channel") or "chat"),
        identity_id=payload.get("identity_id"),
        context_limit=int(payload.get("context_limit") or payload.get("limit") or 5),
        history_limit=int(payload.get("history_limit") or 20),
        world_rules=str(payload.get("world_rules") or ""),
    )


def _to_sse(packet: dict[str, object]) -> str:
    event_type = str(packet.get("type") or "message")
    data = json.dumps(packet, ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"


async def _send_packet(websocket: WebSocket, packet: dict[str, object]) -> None:
    await websocket.send_json(packet)


async def _send_session_bootstrap(websocket: WebSocket, service: RealtimeChatService, session_id: str) -> None:
    snapshot = service.open_session(session_id=session_id)
    for packet in snapshot.to_packets():
        await _send_packet(websocket, packet)
        await asyncio.sleep(0.001)


async def _run_websocket_session(websocket: WebSocket, service: RealtimeChatService, session_id: str) -> None:
    session_closed = False
    try:
        await _send_session_bootstrap(websocket, service, session_id)

        while True:
            raw_message = await websocket.receive_text()
            payload = _decode_payload(raw_message)
            if str(payload.get("type") or "").lower() in {"ping", "heartbeat"}:
                await _send_packet(websocket, {"type": "pong", "session_id": session_id})
                continue

            try:
                input_data = _build_input(payload)
            except ValueError as exc:
                await _send_packet(websocket, {"type": "error", "session_id": session_id, "detail": str(exc)})
                continue

            async for packet in service.stream_turn(input_data, session_id=session_id):
                await _send_packet(websocket, packet)
                await asyncio.sleep(0.002)
    except WebSocketDisconnect:
        service.close_session(session_id, reason="websocket_disconnect")
        session_closed = True
        raise
    finally:
        if not session_closed:
            service.close_session(session_id, reason="websocket_closed")


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    service = _get_realtime_service(websocket.app)
    session_id = str(uuid4())
    try:
        await _run_websocket_session(websocket, service, session_id)
    except WebSocketDisconnect:
        return


def build_realtime_stream(service: RealtimeChatService, payload: InteractionRealtimeInput, session_id: str):
    async def event_stream():
        snapshot = service.open_session(session_id=session_id, history_limit=payload.history_limit)
        try:
            for packet in snapshot.to_packets():
                yield _to_sse(packet)
                await asyncio.sleep(0.001)

            async for packet in service.stream_turn(payload, session_id=session_id):
                yield _to_sse(packet)
                await asyncio.sleep(0.002)
        finally:
            service.close_session(session_id, reason="sse_complete")

    return event_stream()