from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agents.llm import get_llm
from models.schemas import ChatWebSocketRequest

router = APIRouter(tags=["chat"])

# Keep a lightweight in-memory history per session.
SESSION_HISTORY: dict[str, list[BaseMessage]] = defaultdict(list)
SESSION_CONTEXT: dict[str, dict[str, Any]] = {}


def _build_system_prompt(trip_context: dict[str, Any]) -> str:
    context_json = json.dumps(trip_context, default=str)
    return (
        "You are a helpful road trip assistant.\n"
        "Answer the user's follow-up questions using the trip context when relevant.\n"
        "Be concise, practical, and safety-aware. If the user asks about monsoon or safety, call out risks clearly.\n"
        f"Trip context:\n{context_json}"
    )


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = ChatWebSocketRequest.model_validate_json(raw)
            except Exception as exc:
                await websocket.send_json({"type": "error", "content": f"Invalid message payload: {exc}"})
                continue

            session_id = payload.session_id
            trip_context = payload.trip_context or SESSION_CONTEXT.get(session_id, {})
            SESSION_CONTEXT[session_id] = trip_context

            history = SESSION_HISTORY[session_id]
            if not history:
                history.append(SystemMessage(content=_build_system_prompt(trip_context)))
            else:
                history[0] = SystemMessage(content=_build_system_prompt(trip_context))

            history.append(HumanMessage(content=payload.message))

            llm = get_llm(temperature=0.3)
            assistant_text = ""

            try:
                async for chunk in llm.astream(history):
                    token = getattr(chunk, "content", "")
                    if not token:
                        continue
                    assistant_text += token
                    await websocket.send_json(
                        {
                            "type": "token",
                            "session_id": session_id,
                            "content": token,
                        }
                    )
                history.append(AIMessage(content=assistant_text))
                await websocket.send_json(
                    {
                        "type": "done",
                        "session_id": session_id,
                        "content": assistant_text,
                    }
                )
            except Exception as exc:
                await websocket.send_json({"type": "error", "session_id": session_id, "content": str(exc)})
    except WebSocketDisconnect:
        return
