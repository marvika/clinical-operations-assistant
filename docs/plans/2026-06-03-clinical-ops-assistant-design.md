# Clinical Operations Assistant — Implementation Plan

## Context

Technical interview case (see `README.md`): build an agentic clinical-operations assistant over a provided SQLite `database.db` (schema frozen; reviewers may swap in a different db with the same schema). Must: interpret intent, plan/execute multi-step tool calls, answer coordinator questions from db-backed tool results, and gate **all mutating actions behind human approval** (approve/deny) that remains addressable across turns. Read-only tools run directly. Full transparency of tool calls (name/params/results). Frozen clock: `2025-03-16T09:00:00Z`. The candidate presents the code live and wants to discuss orchestration-pattern decisions — code clarity is a first-class requirement.

## Decisions (researched + user-confirmed)

| Decision | Choice | Why |
| --- | --- | --- |
| Orchestration | **LangGraph 1.x, custom `StateGraph`** (not `create_react_agent`) | Native durable HITL via `interrupt()`/`Command(resume=...)` + checkpointer; explicit graph = line-by-line explainable. Beat MS Agent Framework (workflow-centric HITL = ceremony for single agent) and Pydantic AI (app-managed approval persistence). |
| LLM | **`gpt-4.1-mini` only**, temperature 0, via Azure OpenAI v1 endpoint (`ChatOpenAI(base_url=OPENAI_BASE_URL)`, `langchain-openai>=1.0.1`) | `gpt-5.2-chat` is chat-tuned with documented unreliable/no tool support on Azure — likely a deliberate trap in the case. Single model = the production call unless evals show gaps. |
| Frontend | **Vite + React + TS + Tailwind + assistant-ui** | Polished chat; tool cards + runtime wiring are our code (explainable). CopilotKit deliberately rejected (hidden machinery, Node runtime layer) — documented talking point. No Next.js (no SSR need). |
| Frontend↔backend wire | **AI-SDK data-stream protocol via Python `assistant-stream` + assistant-ui data-stream runtime** — NOT `@assistant-ui/react-langgraph` | react-langgraph expects LangGraph Platform/Cloud REST API; we're self-hosted FastAPI. Canonical reference: `Yonom/assistant-ui-langgraph-fastapi`, extended with checkpointer + interrupt approval as a custom data part. |
| Tools | **Pure domain-specific typed tools** (~13: 9 read, 4 write), no SQL escape hatch | Least-privilege; airtight HITL gating (writes = closed set `WRITE_TOOLS`); every tool testable. |
| HITL persistence | `AsyncSqliteSaver` checkpointer in **separate `checkpoints.db`** (gitignored) | Pending approvals survive restarts; provided `database.db` untouched. |
| Containerization | **docker-compose (api + web) + native dual-path**; Makefile | `database.db` bind-mounted (reviewer swaps without rebuild); uv multi-stage image; demo runs natively (hot reload). |
| Testing | Unit + integration (scripted fake LLM, tmp db copy) + **live-LLM scenario evals** (~10, pytest marker) | "Focused tests" + user wants evals. |
| Interface | Web UI only (no CLI) | YAGNI. |

## Key schema/robustness facts (verified against provided db)

- 7 tables: patients(19), clinicians(2), locations(2), appointments(14), journal_notes(19), lab_results(9), service_assignments(3)
- `patients.primary_clinician_id` is **TEXT** referencing INTEGER PK → joins must cast (tolerantly, both ways — a swapped db might use INTEGER)
- **Triggers abort overlapping appointments per location** (INSERT + UPDATE), raising `IntegrityError` "Appointment overlaps existing booking for location" → catch, rollback, surface as tool error so the model narrates it
- Patient names have **no unique constraint** → disambiguation required; clinicians/locations are UNIQUE COLLATE NOCASE
- Timestamps ISO-8601 `+00:00` → compare as ISO strings (lexicographically safe); lab `flag` ∈ {LOW, HIGH, NORMAL}, nullable fields
- Frozen now 2025-03-16 is a **Sunday** → "next week" = Mon 2025-03-24 .. Sun 2025-03-30 (pin in prompt + helper + test)
- Reviewers swap the db → zero hardcoded names/ids anywhere; resolve names via lookup tools

## Architecture

