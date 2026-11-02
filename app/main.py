import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401 - register all ORM relationship targets at startup
from app.api.routes.agent_v21 import router as agent_v21_router
from app.api.routes.blockers import router as blockers_router
from app.api.routes.brain import router as brain_router
from app.api.routes.commitments import router as commitments_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.daily_updates import router as daily_updates_router
from app.api.routes.employees import router as employees_router
from app.api.routes.escalations import router as escalations_router
from app.api.routes.health import router as health_router
from app.api.routes.intelligence import router as intelligence_router
from app.api.routes.llm_usage import router as llm_usage_router
from app.api.routes.management import router as management_router
from app.api.routes.management_context import router as management_context_router
from app.api.routes.memory import router as memory_router
from app.api.routes.microsoft import router as microsoft_router
from app.api.routes.people import router as people_router
from app.api.routes.prism_v22 import router as prism_v22_router
from app.api.routes.projects import router as projects_router
from app.api.routes.provider import router as provider_router
from app.api.routes.qa import router as qa_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.work import bridge as work_bridge_router
from app.api.routes.work import router as work_router
from app.core.config import get_settings
from app.core.security import protect_operator_api
from app.db.session import SessionLocal
from app.services.automation_service import DailyAutomationService
from app.services.errors import DomainError
from app.services.prism_run_service import PrismRunService
from app.services.provider_credential_service import ProviderCredentialService
from app.services.qa_run_service import QaRunService, make_client
from app.services.qa_spend_service import QaSpendService

logger = logging.getLogger(__name__)
QA_SPEND_SYNC_SECONDS = 60


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    stop_event = asyncio.Event()
    credential_db = SessionLocal()
    try:
        ProviderCredentialService.load(credential_db, settings)
    except Exception:
        logger.exception("provider_credential_startup_load_failed")
    finally:
        credential_db.close()

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
                    stop_event.wait(),
                    timeout=max(15, settings.automation_scheduler_interval_seconds),
                )
            except asyncio.TimeoutError:
                continue

    async def prism_scheduler_loop() -> None:
        def run_cycle_in_worker():
            db = SessionLocal()
            try:
                PrismRunService.cycle(db)
            except Exception:
                # Run ownership is database-leased, so a reload or a transient
                # Graph failure cannot turn this local loop into a busy retry.
                logger.exception("prism_v22_scheduler_cycle_failed")
            finally:
                db.close()

        while not stop_event.is_set():
            await asyncio.to_thread(run_cycle_in_worker)
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.prism_v22_scheduler_interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def qa_watcher_loop() -> None:
        def run_cycle_in_worker():
            db = SessionLocal()
            try:
                QaRunService.cycle(db)
            except Exception:
                logger.exception("qa_watcher_cycle_failed")
            finally:
                db.close()

        def sync_spend_in_worker():
            db = SessionLocal()
            try:
                with make_client() as client:
                    QaSpendService.sync(db, client)
            except Exception:
                logger.exception("qa_spend_sync_failed")
            finally:
                db.close()

        next_spend_sync = 0.0
        while not stop_event.is_set():
            await asyncio.to_thread(run_cycle_in_worker)
            if time.monotonic() >= next_spend_sync:
                await asyncio.to_thread(sync_spend_in_worker)
                next_spend_sync = time.monotonic() + QA_SPEND_SYNC_SECONDS
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.qa_watcher_interval_seconds
                )
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(scheduler_loop()) if settings.automation_scheduler_enabled else None
    qa_task = (
        asyncio.create_task(qa_watcher_loop())
        if settings.qa_watcher_enabled and settings.qa_swarm_configured
        else None
    )
    prism_task = (
        asyncio.create_task(prism_scheduler_loop())
        if settings.prism_v22_scheduler_enabled
        else None
    )
    try:
        yield
    finally:
        stop_event.set()
        # A scheduler cycle may be mid-way through a long Graph read. Give it a moment,
        # then stop waiting so Ctrl+C always shuts the server down; leases recover the run.
        for scheduler_task in (task, prism_task, qa_task):
            if scheduler_task is None:
                continue
            try:
                await asyncio.wait_for(scheduler_task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


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
    app.include_router(work_router)
    app.include_router(work_bridge_router)
    app.include_router(agent_v21_router)
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
    app.include_router(provider_router)
    app.include_router(people_router)
    app.include_router(prism_v22_router)
    app.include_router(qa_router)
    app.include_router(brain_router)
    app.mount(
        "/dashboard",
        StaticFiles(directory=Path(__file__).parent / "static", html=True),
        name="dashboard",
    )
    return app


app = create_app()
