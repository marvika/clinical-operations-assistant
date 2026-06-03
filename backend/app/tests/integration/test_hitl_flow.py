"""Integration tests for the agent graph's human-in-the-loop behavior.

The LLM is scripted (deterministic, offline); everything else — the graph,
the interrupt/resume machinery, the checkpointer, the tools, the database
triggers — is real. These tests pin the core guarantees of the case:

1. read-only tools execute without approval
2. mutating tools pause the graph BEFORE any side effect
3. approve executes; deny skips and informs the model
4. pending approvals survive a process restart (checkpointer)
5. database conflicts (overlap trigger) surface gracefully
"""

import json
import sqlite3
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agent.graph import build_graph
from app.tests.integration.scripted_llm import ScriptedChatModel

CONFIG = {"configurable": {"thread_id": "test-thread"}}


@pytest.fixture(autouse=True)
def _use_db_copy(db_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "database_path", db_path)


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


CREATE_APPT_ARGS = {
    "patient_id": 1,
    "clinician_id": 2,
    "location_id": 1,
    "start_time": "2025-03-18T10:00:00+00:00",
    "end_time": "2025-03-18T10:30:00+00:00",
    "type": "Follow-up",
}


def count_appointments(db_path) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]


def build(llm_responses: list[AIMessage], checkpointer=None):
    return build_graph(
        checkpointer=checkpointer or InMemorySaver(),
        llm=ScriptedChatModel(responses=llm_responses),
    )


class TestReadPath:
    def test_read_tool_executes_without_interrupt(self):
        graph = build(
            [
                tool_call("find_patient", {"name": "Sara"}),
                AIMessage(content="Found Sara Thompson."),
            ]
        )
        result = graph.invoke({"messages": [HumanMessage("Find Sara")]}, CONFIG)

        assert "__interrupt__" not in result
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert "Sara Thompson" in tool_messages[0].content
        assert result["messages"][-1].content == "Found Sara Thompson."


class TestApprovalFlow:
    def test_write_tool_interrupts_before_any_side_effect(self, db_path):
        before = count_appointments(db_path)
        graph = build([tool_call("create_appointment", CREATE_APPT_ARGS)])

        result = graph.invoke({"messages": [HumanMessage("Book it")]}, CONFIG)

        (interrupt,) = result["__interrupt__"]
        assert interrupt.value["tool"] == "create_appointment"
        assert interrupt.value["args"] == CREATE_APPT_ARGS
        assert count_appointments(db_path) == before, "no write before approval"

    def test_interrupt_payload_includes_display_names(self):
        graph = build([tool_call("create_appointment", CREATE_APPT_ARGS)])
        result = graph.invoke({"messages": [HumanMessage("Book it")]}, CONFIG)

        display = result["__interrupt__"][0].value["display"]
        assert display["patient"] == "Sara Thompson"
        assert display["clinician"] == "Dr. Alice Nguyen"
        assert display["location"] == "Room 101"

    def test_approve_executes_and_model_narrates(self, db_path):
        before = count_appointments(db_path)
        graph = build(
            [
                tool_call("create_appointment", CREATE_APPT_ARGS),
                AIMessage(content="Booked!"),
            ]
        )
        result = graph.invoke({"messages": [HumanMessage("Book it")]}, CONFIG)
        interrupt_id = result["__interrupt__"][0].id

        result = graph.invoke(Command(resume={interrupt_id: {"approved": True}}), CONFIG)

        assert count_appointments(db_path) == before + 1
        tool_message = [m for m in result["messages"] if isinstance(m, ToolMessage)][-1]
        assert json.loads(tool_message.content)["type"] == "Follow-up"
        assert result["messages"][-1].content == "Booked!"

    def test_deny_skips_execution_and_informs_model(self, db_path):
        before = count_appointments(db_path)
        graph = build(
            [
                tool_call("create_appointment", CREATE_APPT_ARGS),
                AIMessage(content="Understood, I won't book it."),
            ]
        )
        result = graph.invoke({"messages": [HumanMessage("Book it")]}, CONFIG)
        interrupt_id = result["__interrupt__"][0].id

        result = graph.invoke(
            Command(resume={interrupt_id: {"approved": False, "reason": "wrong clinician"}}),
            CONFIG,
        )

        assert count_appointments(db_path) == before, "denied action must not execute"
        tool_message = [m for m in result["messages"] if isinstance(m, ToolMessage)][-1]
        assert "denied" in tool_message.content.lower()
        assert "wrong clinician" in tool_message.content

    def test_pending_approval_survives_restart(self, db_path, tmp_path):
        checkpoint_file = str(tmp_path / "checkpoints.db")
        responses = [
            tool_call("create_appointment", CREATE_APPT_ARGS),
            AIMessage(content="Booked!"),
        ]

        with SqliteSaver.from_conn_string(checkpoint_file) as saver:
            graph = build(responses, checkpointer=saver)
            result = graph.invoke({"messages": [HumanMessage("Book it")]}, CONFIG)
            interrupt_id = result["__interrupt__"][0].id

        # "Restart": a brand-new graph instance over the same checkpoint file.
        with SqliteSaver.from_conn_string(checkpoint_file) as saver:
            graph = build(responses[1:], checkpointer=saver)
            state = graph.get_state(CONFIG)
            assert state.interrupts, "pending approval must be visible after restart"
            assert state.interrupts[0].value["tool"] == "create_appointment"

            before = count_appointments(db_path)
            graph.invoke(Command(resume={interrupt_id: {"approved": True}}), CONFIG)
            assert count_appointments(db_path) == before + 1


