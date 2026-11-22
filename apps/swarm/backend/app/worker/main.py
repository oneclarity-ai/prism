"""Run worker: `uv run python -m app.worker.main`.

Claims queued runs with SELECT ... FOR UPDATE SKIP LOCKED (safe with several workers)
and executes up to MAX_CONCURRENT_RUNS at a time.
"""

import asyncio
import signal

from sqlalchemy import select, text

from app.computers.manager import manager as computers
from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.enums import RunStatus
from app.db.models import Agent, Run
from app.db.session import SessionLocal, engine
from app.worker.executor import claim_next, execute_run, recover_stale
from app.worker.heartbeat import WORKER_ID, goodbye, heartbeat_loop


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level, settings.log_json, service="worker", log_dir=settings.log_dir, log_sql=settings.log_sql
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await recover_stale()
    beats = asyncio.create_task(heartbeat_loop(stop))

    async def reaper() -> None:
        """Stop computers nobody has used for a while. Their browser profile is kept."""
        try:
            await computers.adopt()
        except Exception as exc:  # noqa: BLE001 - Docker may simply not be installed
            log.info("computers_unavailable", error=str(exc)[:200])
            return
        while not stop.is_set():
            try:
                async with SessionLocal() as s:
                    busy = set(
                        await s.scalars(
                            select(Agent.key).join(Run, Run.agent_id == Agent.id).where(Run.status == RunStatus.running)
                        )
                    )
                for key in await computers.reap_idle(busy):
                    log.info("computer_stopped_idle", key=key)
            except Exception as exc:  # noqa: BLE001
                log.warning("reaper_failed", error=str(exc)[:200])
            try:
                await asyncio.wait_for(stop.wait(), timeout=60)
            except TimeoutError:
                pass

    reaper_task = asyncio.create_task(reaper())

    async def recovery_loop() -> None:
        while not stop.is_set():
            try:
                await recover_stale()
            except Exception as exc:  # noqa: BLE001
                log.warning("run_recovery_failed", error=str(exc)[:200])
            try:
                await asyncio.wait_for(stop.wait(), timeout=max(5, settings.run_lease_seconds / 2))
            except TimeoutError:
                pass

    recovery_task = asyncio.create_task(recovery_loop())
    log.info("worker_ready", worker_id=WORKER_ID, max_concurrent_runs=settings.max_concurrent_runs)

    slots = asyncio.Semaphore(settings.max_concurrent_runs)
    running: set[asyncio.Task] = set()

    async def run_one(run_id) -> None:
        try:
            await execute_run(run_id)
        except Exception as exc:  # noqa: BLE001
            log.error("execute_failed", run_id=str(run_id), error=str(exc))
        finally:
            slots.release()

    while not stop.is_set():
        await slots.acquire()
        run_id = None
        try:
            run_id = await claim_next()
        except Exception as exc:  # noqa: BLE001 - e.g. database restarting
            log.warning("claim_failed", error=str(exc))
        if run_id is None:
            slots.release()
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
            except TimeoutError:
                pass
            continue
        t = asyncio.create_task(run_one(run_id))
        running.add(t)
        t.add_done_callback(running.discard)

    if running:
        log.info("worker_stopping", in_flight=len(running))
        for t in running:
            t.cancel()
        await asyncio.gather(*running, return_exceptions=True)
    await beats
    reaper_task.cancel()
    recovery_task.cancel()
    await asyncio.gather(reaper_task, recovery_task, return_exceptions=True)
    await goodbye()
    await engine.dispose()
    log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
