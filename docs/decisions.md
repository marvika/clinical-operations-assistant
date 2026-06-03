# Design decisions

The choices behind this solution, with the trade-offs that were weighed. Each
section is intentionally short — these are discussion starters, not essays.

## 1. Orchestration: LangGraph with a hand-built two-node graph

**Choice.** A custom `StateGraph` with two nodes (`agent` ⇄ `tools`) — the
classic ReAct loop — rather than LangGraph's prebuilt `create_react_agent`,
Microsoft Agent Framework, Pydantic AI, or a hand-rolled tool-calling loop.

**Why LangGraph.** The case's hardest requirement is that *pending approvals
remain addressable across turns*. LangGraph is the only mainstream framework
where that is a first-class, durable primitive: `interrupt()` pauses the graph,
the checkpointer persists the paused state under the conversation's
`thread_id`, and `Command(resume=...)` continues it — minutes or days later,
even after a process restart. Microsoft Agent Framework (evaluated; GA since
April 2026) models HITL at the *workflow* level, which adds ceremony a
single-agent case doesn't need. Pydantic AI's `requires_approval` deferred
tools are elegant but stateless — the application owns approval persistence.

**Why not `create_react_agent`.** The prebuilt agent hides exactly the parts
this case is about. With ~60 lines of explicit graph, the approval gate, the
routing, and the loop are all inspectable code.

## 2. HITL as an interrupt, not a side-channel

Pending approvals are **not** rows in a table or flags in app state — they
*are* the interrupt, stored by the checkpointer. There is exactly one source
of truth for "what is the agent waiting for", and it cannot drift from where
the graph actually paused. The UI's pending tray is populated by reading graph
state (`GET /threads/{id}/state`), so a browser refresh or backend restart
changes nothing.

**The trade-off.** LangGraph re-runs an interrupted node from the top on every
resume. That demands side-effect discipline, which led to…

## 3. The two-phase tools node

The tools node first **collects** all approval decisions (one `interrupt()`
per undecided mutating call — pure, repeatable), and only when every decision
is in does it **execute** anything. Side effects happen exactly once, on the
final pass. This makes multiple pending writes in one turn safe: approve one,
deny the other, and exactly one executes. (A subtle bug class — re-executing
an already-approved write when a later interrupt resumes — is eliminated
structurally rather than by bookkeeping.)

## 4. Tool design: a closed set of typed domain tools, no SQL escape hatch

Nine read tools, four write tools, all with typed parameters. The HITL gate is
driven by membership in `WRITE_TOOLS` — a closed set, so "which actions can
mutate the database" is a one-line audit. A read-only SQL tool was considered
(more flexible for long-tail questions) and rejected: it blurs the
read/write boundary the whole case hinges on, and every domain tool is
individually testable. Write tools validate references up front
(`No patient with id 42`) so approval cards and error messages stay humane.

## 5. Model: gpt-4.1-mini only — and why not gpt-5.2-chat

Two deployments were provided. `gpt-5.2-chat` is the chat-tuned variant with a
documented history of not supporting tool calling on Azure (Microsoft's own
guidance: use a tool-enabled model for agents). An agentic system whose brain
silently drops tool calls is the worst failure mode available, so the
tool-loop runs on `gpt-4.1-mini` (temperature 0 for determinism). A two-model
split — 4.1-mini for the loop, 5.2-chat to phrase final answers — was
considered and rejected: in production you add a second model when evals show
a quality gap, not because one is available.

## 6. Frozen clock as an injected constant

`app/clock.py` is the only place that knows what "now" is; nothing calls
`datetime.now()`. The system prompt states the frozen instant *and*
precomputed windows ("next week = Mon 2025-03-17 … Sun 2025-03-23") so the
model does no unaided calendar math. Date-boundary unit tests pin the windows
— including the fact that 2025-03-16 is a Sunday, which makes "next week"
genuinely ambiguous for humans and models alike.

## 7. Schema quirks handled in the data layer, invisibly to the model

The provided schema stores `patients.primary_clinician_id` as TEXT against an
INTEGER key; joins CAST both sides so a swapped database using INTEGER also
works. Timestamps are compared as ISO-8601 strings (lexicographically safe).
The room-overlap triggers surface as `ConflictError` → an error tool message →
a model apology with alternatives, not a stack trace. The model never learns
about any of this — storage quirks don't belong in prompts.

## 8. Names are resolved, never guessed

The prompt forbids inventing ids: every person/place is resolved through
`find_*` tools. Patient names are not unique in this schema, so ambiguity is a
first-class flow — the agent stops and asks (listing dates of birth) rather
than acting. The eval suite makes a name ambiguous on purpose and asserts no
write happens.

## 9. Denial feeds back as a tool message

A denied action becomes a `ToolMessage` ("Denied by the coordinator (reason:
…). Do not retry.") rather than silently vanishing. The model stays in a
coherent loop — every tool call has a result — and can acknowledge the
decision in language, while the prompt forbids retrying.

## 10. Wire protocol: AI SDK v6 UI Message Stream, implemented directly

The frontend uses assistant-ui over the AI SDK's `useChat`, which speaks the
documented "UI Message Stream" SSE protocol. The backend implements that
protocol in one module (`stream/datastream.py`) rather than pulling in a
bridge dependency — the obvious candidate (`assistant-stream`) still emits the
deprecated v4 wire format. The encoder was written against the installed
package's own TypeScript types. In a long-lived product I would prefer a
maintained adapter (e.g. the AG-UI protocol); the mitigation here is
structural: the protocol knowledge lives behind one module boundary and is
swappable without touching the graph or routes.

## 11. Frontend: assistant-ui, deliberately not CopilotKit

CopilotKit was evaluated and is arguably the production-grade default for
agentic UIs (it authored the AG-UI protocol; first-party LangGraph
integration). It was rejected *for this case* because it hides the most
interesting machinery — interrupt transport, state sync, tool rendering —
inside its runtime and Python SDK. With assistant-ui's headless primitives,
the approval tray, the tool transparency cards, and the resume flow are all
application code that can be read line by line. UI state for approvals is
always fetched back from the server (the checkpointer), never trusted locally.

## 12. Testing: scripted LLM for logic, live LLM for behavior

Two layers with different jobs:

- **Offline (53 tests, `make test`)** — the LLM is a `ScriptedChatModel`
  returning canned tool-call messages, everything else is real (graph,
  interrupts, checkpointer, SQLite triggers, API + SSE). Deterministic
  coverage of every HITL edge: no-write-before-approval, deny, restart
  survival, multi-pending, conflict rollback, swapped-db robustness.
- **Live evals (10 scenarios, `make eval`)** — the real model against a
  throwaway db copy, asserting *structure*, not wording: which tools ran,
  whether an interrupt fired, what changed in the database, which facts the
  answer contains. This is the layer that catches prompt regressions.

The split keeps CI fast and free while still measuring actual agent behavior.

## 13. One deliberate scope cut

Clinician double-booking is not prevented — the database only enforces room
overlaps, and the agent checks the clinician's calendar before proposing times
but nothing hard-stops a conflicting approval. Enforcing it app-side would
mean second-guessing the schema's intent with a second, weaker constraint
system; surfacing the db's own rules honestly seemed more valuable than
inventing stricter ones.
