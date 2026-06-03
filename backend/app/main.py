"""FastAPI application.

The agent graph is built once at startup with a SQLite-backed checkpointer
(separate file from the clinical database), so pending approvals survive
process restarts. Tests pass a prebuilt graph instead.
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.graph import build_graph
from app.api.routes import router
from app.config import settings


def create_app(graph: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if graph is not None:
            yield
            return
        async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_path)) as saver:
            app.state.graph = build_graph(checkpointer=saver)
            yield

    app = FastAPI(title="Clinical Operations Assistant", lifespan=lifespan)
    if graph is not None:
        app.state.graph = graph

    # Both shipped setups are same-origin (Vite dev proxy / nginx both forward
    # /api), so this only matters if the SPA is served from another host.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