```text
React SPA (Vite, assistant-ui) ──data-stream/SSE──► FastAPI ──► LangGraph StateGraph ──► tools ──► database.db
                                                       │               │
                                                       │          AsyncSqliteSaver (checkpoints.db, thread_id per chat)
                                                       └── POST /api/approve → Command(resume={approved,...})
```

## Repo structure

```text
aidn/
├── README.md  Makefile  docker-compose.yml  .env  .gitignore(+checkpoints.db)  database.db
├── docs/
│   ├── design.md            # architecture, sequence diagrams
│   ├── decisions.md         # interview talking points (see §Talking points)
│   └── transcripts/         # example sessions (3 README queries + deny path)
├── backend/
│   ├── pyproject.toml  uv.lock  Dockerfile  .env.example
│   └── app/
│       ├── config.py        # pydantic-settings: base_url, api_key, model, db paths, frozen_now
│       ├── clock.py         # now() indirection = 2025-03-16T09:00:00+00:00; iso(), days_from_now(), start_of_next_week()
│       ├── db/connection.py # per-request sqlite3 conn, Row factory, PRAGMA foreign_keys
│       ├── db/repository.py # parameterized read/write functions, IntegrityError translation
│       ├── domain/schemas.py / resolve.py   # Pydantic models; name→id resolution + ambiguity
│       ├── tools/reads.py / writes.py / __init__.py  # @tool defs + WRITE_TOOLS set
│       ├── agent/state.py / prompt.py / llm.py / graph.py
│       ├── stream/datastream.py  # LangGraph astream → assistant-stream RunController bridge
│       ├── api/routes.py / models.py / deps.py
│       ├── main.py          # app, CORS, lifespan (checkpointer)
│       └── tests/ (unit/, integration/, evals/, conftest.py)
└── frontend/
    ├── package.json  vite.config.ts  tailwind  Dockerfile  index.html
    └── src/
        ├── App.tsx  main.tsx  index.css
        ├── runtime/useClinicalRuntime.ts   # data-stream runtime → /api/chat, thread_id mgmt
        ├── components/Thread.tsx / ToolCallCard.tsx / ApprovalCard.tsx
        └── lib/api.ts                      # postApproval, state rehydration
```

## Backend design

**Tools** (LangChain `@tool`, Pydantic args; reads open short-lived conns):
- Reads (direct): `find_patient(name)`, `find_clinician(name)`, `find_location(name)` (return candidate lists for disambiguation), `get_patient_details(patient_id)`, `list_upcoming_appointments(days=7, clinician_id?, patient_id?)`, `get_abnormal_labs(days=14, flag="HIGH")`, `list_patient_labs`, `list_patient_notes`, `list_service_assignments`
- Writes (HITL-gated): `create_appointment`, `update_appointment`, `add_journal_note`, `create_service_assignment`

**Graph** (`agent/graph.py`):
- State: `messages: Annotated[list[AnyMessage], add_messages]` — pending-approval state lives in checkpointer+interrupt, not custom fields
- Nodes: `agent` (LLM with bound tools) →conditional→ `tools` (custom node, not prebuilt ToolNode) → back to `agent`; END when no tool_calls
- In `tools` node, per tool_call: if name ∈ `WRITE_TOOLS` → `decision = interrupt({type:"approval_request", tool, args, tool_call_id})`; approved → execute + ToolMessage(result); denied → ToolMessage("DENIED by human reviewer. Reason: … Do not retry; inform the user."); reads execute immediately
- **Idempotency rule**: node restarts from top on resume → no side effects before `interrupt()`; reads re-running is harmless. Multiple write calls in one turn → sequential interrupts, resume-by-id; tested explicitly
- Compile with `AsyncSqliteSaver(checkpoints.db)`

**System prompt** (`agent/prompt.py`): frozen now verbatim + relative-date rules ("next week" = computed Mon–Sun block with concrete dates); "never guess ids — resolve names via find_* tools; ask user when ambiguous, report when no match"; approval awareness ("if denied, don't retry, explain"); brief tool transparency in answers.

**API** (`/api`):
- `POST /api/chat` `{thread_id?, messages:[...]}` → assistant-stream `DataStreamResponse`: text deltas, tool-call/tool-result parts, custom `data-thread {thread_id}` part, and `data-approval_request {tool, args, tool_call_id, interrupt_id}` when graph interrupts (check `aget_state(config).interrupts` after stream)
- `POST /api/approve` `{thread_id, decisions:[{tool_call_id, approved, reason?}]}` → resumes via `Command(resume=...)`, returns continuing DataStreamResponse
- `GET /api/threads/{id}/state` → messages + pending approvals (UI rehydration after refresh/restart — proves cross-turn addressability)
- `GET /api/health`

