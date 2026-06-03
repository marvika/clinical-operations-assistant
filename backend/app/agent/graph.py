"""The agent graph: a ReAct loop with an approval gate on mutating tools.

    START ─► agent ─► (tool calls?) ─► tools ─► agent ─► ... ─► END

Two nodes. The ``agent`` node calls the LLM with the tools bound; the
``tools`` node executes the requested calls. Any call whose tool is in
WRITE_TOOLS pauses the graph with ``interrupt()`` and only proceeds once a
human resumes it with an approve/deny decision.

Interrupt semantics that shape this code (LangGraph re-runs an interrupted
node from the top on every resume):

- The tools node is *two-phase*: it first collects ALL approval decisions
  (interrupting once per undecided write call), and only when every decision
  is in does it execute anything. Side effects therefore happen exactly once,
  on the final pass — re-running the collection phase is pure.
- Pending approvals are not extra state; they ARE the interrupt, persisted by
  the checkpointer under the conversation's thread_id. That is what makes a
  pending action addressable in later turns and across process restarts.
"""

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agent.llm import make_llm
from app.agent.prompt import build_system_prompt
from app.agent.state import AgentState
from app.db import repository
from app.db.connection import connect
from app.tools import TOOLS_BY_NAME, ALL_TOOLS, WRITE_TOOLS


def build_graph(checkpointer: Any, llm: BaseChatModel | None = None):
    model = (llm or make_llm()).bind_tools(ALL_TOOLS)

    def agent(state: AgentState) -> dict[str, Any]:
        messages = [SystemMessage(build_system_prompt()), *state["messages"]]
        response = model.invoke(messages)
        return {"messages": [response]}

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    def tools(state: AgentState) -> dict[str, Any]:
        tool_calls = state["messages"][-1].tool_calls

        # Phase 1 — collect decisions (pure; may pause repeatedly).
        decisions: dict[str, dict[str, Any] | None] = {}
        for call in tool_calls:
            if call["name"] in WRITE_TOOLS:
                decisions[call["id"]] = interrupt(_approval_request(call))
            else:
                decisions[call["id"]] = None  # read-only: no approval needed

        # Phase 2 — execute (side effects; runs exactly once).
        results = []
        for call in tool_calls:
            decision = decisions[call["id"]]
            if decision is not None and not decision.get("approved"):
                reason = decision.get("reason") or "no reason given"
                results.append(
                    ToolMessage(
                        content=f"Denied by the coordinator (reason: {reason}). "
                        "Do not retry this action.",
                        name=call["name"],
                        tool_call_id=call["id"],
                        # Structural marker so the UI can render "denied"
                        # instead of a normal result (the content above is
                        # what the model reads).
                        additional_kwargs={"hitl_decision": "denied"},
                    )
                )
            else:
                results.append(_execute(call))
        return {"messages": results}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)


def _execute(call: dict[str, Any]) -> ToolMessage:
    """Run one tool call, mapping failures to an error ToolMessage so the
    model can explain the problem instead of the graph crashing."""
    try:
        output = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
        content = json.dumps(output, default=str)
    except (repository.ConflictError, ValueError) as exc:
        return ToolMessage(
            content=f"ERROR: {exc}", name=call["name"],
            tool_call_id=call["id"], status="error",
        )
    return ToolMessage(content=content, name=call["name"], tool_call_id=call["id"])


def _approval_request(call: dict[str, Any]) -> dict[str, Any]:
    """The payload a reviewer sees when deciding on a pending action."""
    return {
        "tool": call["name"],
        "args": call["args"],
        "tool_call_id": call["id"],
        "display": _display_names(call["args"]),
    }


def _display_names(args: dict[str, Any]) -> dict[str, str]:
    """Resolve ids in the args to human-readable names for the approval card."""
    lookups = {
        "patient": ("patient_id", "SELECT name FROM patients WHERE patient_id = ?"),
        "clinician": ("clinician_id", "SELECT name FROM clinicians WHERE clinician_id = ?"),
        "location": ("location_id", "SELECT name FROM locations WHERE location_id = ?"),
    }
    display = {}
    with connect() as conn:
        for label, (key, query) in lookups.items():
            if key in args:
                row = conn.execute(query, [args[key]]).fetchone()
                if row:
                    display[label] = row["name"]
    return display
