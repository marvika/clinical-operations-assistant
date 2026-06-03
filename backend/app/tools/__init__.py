"""Tool registry.

The read/write split drives the human-in-the-loop gate: the agent graph
checks tool names against WRITE_TOOLS and pauses for approval before
executing any of them. Read tools run directly.
"""

from app.tools.reads import READ_TOOLS
from app.tools.writes import WRITE_TOOL_LIST

ALL_TOOLS = [*READ_TOOLS, *WRITE_TOOL_LIST]

WRITE_TOOLS = frozenset(t.name for t in WRITE_TOOL_LIST)

TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}
