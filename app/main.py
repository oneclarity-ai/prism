import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.blockers import router as blockers_router
from app.api.routes.commitments import router as commitments_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.daily_updates import router as daily_updates_router
from app.api.routes.employees import router as employees_router
from app.api.routes.escalations import router as escalations_router
from app.api.routes.health import router as health_router
from app.api.routes.projects import router as projects_router
from app.api.routes.management import router as management_router
from app.api.routes.management_context import router as management_context_router
from app.api.routes.memory import router as memory_router
from app.api.routes.microsoft import router as microsoft_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.llm_usage import router as llm_usage_router
from app.api.routes.intelligence import router as intelligence_router
from app.core.config import get_settings
from app.core.security import protect_operator_api
from app.db.session import SessionLocal
import app.models  # noqa: F401 - register all ORM relationship targets at startup
from app.services.errors import DomainError
from app.services.automation_service import DailyAutomationService


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    stop_event = asyncio.Event()

    async def scheduler_loop() -> None:
        def run_cycle_in_worker():
            db = SessionLocal()
            try:
                DailyAutomationService.run_cycle(db)
            except Exception:
                # The loop stays alive for transient failures, but a manager
                # must be able to see exactly which scheduled job failed.
                logger.exception("daily_manager_scheduler_cycle_failed")
            finally:
                db.close()
        while not stop_event.is_set():
            await asyncio.to_thread(run_cycle_in_worker)
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=max(15, settings.automation_scheduler_interval_seconds)
                )
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(scheduler_loop()) if settings.automation_scheduler_enabled else None
    try:
        yield
    finally:
        stop_event.set()
        if task is not None:
            await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.middleware("http")(protect_operator_api)

    @app.exception_handler(DomainError)
    def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    app.include_router(health_router)
    app.include_router(employees_router)
    app.include_router(projects_router)
    app.include_router(tasks_router)
    app.include_router(daily_updates_router)
    app.include_router(blockers_router)
    app.include_router(commitments_router)
    app.include_router(conversations_router)
    app.include_router(escalations_router)
    app.include_router(management_router)
    app.include_router(management_context_router)
    app.include_router(memory_router)
    app.include_router(microsoft_router)
    app.include_router(llm_usage_router)
    app.include_router(intelligence_router)
    app.mount(
        "/dashboard",
        StaticFiles(directory=Path(__file__).parent / "static", html=True),
        name="dashboard",
    )
    return app


app = create_app()
