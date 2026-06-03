"""Graph state.

The conversation is the state: a single append-only message list managed by
LangGraph's ``add_messages`` reducer. Pending approvals are deliberately NOT
modeled here — they live in the checkpointer as interrupts, so approval state
can never drift out of sync with where the graph actually paused.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
