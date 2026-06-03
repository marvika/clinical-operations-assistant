# Clinical Operations Assistant

An agentic chat assistant for care coordinators: it interprets intent, plans
multi-step tool calls over the provided SQLite database, answers questions
from tool results, and **pauses for human approval before any mutating
action**. Original case description: [docs/case.md](docs/case.md).

```text
React SPA (Vite + assistant-ui) ──SSE──► FastAPI ──► LangGraph agent ──► 13 typed tools ──► database.db
                                            │             │
                                            │       SqliteSaver checkpointer (checkpoints.db)
                                            └── approve/deny ──► Command(resume=…) at the interrupt
```

- **Reads** (9 tools) execute directly; **writes** (4 tools) hit a LangGraph
  `interrupt()` *before* any side effect and wait for approval.
- Pending approvals live in the checkpointer — they survive follow-up
  questions, page refreshes and backend restarts, and are listed in the UI's
  approval tray until decided.
- Every tool call is rendered in the transcript with its parameters and
  result (transparency cards).
- The clock is frozen at `2025-03-16T09:00:00Z` per the case description
  (`backend/app/clock.py`).

Design rationale and trade-offs: **[docs/decisions.md](docs/decisions.md)** ·
Example sessions: **[docs/transcripts/](docs/transcripts/)**

## Quickstart

Requires the provided `.env` in the repo root (see `.env.example`).

### Native (recommended for development / the live demo)

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
make backend    # FastAPI + hot reload on http://localhost:8000
make frontend   # Vite dev server on http://localhost:3000 (proxies /api)
```

Open <http://localhost:3000> — the three example queries from the case are
one-click suggestions.

### Docker

```bash
docker compose up --build    # web on :3000, api on :8000
```

`database.db` is bind-mounted: swap the file and restart to run against a
different database with the same schema — no rebuild.

## Tests

```bash
make test   # 53 offline tests: unit + integration (scripted LLM, no network)
make eval   # 10 live-LLM scenario evals against a throwaway db copy (needs .env)
```

The offline suite covers the full HITL state machine (no write before
approval, deny, restart survival, multiple pending actions, conflict
rollback) plus date logic and swapped-database robustness. The evals run the
real model and assert structure — tools called, interrupts fired, rows
written, facts present — never exact wording.

## Repository layout

```text
backend/app/
  clock.py            frozen "now" — the only place that knows the time
  db/                 connection + all SQL (parameterized, quirk-tolerant)
  domain/resolve.py   name → id resolution (ambiguity is a first-class case)
  tools/              9 read tools + 4 write tools; WRITE_TOOLS drives the gate
  agent/              system prompt, model factory, the two-node graph
  stream/             LangGraph events → AI SDK UI Message Stream (SSE)
  api/                /api/chat, /api/threads/{id}/state, /api/health
  tests/              unit / integration / evals
frontend/src/
  chat/ChatProvider.tsx      useChat ↔ assistant-ui wiring + approval context
  components/Thread.tsx      chat surface (headless primitives, own styling)
  components/ToolCallCard.tsx  per-tool transparency card
  components/PendingApprovals.tsx  the approve/deny tray
docs/                 case text, design decisions, example transcripts
```

## Notes for reviewers

- The provided `database.db` schema is never modified; LangGraph checkpoints
  live in a separate, gitignored `checkpoints.db` (`make clean` resets it).
- Of the two provided models, `gpt-5.2-chat` does not reliably support tool
  calling on Azure, so the agent runs on `gpt-4.1-mini` — see
  [docs/decisions.md §5](docs/decisions.md).
- To demonstrate restart persistence: create a booking, leave it pending,
  restart `make backend`, refresh the browser — the approval tray returns.