class TestMultiplePendingActions:
    def test_two_writes_approve_one_deny_one(self, db_path):
        second_args = {**CREATE_APPT_ARGS, "location_id": 2}
        two_calls = AIMessage(
            content="",
            tool_calls=[
                {"name": "create_appointment", "args": CREATE_APPT_ARGS, "id": "call_1"},
                {"name": "create_appointment", "args": second_args, "id": "call_2"},
            ],
        )
        graph = build([two_calls, AIMessage(content="One booked, one denied.")])
        before = count_appointments(db_path)

        result = graph.invoke({"messages": [HumanMessage("Book both")]}, CONFIG)
        first = result["__interrupt__"][0]
        result = graph.invoke(Command(resume={first.id: {"approved": True}}), CONFIG)
        second = result["__interrupt__"][0]
        assert second.value["args"] == second_args
        assert count_appointments(db_path) == before, "no execution until ALL decisions in"

        result = graph.invoke(
            Command(resume={second.id: {"approved": False, "reason": "no"}}), CONFIG
        )

        assert count_appointments(db_path) == before + 1, "exactly the approved one ran"
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert json.loads(tool_messages[-2].content)["location_id"] == 1
        assert "denied" in tool_messages[-1].content.lower()


class TestConflictSurfacing:
    def test_room_overlap_becomes_error_tool_message(self, db_path):
        # Appointment 2 in the provided db: Room 202 on 2025-03-12 11:00-11:30.
        overlapping = {**CREATE_APPT_ARGS, "location_id": 2,
                       "start_time": "2025-03-12T11:00:00+00:00",
                       "end_time": "2025-03-12T11:30:00+00:00"}
        graph = build(
            [
                tool_call("create_appointment", overlapping),
                AIMessage(content="That room is taken at that time."),
            ]
        )
        before = count_appointments(db_path)

        result = graph.invoke({"messages": [HumanMessage("Book it")]}, CONFIG)
        interrupt_id = result["__interrupt__"][0].id
        result = graph.invoke(Command(resume={interrupt_id: {"approved": True}}), CONFIG)

        assert count_appointments(db_path) == before
        tool_message = [m for m in result["messages"] if isinstance(m, ToolMessage)][-1]
        assert tool_message.status == "error"
        assert "overlaps" in tool_message.content
        assert result["messages"][-1].content == "That room is taken at that time."

    def test_invalid_reference_becomes_error_tool_message(self):
        graph = build(
            [
                tool_call("create_appointment", {**CREATE_APPT_ARGS, "patient_id": 999999}),
                AIMessage(content="No such patient."),
            ]
        )
        result = graph.invoke({"messages": [HumanMessage("Book it")]}, CONFIG)
        interrupt_id = result["__interrupt__"][0].id
        result = graph.invoke(Command(resume={interrupt_id: {"approved": True}}), CONFIG)

        tool_message = [m for m in result["messages"] if isinstance(m, ToolMessage)][-1]
        assert tool_message.status == "error"
        assert "999999" in tool_message.content
