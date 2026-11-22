"""Worker heartbeat: lets the API/UI know whether any worker is alive to pick up queued runs."""

import asyncio
import os
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.logging import log
from app.db.models import WorkerHeartbeat
from app.db.session import SessionLocal

INTERVAL_SEC = 5
ONLINE_WITHIN_SEC = 20

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


async def beat() -> None:
    async with SessionLocal() as s:
        stmt = insert(WorkerHeartbeat).values(worker_id=WORKER_ID, hostname=socket.gethostname(), pid=os.getpid())
        await s.execute(stmt.on_conflict_do_update(index_elements=["worker_id"], set_={"last_seen": func.now()}))
        # Tidy rows of workers that died without saying goodbye.
        await s.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.last_seen < func.now() - timedelta(hours=1)))
        await s.commit()


async def heartbeat_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await beat()
        except Exception as exc:  # noqa: BLE001 - a missed beat must not kill the worker
            log.warning("heartbeat_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL_SEC)
        except TimeoutError:
            pass


async def goodbye() -> None:
    async with SessionLocal() as s:
        await s.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == WORKER_ID))
        await s.commit()


async def workers_online(session) -> int:
    since = datetime.now(UTC) - timedelta(seconds=ONLINE_WITHIN_SEC)
    return await session.scalar(
        select(func.count()).select_from(WorkerHeartbeat).where(WorkerHeartbeat.last_seen >= since)
    )
