"""API-level tests: the FastAPI surface and the AI SDK v6 UI Message Stream.

The scripted LLM keeps these offline; the SSE wire format is asserted
explicitly because the frontend's useChat depends on it exactly.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_graph
from app.main import create_app
from app.tests.integration.scripted_llm import ScriptedChatModel
from app.tests.integration.test_hitl_flow import CREATE_APPT_ARGS, tool_call


@pytest.fixture(autouse=True)
def _use_db_copy(db_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "database_path", db_path)


def make_client(responses: list[AIMessage]) -> AsyncClient:
    graph = build_graph(checkpointer=InMemorySaver(), llm=ScriptedChatModel(responses=responses))
    app = create_app(graph=graph)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def post_chat(client: AsyncClient, body: dict) -> tuple[list[dict], str]:
    """POST /api/chat and parse the SSE body into chunks + raw text."""
    response = await client.post("/api/chat", json=body)
    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    raw = response.text
    chunks = [
        json.loads(line.removeprefix("data: "))
        for line in raw.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    return chunks, raw


def chunk_types(chunks: list[dict]) -> list[str]:
    return [c["type"] for c in chunks]


USER_MSG = {"role": "user", "parts": [{"type": "text", "text": "Find Sara"}]}


class TestChatStream:
    async def test_read_flow_streams_protocol_chunks(self):
        async with make_client(
            [tool_call("find_patient", {"name": "Sara"}), AIMessage(content="Found her.")]
        ) as client:
            chunks, raw = await post_chat(
                client, {"thread_id": "t1", "messages": [USER_MSG]}
            )

        types = chunk_types(chunks)
        assert types[0] == "start"
        assert "tool-input-available" in types
        assert "tool-output-available" in types
        assert "text-delta" in types
        assert types[-1] == "finish"
        assert raw.rstrip().endswith("data: [DONE]")

        tool_input = next(c for c in chunks if c["type"] == "tool-input-available")
        assert tool_input["toolName"] == "find_patient"
        assert tool_input["input"] == {"name": "Sara"}
        tool_output = next(c for c in chunks if c["type"] == "tool-output-available")
        assert tool_output["toolCallId"] == tool_input["toolCallId"]
        assert "Sara Thompson" in json.dumps(tool_output["output"])

    async def test_thread_id_is_issued_when_missing(self):
        async with make_client([AIMessage(content="Hi!")]) as client:
            chunks, _ = await post_chat(client, {"messages": [USER_MSG]})
        thread_chunk = next(c for c in chunks if c["type"] == "data-thread")
        assert thread_chunk["data"]["thread_id"]


class TestApprovalOverApi:
    async def test_write_flow_emits_approval_request_then_resume_executes(self):
        responses = [
            tool_call("create_appointment", CREATE_APPT_ARGS),
            AIMessage(content="Booked!"),
        ]
        async with make_client(responses) as client:
            chunks, _ = await post_chat(
                client,
                {"thread_id": "t1", "messages": [{"role": "user", "parts": [{"type": "text", "text": "Book it"}]}]},
            )
            approval = next(c for c in chunks if c["type"] == "data-approval_request")
            assert approval["data"]["tool"] == "create_appointment"
            assert approval["data"]["display"]["patient"] == "Sara Thompson"
            interrupt_id = approval["data"]["interrupt_id"]

            # State endpoint shows the pending action between turns.
            state = (await client.get("/api/threads/t1/state")).json()
            assert state["pending"][0]["tool"] == "create_appointment"

            chunks, _ = await post_chat(
                client,
                {"thread_id": "t1",
                 "resume": [{"interrupt_id": interrupt_id, "approved": True}]},
            )

        types = chunk_types(chunks)
        # The executed call is re-emitted as a complete input+output pair so
        # the result lands in the new message.
        assert "tool-input-available" in types
        output = next(c for c in chunks if c["type"] == "tool-output-available")
        assert json.loads(output["output"]) if isinstance(output["output"], str) else output["output"]
        assert "data-approval_request" not in types
        text = "".join(c["delta"] for c in chunks if c["type"] == "text-delta")
        assert text == "Booked!"

    async def test_deny_over_api(self):
        responses = [
            tool_call("create_appointment", CREATE_APPT_ARGS),
            AIMessage(content="Okay, not booking."),
        ]
        async with make_client(responses) as client:
            chunks, _ = await post_chat(
                client,
                {"thread_id": "t1", "messages": [{"role": "user", "parts": [{"type": "text", "text": "Book it"}]}]},
            )
            interrupt_id = next(
                c for c in chunks if c["type"] == "data-approval_request"
            )["data"]["interrupt_id"]

            chunks, _ = await post_chat(
                client,
                {"thread_id": "t1",
                 "resume": [{"interrupt_id": interrupt_id, "approved": False, "reason": "nope"}]},
            )

            state = (await client.get("/api/threads/t1/state")).json()

        output = next(c for c in chunks if c["type"] == "tool-output-available")
        assert "denied" in str(output["output"]).lower()
        assert state["pending"] == []


class TestStateAndHealth:
    async def test_state_returns_message_history(self):
        async with make_client(
            [tool_call("find_patient", {"name": "Sara"}), AIMessage(content="Found her.")]
        ) as client:
            await post_chat(client, {"thread_id": "t9", "messages": [USER_MSG]})
            state = (await client.get("/api/threads/t9/state")).json()

        roles = [m["role"] for m in state["messages"]]
        assert roles[0] == "user" and roles[-1] == "assistant"
        assert state["pending"] == []

    async def test_unknown_thread_state_is_empty(self):
        async with make_client([]) as client:
            state = (await client.get("/api/threads/nope/state")).json()
        assert state == {"messages": [], "pending": []}

    async def test_health(self):
        async with make_client([]) as client:
            health = (await client.get("/api/health")).json()
        assert health["status"] == "ok"
        assert health["frozen_now"] == "2025-03-16T09:00:00+00:00"
