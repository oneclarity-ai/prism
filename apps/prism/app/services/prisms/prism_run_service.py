"""Lease-coordinated, local monitoring runs for Prism v2.2."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.enums import PrismLifecycleState
from app.models.prisms.prism_v22 import Prism, PrismExternalEvent, PrismRun, PrismTriggerPolicy
from app.schemas.prisms.prism_v22 import (
    PrismTriggerPolicyRead,
    PrismTriggerPolicyUpdate,
)
from app.services.errors import ConflictError, DomainError, RuleViolationError
from app.services.prisms.prism_health_service import PrismHealthService
from app.services.prisms.prism_lifecycle_service import PrismLifecycleService
from app.services.prisms.prism_observation_service import PrismObservationService
from app.services.prisms.prism_retention_service import PrismRetentionService
from app.services.prisms.prism_teams_policy_service import PrismTeamsPolicyService


class PrismRunService:
    """Coordinates bounded local monitoring work without granting action authority."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT_DRIVEN = "event_driven"
    CONTINUOUS = "continuous"
    TRIGGER_MODES = {MANUAL, SCHEDULED, EVENT_DRIVEN, CONTINUOUS}
    TERMINAL_STATES = {"completed", "skipped", "failed", "cancelled"}
    MAX_ATTEMPTS = 2

    @classmethod
    def get_policy(cls, db: Session, prism_id: uuid.UUID) -> PrismTriggerPolicy:
        PrismLifecycleService.get(db, prism_id)
        policy = db.scalar(
            select(PrismTriggerPolicy).where(PrismTriggerPolicy.prism_id == prism_id)
        )
        if policy is not None:
            return policy
        policy = PrismTriggerPolicy(prism_id=prism_id)
        db.add(policy)
        db.commit()
        return db.get(PrismTriggerPolicy, policy.id) or policy

    @classmethod
    def policy_read(
        cls, db: Session, prism_id: uuid.UUID, *, now: datetime | None = None
    ) -> PrismTriggerPolicyRead:
        policy = cls.get_policy(db, prism_id)
        return PrismTriggerPolicyRead(
            prism_id=policy.prism_id,
            mode=policy.mode,
            revision=policy.revision,
            enabled=policy.enabled,
            timezone=policy.timezone,
            daily_time=policy.daily_time,
            missed_run_policy=policy.missed_run_policy,
            continuous_interval_seconds=policy.continuous_interval_seconds,
            event_coalesce_seconds=policy.event_coalesce_seconds,
            event_cursor_at=policy.event_cursor_at,
            last_scheduled_for=policy.last_scheduled_for,
            next_scheduled_for=cls.next_scheduled_for(policy, now=now),
            local_scheduler_enabled=get_settings().prism_v22_scheduler_enabled,
        )

    @classmethod
    def update_policy(
        cls,
        db: Session,
        prism_id: uuid.UUID,
        payload: PrismTriggerPolicyUpdate,
    ) -> PrismTriggerPolicyRead:
        cls._validate_schedule(payload.timezone, payload.daily_time)
        policy = cls.get_policy(db, prism_id)
        policy = (
            db.scalar(
                select(PrismTriggerPolicy)
                .where(PrismTriggerPolicy.id == policy.id)
                .with_for_update()
            )
            or policy
        )
        if policy.revision != payload.expected_revision:
            raise ConflictError("Run schedule changed; refresh before saving")
        for field, value in payload.model_dump(exclude={"expected_revision"}).items():
            setattr(policy, field, value)
        policy.revision += 1
        db.commit()
        return cls.policy_read(db, prism_id)

    @classmethod
    def list_runs(cls, db: Session, prism_id: uuid.UUID) -> tuple[list[PrismRun], int]:
        PrismLifecycleService.get(db, prism_id)
        statement = (
            select(PrismRun)
            .where(PrismRun.prism_id == prism_id)
            .order_by(PrismRun.created_at.desc(), PrismRun.id.desc())
        )
        return list(db.scalars(statement.limit(30))), int(
            db.scalar(select(func.count(PrismRun.id)).where(PrismRun.prism_id == prism_id)) or 0
        )

    @classmethod
    def run_manual(cls, db: Session, prism_id: uuid.UUID) -> PrismRun:
        """Create and attempt one explicit manager-requested monitoring run."""

        policy = cls.get_policy(db, prism_id)
        run = cls._enqueue(
            db,
            prism_id=prism_id,
            policy=policy,
            trigger_type=cls.MANUAL,
            occurrence_key=f"manual:{uuid.uuid4()}",
            scheduled_for=None,
        )
        cls.process_queued(db)
        return db.get(PrismRun, run.id) or run

    @classmethod
    def cycle(cls, db: Session, *, now: datetime | None = None) -> dict[str, int]:
        """One reload-safe scheduler cycle. It is harmless to call from two workers."""

        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        recovered = cls.recover_expired_leases(db, now=current)
        queued = skipped = 0
        policies = list(
            db.scalars(
                select(PrismTriggerPolicy)
                .options(selectinload(PrismTriggerPolicy.prism))
                .join(Prism, Prism.id == PrismTriggerPolicy.prism_id)
                .where(
                    Prism.state == PrismLifecycleState.ACTIVE, PrismTriggerPolicy.enabled.is_(True)
                )
            )
        )
        for policy in policies:
            if policy.mode == cls.SCHEDULED:
                created, was_skipped = cls._enqueue_due_schedule(db, policy, current)
                queued += int(created)
                skipped += int(was_skipped)
            elif policy.mode == cls.CONTINUOUS:
                queued += int(cls._enqueue_continuous_if_due(db, policy, current))
            elif policy.mode == cls.EVENT_DRIVEN:
                queued += int(cls._enqueue_coalesced_event_run(db, policy, current))
        processed = cls.process_queued(db, now=current)
        cls._compact_if_due(db, current)
        return {
            "recovered": recovered,
            "queued": queued,
            "skipped": skipped,
            "processed": processed,
        }

    _last_compaction: datetime | None = None

    @classmethod
    def _compact_if_due(cls, db: Session, now: datetime) -> None:
        """Retention runs at most hourly and must never break a scheduler cycle."""

        if cls._last_compaction and now - cls._last_compaction < timedelta(hours=1):
            return
        cls._last_compaction = now
        try:
            PrismRetentionService.compact(db, now)
        except Exception:
            db.rollback()

    @classmethod
    def recover_expired_leases(cls, db: Session, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        stale = list(
            db.scalars(
                select(PrismRun)
                .where(PrismRun.state == "running", PrismRun.lease_expires_at < current)
                .with_for_update()
            )
        )
        for run in stale:
            if run.attempt_count >= cls.MAX_ATTEMPTS:
                run.state = "failed"
                run.safe_error = "The local monitoring lease expired twice; run it again manually."
                run.completed_at = current
            else:
                run.state = "queued"
                run.lease_owner = None
                run.lease_expires_at = None
                run.safe_error = "Recovered after a local restart."
        if stale:
            db.commit()
        return len(stale)

    @classmethod
    def process_queued(cls, db: Session, *, now: datetime | None = None) -> int:
        """Claim up to the global budget, then perform only bounded Graph reads."""

        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        # A session-level PostgreSQL advisory lock serializes local reloads and
        # API-triggered runs. It lives on its own connection: the work below commits,
        # and a pooled session may hop connections, which would strand the lock on
        # one connection and silently stop every later run.
        lock_connection = None
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            lock_connection = bind.connect()
            if not lock_connection.execute(text("SELECT pg_try_advisory_lock(22072201)")).scalar():
                lock_connection.close()
                return 0
        try:
            settings = get_settings()
            running = int(
                db.scalar(select(func.count(PrismRun.id)).where(PrismRun.state == "running")) or 0
            )
            available = max(0, settings.prism_v22_scheduler_global_concurrency - running)
            if not available:
                return 0
            candidates = list(
                db.scalars(
                    select(PrismRun)
                    .where(PrismRun.state == "queued")
                    .order_by(PrismRun.created_at, PrismRun.id)
                    .limit(available)
                )
            )
            processed = 0
            for candidate in candidates:
                claimed = cls._claim(db, candidate.id, current)
                if claimed is None:
                    continue
                cls._execute_claimed(db, claimed.id, current)
                processed += 1
            return processed
        finally:
            if lock_connection is not None:
                try:
                    lock_connection.execute(text("SELECT pg_advisory_unlock(22072201)"))
                finally:
                    lock_connection.close()

    @classmethod
    def next_scheduled_for(
        cls, policy: PrismTriggerPolicy, *, now: datetime | None = None
    ) -> datetime | None:
        if not policy.enabled or policy.mode != cls.SCHEDULED:
            return None
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        zone, schedule_time = cls._schedule_parts(policy.timezone, policy.daily_time)
        local_now = current.astimezone(zone)
        candidate = cls._local_schedule(local_now.date(), schedule_time, zone)
        if candidate <= local_now:
            candidate = cls._local_schedule(
                local_now.date() + timedelta(days=1), schedule_time, zone
            )
        return candidate.astimezone(timezone.utc)

    @classmethod
    def _enqueue_due_schedule(
        cls, db: Session, policy: PrismTriggerPolicy, now: datetime
    ) -> tuple[bool, bool]:
        zone, schedule_time = cls._schedule_parts(policy.timezone, policy.daily_time)
        local_now = now.astimezone(zone)
        scheduled_local = cls._local_schedule(local_now.date(), schedule_time, zone)
        if scheduled_local > local_now:
            return False, False
        scheduled_for = scheduled_local.astimezone(timezone.utc)
        if policy.last_scheduled_for is not None and policy.last_scheduled_for >= scheduled_for:
            return False, False
        occurrence_key = f"scheduled:{scheduled_for.isoformat()}"
        overdue = (now - scheduled_for).total_seconds()
        if (
            overdue > get_settings().prism_v22_schedule_catch_up_seconds
            and policy.missed_run_policy == "skip"
        ):
            run = cls._enqueue(
                db,
                prism_id=policy.prism_id,
                policy=policy,
                trigger_type=cls.SCHEDULED,
                occurrence_key=occurrence_key,
                scheduled_for=scheduled_for,
                initial_state="skipped",
                safe_error="Skipped because the local Prism scheduler was offline past its catch-up window.",
            )
            policy.last_scheduled_for = scheduled_for
            db.commit()
            return run is not None, True
        run = cls._enqueue(
            db,
            prism_id=policy.prism_id,
            policy=policy,
            trigger_type=cls.SCHEDULED,
            occurrence_key=occurrence_key,
            scheduled_for=scheduled_for,
        )
        policy.last_scheduled_for = scheduled_for
        db.commit()
        return run is not None, False

    @classmethod
    def _enqueue_continuous_if_due(
        cls, db: Session, policy: PrismTriggerPolicy, now: datetime
    ) -> bool:
        interval = policy.continuous_interval_seconds
        window = int(now.timestamp()) // interval
        occurrence_key = f"continuous:{window}"
        if db.scalar(
            select(PrismRun.id).where(
                PrismRun.prism_id == policy.prism_id, PrismRun.occurrence_key == occurrence_key
            )
        ):
            return False
        cls._enqueue(
            db,
            prism_id=policy.prism_id,
            policy=policy,
            trigger_type=cls.CONTINUOUS,
            occurrence_key=occurrence_key,
            scheduled_for=now,
        )
        return True

    @classmethod
    def _enqueue_coalesced_event_run(
        cls, db: Session, policy: PrismTriggerPolicy, now: datetime
    ) -> bool:
        statement = select(PrismExternalEvent).where(PrismExternalEvent.prism_id == policy.prism_id)
        if policy.event_cursor_at is not None:
            statement = statement.where(PrismExternalEvent.occurred_at > policy.event_cursor_at)
        events = list(
            db.scalars(
                statement.order_by(PrismExternalEvent.occurred_at, PrismExternalEvent.id).limit(500)
            )
        )
        if not events or events[-1].created_at > now - timedelta(
            seconds=policy.event_coalesce_seconds
        ):
            return False
        last_event = events[-1]
        occurrence_key = f"event:{last_event.id}"
        if db.scalar(
            select(PrismRun.id).where(
                PrismRun.prism_id == policy.prism_id, PrismRun.occurrence_key == occurrence_key
            )
        ):
            return False
        cls._enqueue(
            db,
            prism_id=policy.prism_id,
            policy=policy,
            trigger_type=cls.EVENT_DRIVEN,
            occurrence_key=occurrence_key,
            scheduled_for=now,
            input_event_count=len(events),
        )
        policy.event_cursor_at = last_event.occurred_at
        db.commit()
        return True

    @classmethod
    def _enqueue(
        cls,
        db: Session,
        *,
        prism_id: uuid.UUID,
        policy: PrismTriggerPolicy,
        trigger_type: str,
        occurrence_key: str,
        scheduled_for: datetime | None,
        input_event_count: int = 0,
        initial_state: str = "queued",
        safe_error: str | None = None,
    ) -> PrismRun:
        prism = PrismLifecycleService.get(db, prism_id)
        source_policy = PrismTeamsPolicyService.get(db, prism_id)
        run = PrismRun(
            prism_id=prism_id,
            trigger_policy_id=policy.id,
            trigger_type=trigger_type,
            occurrence_key=occurrence_key,
            state=initial_state,
            agreement_revision=prism.agreement_revision,
            source_policy_revision=source_policy.revision,
            budget={
                "source_limit": get_settings().v22_teams_poll_source_limit,
                "messages_per_source": get_settings().v22_teams_poll_message_limit,
            },
            input_event_count=input_event_count,
            scheduled_for=scheduled_for,
            completed_at=datetime.now(timezone.utc) if initial_state == "skipped" else None,
            safe_error=safe_error,
        )
        db.add(run)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(PrismRun).where(
                    PrismRun.prism_id == prism_id, PrismRun.occurrence_key == occurrence_key
                )
            )
            if existing is None:
                raise
            return existing
        return db.get(PrismRun, run.id) or run

    @classmethod
    def _claim(cls, db: Session, run_id: uuid.UUID, now: datetime) -> PrismRun | None:
        run = db.scalar(select(PrismRun).where(PrismRun.id == run_id).with_for_update())
        if run is None or run.state != "queued":
            return None
        prism = db.get(Prism, run.prism_id)
        if prism is None or prism.state != PrismLifecycleState.ACTIVE:
            run.state = "skipped"
            run.safe_error = "Skipped because this Prism is not active."
            run.completed_at = now
            db.commit()
            return None
        policy = db.get(PrismTriggerPolicy, run.trigger_policy_id)
        if policy is None or (
            run.trigger_type != cls.MANUAL
            and (not policy.enabled or policy.mode != run.trigger_type)
        ):
            run.state = "skipped"
            run.safe_error = "Skipped because this monitoring schedule changed before it ran."
            run.completed_at = now
            db.commit()
            return None
        blocked = PrismHealthService.block_reason(db, run.prism_id, run.trigger_type, now)
        if blocked is not None:
            run.state = "skipped"
            run.safe_error = blocked
            run.completed_at = now
            db.commit()
            return None
        another_for_prism = db.scalar(
            select(PrismRun.id).where(
                PrismRun.prism_id == run.prism_id,
                PrismRun.state == "running",
                PrismRun.id != run.id,
            )
        )
        if another_for_prism is not None:
            # Keep this one queued. The existing run owns the per-Prism lease
            # and a later local cycle will pick it up safely.
            return None
        run.state = "running"
        run.attempt_count += 1
        run.started_at = now
        run.lease_owner = f"local:{uuid.uuid4().hex[:12]}"
        run.lease_expires_at = now + timedelta(
            seconds=get_settings().prism_v22_scheduler_lease_seconds
        )
        run.safe_error = None
        db.commit()
        return db.get(PrismRun, run.id)

    @classmethod
    def _execute_claimed(cls, db: Session, run_id: uuid.UUID, now: datetime) -> None:
        run = db.get(PrismRun, run_id)
        if run is None or run.state != "running":
            return
        try:
            sync = PrismTeamsPolicyService.sync(db, run.prism_id)
            evaluation = PrismObservationService.evaluate_run(
                db, prism_id=run.prism_id, run_id=run_id, now=now
            )
            run = db.get(PrismRun, run_id)
            if run is None:
                return
            run.state = "completed"
            finished = datetime.now(timezone.utc)
            run.result = {
                **sync.model_dump(mode="json"),
                "signal_evaluation": evaluation,
                # Counts only: no message text, credentials, or tokens.
                "metrics": {
                    "duration_ms": int(
                        (finished - (run.started_at or finished)).total_seconds() * 1000
                    ),
                    "graph_reads": sync.scanned_chats,
                    "events_created": sync.created_events,
                    "candidates": int(evaluation.get("candidates", 0)),
                    "observations_created": int(evaluation.get("created", 0)),
                    "model_calls": int(evaluation.get("model_calls", 0)),
                    "suppressed_by_preference": int(evaluation.get("suppressed_by_preference", 0)),
                },
            }
            run.completed_at = finished
            run.lease_expires_at = None
            run.lease_owner = None
            if sync.status == "degraded":
                run.safe_error = (
                    sync.source_errors[0]["detail"] if sync.source_errors else "Teams read degraded"
                )
            db.commit()
        except DomainError as exc:
            cls._fail_run(db, run_id, exc.detail)
        except Exception:
            cls._fail_run(db, run_id, "The local monitoring run failed. Try again manually.")

    @staticmethod
    def _fail_run(db: Session, run_id: uuid.UUID, safe_error: str) -> None:
        db.rollback()  # a failed flush leaves the session unusable until rolled back
        run = db.get(PrismRun, run_id)
        if run is None:
            return
        run.state = "failed"
        run.safe_error = safe_error
        run.completed_at = datetime.now(timezone.utc)
        run.lease_expires_at = None
        run.lease_owner = None
        db.commit()

    @staticmethod
    def _validate_schedule(timezone_name: str, daily_time: str) -> None:
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise RuleViolationError(
                "Choose a valid IANA timezone, for example Asia/Kolkata"
            ) from exc
        try:
            time.fromisoformat(daily_time)
        except ValueError as exc:
            raise RuleViolationError("Choose a schedule time in HH:MM format") from exc

    @classmethod
    def _schedule_parts(cls, timezone_name: str, daily_time: str) -> tuple[ZoneInfo, time]:
        cls._validate_schedule(timezone_name, daily_time)
        return ZoneInfo(timezone_name), time.fromisoformat(daily_time)

    @staticmethod
    def _local_schedule(day, schedule_time: time, zone: ZoneInfo) -> datetime:
        """Resolve a DST gap forward, and use the first occurrence in an overlap."""

        candidate = datetime.combine(day, schedule_time, tzinfo=zone).replace(fold=0)
        resolved = candidate.astimezone(timezone.utc).astimezone(zone)
        if (resolved.hour, resolved.minute) == (schedule_time.hour, schedule_time.minute):
            return candidate
        # A nonexistent local time is moved forward to the first valid minute.
        for minutes in range(1, 181):
            shifted = candidate + timedelta(minutes=minutes)
            round_trip = shifted.astimezone(timezone.utc).astimezone(zone)
            if (round_trip.hour, round_trip.minute) == (shifted.hour, shifted.minute):
                return shifted
        return resolved
