"""HTTP surface.

POST /api/chat                   one conversational turn (or an approval
                                 decision), streamed as an AI SDK v6
                                 UI Message Stream
GET  /api/threads/{id}/state     rehydrate a thread: messages + pending approvals
GET  /api/health                 liveness + configuration echo
"""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from app import clock
from app.api.history import to_ui_messages
from app.config import settings
from app.stream.datastream import PROTOCOL_HEADERS, stream_run

router = APIRouter(prefix="/api")


class ResumeDecision(BaseModel):
    interrupt_id: str
    approved: bool
    reason: str | None = None


class ChatRequest(BaseModel):
    thread_id: str | None = None
    messages: list[dict] = []
    resume: list[ResumeDecision] | None = None


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request) -> StreamingResponse:
    graph = http_request.app.state.graph
    thread_id = request.thread_id or uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    if request.resume:
        # Approval decisions resume the paused graph at its interrupt(s).
        run_input = Command(
            resume={
                d.interrupt_id: {"approved": d.approved, "reason": d.reason}
                for d in request.resume
            }
        )
    else:
        run_input = {"messages": [HumanMessage(_last_user_text(request.messages))]}

    return StreamingResponse(
        stream_run(graph, run_input, config, thread_id),
        media_type="text/event-stream",
        headers=PROTOCOL_HEADERS,
    )


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            text = " ".join(
                part.get("text", "")
                for part in message.get("parts", [])
                if part.get("type") == "text"
            ).strip()
            if text:
                return text
    raise HTTPException(status_code=422, detail="No user message text found")


@router.get("/threads/{thread_id}/state")
async def thread_state(thread_id: str, http_request: Request) -> dict:
    graph = http_request.app.state.graph
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    return {
        "messages": to_ui_messages((snapshot.values or {}).get("messages", [])),
        "pending": [
            {**interrupt.value, "interrupt_id": interrupt.id}
            for interrupt in snapshot.interrupts
        ],
    }


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": settings.model_name,
        "database": str(settings.database_path),
        "frozen_now": clock.iso(clock.now()),
    }
