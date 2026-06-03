# Technical Case: Clinical Operations Assistant

## Overview

Build a small **agentic** "clinical operations assistant" that:

- interprets user intent,
- plans and executes multi-step tool calls,
- answers coordinator questions from database-backed tool results,
- and proposes actions that require human approval before execution.

The provided `database.db` (SQLite) is the only data source you should use, containing a couple of tables with synthetic clinical data.

- Do not change the schema of the database, use as is.
- You are expected to both read and write rows in the database.
- During review, we may swap in a different `.db` file with the same schema to verify robustness.

In order for this case to be deterministic, assume current date/time is always `2025-03-16T09:00:00Z`.

You may use any language/framework and any helper tools, including AI coding assistants and fully LLM-generated code.

An API key for the LLM used by your solution will be provided. Details on how it is shared will be provided to shortlisted candidates.

## Functional Requirements

Authentication and authorization are explicitly out of scope for this case. You are not expected to implement login, user/session management, RBAC/permissions, OAuth, end-user API key management, or any other auth mechanism. Integrating a provided LLM API key into the runtime configuration of your solution is sufficient.

1. Implement an agentic **interactive chat** interface that can be demonstrated live during review (CLI, web interface, or equivalent).

- The interface must support multi-turn follow-up questions in the same session.
- The interface must support interactive approval decisions (`approve` / `deny`) for pending mutating actions.

2. Implement tool-based retrieval:

- All data must be fetched through tool abstractions.
- Any mutating action (write/update/delete) must require HITL (Human-in-the-Loop) approval before execution.
- Read-only operations can execute directly (no HITL required).
- Provide transparency over which tools were called, with which parameters, and what results were returned.
- Pending actions should remain addressable in the live interaction so a reviewer can approve/deny them in subsequent turns.

3. Add focused tests where appropriate (unit and/or integration)

Example queries which should be supported:

- "Which patients are scheduled for appointments in the next 7 days?"
- "Who has abnormal (HIGH) lab results in the last 14 days?"
- "Create an appointment for Patricia Adams with Dr. Alice Nguyen next week as a follow-up."

## Expected Deliverables

Source code, documentation and example inputs/outputs demonstrating the system's capabilities.