## Frontend design

- assistant-ui data-stream runtime (`@assistant-ui/react-ai-sdk`; pin exact hook name against installed types in Phase 4) pointed at `/api/chat`; `thread_id` in localStorage, captured from `data-thread` part
- `ToolCallCard.tsx`: generic fallback tool UI — name, pretty JSON args, result (transparency requirement)
- `ApprovalCard.tsx`: renders approval_request data part with human-readable summary (resolved names, not raw ids) + Approve/Deny buttons (deny → optional reason) → `postApproval` → continuation stream appends to thread; state survives refresh via `/state`
- New-chat button resets thread_id

## Testing & evals

- **Fake**: LLM only (`ScriptedChatModel` returning predetermined AIMessages w/ tool_calls). DB = tmp copy of `database.db` per test; tmp checkpoints db
- Unit: clock/date windows ("next week" = 2025-03-24..30), resolve (0/1/many matches, TEXT/INT cast), repository queries, tool schemas + write inserts
- Integration (real graph, scripted LLM): `test_hitl_flow` (interrupt fires, no row before approve, row after), `test_deny_path` (no insert, DENIED ToolMessage, narration), `test_trigger_abort` (overlap IntegrityError surfaced, no partial commit), `test_multi_pending` (approve one + deny one → exactly one insert), `test_db_swapped` (alternate fixture db), `test_read_no_interrupt`
- Evals (`@pytest.mark.eval`, live LLM, structural assertions): the 3 README queries, ambiguous-name disambiguation, unknown-name no-write, deny no-retry, overlap surfaced, multi-turn follow-up reference, read stays direct, update gated. `make test` (offline) vs `make eval` (needs .env)

## Implementation order

0. **Scaffold**: uv backend, Vite frontend, Makefile, .gitignore, compose skeleton → imports + dev servers run
1. **DB layer**: connection, repository, resolve, clock → unit tests green
2. **Tools**: reads/writes + WRITE_TOOLS → test_tools green; manual sanity vs sqlite
3. **Graph + HITL** (no HTTP): state/prompt/llm/graph + AsyncSqliteSaver → all integration tests green
4. **FastAPI + datastream bridge**: routes + bridge + lifespan → curl shows stream parts; approve resumes
5. **Frontend**: runtime, Thread, ToolCallCard, ApprovalCard → manual demo of 3 README queries, approve/deny, refresh keeps pending
6. **Evals + docs + docker**: scenarios, design.md, decisions.md, transcripts, README, Dockerfiles, compose → `make eval` ≥9/10, `docker compose up` healthy, `database.db` git-clean

## Edge cases

- All timestamps UTC-aware; never naive datetime, never `datetime.now()`
- Tolerant id casts both directions (swapped db may differ)
- Clinician double-booking NOT db-enforced → deliberately rely on db trigger only (documented scope choice)
- Per-request connections; AsyncSqliteSaver single-process fine for demo
- Empty results handled gracefully ("none found")

## Talking points (docs/decisions.md)

Custom StateGraph vs create_react_agent · interrupt()+checkpointer vs side-channel flag (incl. node-restart/idempotency trade-off) · data-stream protocol vs LangGraph Platform runtime · separate checkpoints.db · frozen clock injection · schema quirks isolated in data layer · name disambiguation policy · denial as ToolMessage · scripted-LLM tests vs live evals · gpt-4.1-mini over gpt-5.2-chat (tool-support trap) · CopilotKit evaluated, rejected for explainability

## Verification

- `make test` → unit + integration green (offline)
- `make eval` → ≥9/10 live scenarios pass
- Manual: `make dev`, run 3 README queries, approve + deny a create_appointment, **restart backend mid-pending-approval** and confirm still addressable, refresh browser keeps pending card
- `docker compose up` cold start; swap database.db copy to simulate reviewer
- `git status`: provided database.db unmodified by tests; checkpoints.db ignored

## Key references

- https://github.com/Yonom/assistant-ui-langgraph-fastapi (wire-format reference)
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://www.assistant-ui.com/docs (runtime hook names — verify at install time)
