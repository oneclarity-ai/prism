import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import agents, analytics, auth, computers, health, org_chart, runs, secrets, targets, tasks
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, log
from app.db.session import engine

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("api_started")
    yield
    await engine.dispose()
    log.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        settings.log_level, settings.log_json, service="api", log_dir=settings.log_dir, log_sql=settings.log_sql
    )

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            ms = round((time.perf_counter() - started) * 1000, 1)
            path = request.url.path
            if not path.endswith("/health"):
                level = "error" if status >= 500 else "warning" if status >= 400 else "info"
                getattr(log, level)("request", method=request.method, path=path, status=status, ms=ms)
            structlog.contextvars.clear_contextvars()

    register_error_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    for module in (health, auth, agents, secrets, computers, targets, tasks, runs, org_chart, analytics):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
