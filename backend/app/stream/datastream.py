"""Bridge: LangGraph run -> AI SDK v6 "UI Message Stream" (SSE).

This module is the single place that knows both vocabularies. It consumes a
LangGraph stream in two modes —

- ``messages``: token-level chunks from the LLM (live typing effect)
- ``updates``:  completed node outputs (tool calls, tool results, interrupts)

— and emits the protocol chunks the frontend's ``useChat`` consumes
(https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol): ``text-*``,
``tool-input-available``, ``tool-output-available`` / ``-error``, custom
``data-*`` parts, framed as ``data: {json}`` SSE lines ending with
``data: [DONE]``.

Custom data parts (ours, not the protocol's):
- ``data-thread``:           tells the client its thread id
- ``data-approval_request``: a mutating tool call is paused for approval

If the protocol moves on (v7...), this file is the only one to change.
"""

import json
from typing import Any, AsyncIterator
from uuid import uuid4

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

PROTOCOL_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
}


def encode(chunk: dict[str, Any]) -> str:
    return f"data: {json.dumps(chunk)}\n\n"


async def stream_run(
    graph: Any, run_input: Any, config: dict[str, Any], thread_id: str
) -> AsyncIterator[str]:
    yield encode({"type": "start"})
    yield encode({"type": "data-thread", "data": {"thread_id": thread_id}})

    emitter = _Emitter(args_by_id=await _known_tool_args(graph, config))
    try:
        async for mode, payload in graph.astream(
            run_input, config, stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                chunks = emitter.on_token(payload[0])
            else:
                chunks = emitter.on_update(payload)
            for chunk in chunks:
                yield encode(chunk)
    except Exception as exc:  # surface as a protocol error chunk, not a 500
        for chunk in emitter.close():
            yield encode(chunk)
        yield encode({"type": "error", "errorText": str(exc)})
        yield encode({"type": "finish"})
        yield "data: [DONE]\n\n"
        return

    for chunk in emitter.close():
        yield encode(chunk)
    yield encode({"type": "finish"})
    yield "data: [DONE]\n\n"


async def _known_tool_args(graph: Any, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Tool-call args already in this thread's history.

    When a resumed run executes a previously-approved call, the executing
    stream re-emits the call as a complete input+output pair; the args come
    from the AIMessage recorded before the interrupt.
    """
    snapshot = await graph.aget_state(config)
    args_by_id: dict[str, dict[str, Any]] = {}
    for message in (snapshot.values or {}).get("messages", []):
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                args_by_id[call["id"]] = {"name": call["name"], "args": call["args"]}
    return args_by_id


class _Emitter:
    """Stateful translator from LangGraph events to protocol chunks.

    Token chunks and node updates describe overlapping facts (the same AI
    message arrives once as a token stream, once complete), so it tracks what
    was already emitted and never says the same thing twice.
    """

    def __init__(self, args_by_id: dict[str, dict[str, Any]]):
        self.args_by_id = args_by_id
        self.text_done: set[str] = set()
        self.inputs_done: set[str] = set()
        self.open_text_id: str | None = None

    # -- token stream ------------------------------------------------------

    def on_token(self, message: Any) -> list[dict[str, Any]]:
        if not isinstance(message, (AIMessage, AIMessageChunk)):
            return []
        if not message.id or not isinstance(message.content, str) or not message.content:
            return []
        chunks = []
        if self.open_text_id != message.id:
            chunks += self.close()
            chunks.append({"type": "text-start", "id": message.id})
            self.open_text_id = message.id
            self.text_done.add(message.id)
        chunks.append({"type": "text-delta", "id": message.id, "delta": message.content})
        return chunks

    # -- node updates --------------------------------------------------------

    def on_update(self, update: dict[str, Any]) -> list[dict[str, Any]]:
        chunks = []
        for interrupt in update.get("__interrupt__", ()):
            chunks += self.close()
            chunks.append(
                {
                    "type": "data-approval_request",
                    "data": {**interrupt.value, "interrupt_id": interrupt.id},
                }
            )
        for node_update in update.values():
            if not isinstance(node_update, dict):
                continue
            for message in node_update.get("messages", []):
                if isinstance(message, ToolMessage):
                    chunks += self._tool_result(message)
                elif isinstance(message, AIMessage):
                    chunks += self._ai_message(message)
        return chunks

    def _ai_message(self, message: AIMessage) -> list[dict[str, Any]]:
        chunks = []
        # Text not seen on the token stream (e.g. non-streaming model).
        text_key = message.id or uuid4().hex
        if message.content and text_key not in self.text_done:
            self.text_done.add(text_key)
            chunks += self.close()
            chunks.append({"type": "text-start", "id": text_key})
            chunks.append({"type": "text-delta", "id": text_key, "delta": message.content})
            chunks.append({"type": "text-end", "id": text_key})
        for call in message.tool_calls:
            self.args_by_id[call["id"]] = {"name": call["name"], "args": call["args"]}
            chunks += self.close()
            chunks += self._tool_input(call["id"])
        return chunks

    def _tool_input(self, call_id: str) -> list[dict[str, Any]]:
        self.inputs_done.add(call_id)
        known = self.args_by_id.get(call_id, {"name": "unknown", "args": {}})
        return [
            {"type": "tool-input-start", "toolCallId": call_id, "toolName": known["name"]},
            {
                "type": "tool-input-available",
                "toolCallId": call_id,
                "toolName": known["name"],
                "input": known["args"],
            },
        ]

    def _tool_result(self, message: ToolMessage) -> list[dict[str, Any]]:
        chunks = self.close()
        if message.tool_call_id not in self.inputs_done:
            # Result of a call announced in an earlier turn (approved resume):
            # re-emit the input so this message carries a complete pair.
            chunks += self._tool_input(message.tool_call_id)
        if message.status == "error":
            chunks.append(
                {
                    "type": "tool-output-error",
                    "toolCallId": message.tool_call_id,
                    "errorText": str(message.content),
                }
            )
        else:
            chunks.append(
                {
                    "type": "tool-output-available",
                    "toolCallId": message.tool_call_id,
                    "output": _maybe_json(message.content),
                }
            )
        return chunks

    def close(self) -> list[dict[str, Any]]:
        """End the open text block, if any (before any non-text chunk)."""
        if self.open_text_id is None:
            return []
        chunk = {"type": "text-end", "id": self.open_text_id}
        self.open_text_id = None
        return [chunk]


def _maybe_json(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except ValueError:
            return content
    return content
