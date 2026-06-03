"""Convert LangChain message history to UI messages for thread rehydration.

When the browser reloads (or the backend restarted), GET /threads/{id}/state
returns the conversation in the same shape useChat builds incrementally from
the stream: text parts and tool parts, with approval state derivable from
whether a tool part has output yet.
"""

import json
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage


def to_ui_messages(messages: list[AnyMessage]) -> list[dict[str, Any]]:
    ui_messages: list[dict[str, Any]] = []
    outputs = {
        m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)
    }
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            ui_messages.append(
                {
                    "id": message.id or f"msg-{index}",
                    "role": "user",
                    "parts": [{"type": "text", "text": str(message.content)}],
                }
            )
        elif isinstance(message, AIMessage):
            parts: list[dict[str, Any]] = []
            if message.content:
                parts.append({"type": "text", "text": str(message.content)})
            for call in message.tool_calls:
                parts.append(_tool_part(call, outputs.get(call["id"])))
            if parts:
                ui_messages.append(
                    {"id": message.id or f"msg-{index}", "role": "assistant", "parts": parts}
                )
    return ui_messages


def _tool_part(call: dict[str, Any], result: ToolMessage | None) -> dict[str, Any]:
    part: dict[str, Any] = {
        "type": f"tool-{call['name']}",
        "toolCallId": call["id"],
        "input": call["args"],
    }
    if result is None:
        part["state"] = "input-available"  # still awaiting approval/execution
    elif result.status == "error":
        part["state"] = "output-error"
        part["errorText"] = str(result.content)
    else:
        part["state"] = "output-available"
        part["output"] = _maybe_json(result.content)
    return part


def _maybe_json(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except ValueError:
            return content
    return content
