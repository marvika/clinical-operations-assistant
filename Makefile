# Clinical Operations Assistant — developer entry points.
#
# Native development (recommended for the live demo):
#   make backend    # FastAPI with hot reload on :8000
#   make frontend   # Vite dev server on :3000 (proxies /api to :8000)
#
# Reviewer one-liner:
#   make up         # docker compose up --build

.PHONY: help backend frontend test eval up down clean

help:
	@grep -E '^[a-z]+:' Makefile | sed 's/:.*//' | sort

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:           ## offline unit + integration tests (no LLM, no network)
	cd backend && uv run pytest app/tests -m "not eval" -q

eval:           ## live-LLM scenario evals (requires .env with API key)
	cd backend && uv run pytest app/tests -m eval -q

up:
	docker compose up --build

down:
	docker compose down

clean:
	rm -f checkpoints.db
