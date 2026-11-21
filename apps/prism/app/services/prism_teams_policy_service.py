"""Durable Teams source policies and bounded local activity ingestion for Prism v2.2."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.prism_v22 import (
    PrismExternalEvent,
    PrismTeamsSourceCursor,
    PrismTeamsSourcePolicy,
    PrismTeamsSourceRule,
)
from app.schemas.agent_sources import TeamsChatSourceRead
from app.schemas.prism_v22 import PrismTeamsSourcePolicyUpdate, PrismTeamsSyncRead
from app.services.errors import ConflictError, DomainError, RuleViolationError
from app.services.microsoft_service import MicrosoftGraphClient, MicrosoftService
from app.services.prism_lifecycle_service import PrismLifecycleService
from app.services.teams_read_service import TeamsReadService


@dataclass(frozen=True)
class NormalizedTeamsActivityEvent:
    external_message_id: str
    event_kind: str
    source_version: str
    occurred_at: datetime
    sender_external_id: str | None
    sender_display_name: str
    body_text: str
    reply_to_external_id: str | None
    metadata: dict[str, Any]


class PrismTeamsPolicyService:
    """Owns source scoping before a Prism reads or stores Teams activity.

    Polling is intentionally pull-based in this phase: it works on localhost,
    needs no callback URL, and uses event keys plus durable cursors so a server
    restart or overlapping manual refresh cannot duplicate activity.
    """

    ALL_CHATS = "all_chats"
    INCLUDE_ONLY = "include_only"
    ALL_EXCEPT = "all_except"
    MODES = {ALL_CHATS, INCLUDE_ONLY, ALL_EXCEPT}

    @classmethod
    def get(cls, db: Session, prism_id: uuid.UUID) -> PrismTeamsSourcePolicy:
        PrismLifecycleService.get(db, prism_id)
        policy = db.scalar(
            select(PrismTeamsSourcePolicy)
            .options(selectinload(PrismTeamsSourcePolicy.rules))
            .where(PrismTeamsSourcePolicy.prism_id == prism_id)
        )
        if policy is not None:
            return policy
        policy = PrismTeamsSourcePolicy(prism_id=prism_id, mode=cls.ALL_CHATS, revision=1)
        db.add(policy)
        db.commit()
        return (
            db.scalar(
                select(PrismTeamsSourcePolicy)
                .options(selectinload(PrismTeamsSourcePolicy.rules))
                .where(PrismTeamsSourcePolicy.id == policy.id)
            )
            or policy
        )

    @classmethod
    def update(
        cls,
        db: Session,
        prism_id: uuid.UUID,
        payload: PrismTeamsSourcePolicyUpdate,
    ) -> PrismTeamsSourcePolicy:
        PrismLifecycleService.get(db, prism_id)
        policy = cls.get(db, prism_id)
        policy = (
            db.scalar(
                select(PrismTeamsSourcePolicy)
                .options(selectinload(PrismTeamsSourcePolicy.rules))
                .where(PrismTeamsSourcePolicy.id == policy.id)
                .with_for_update()
            )
            or policy
        )
        if policy.revision != payload.expected_revision:
            raise ConflictError("Teams monitoring scope changed; refresh before saving")

        external_ids = list(
            dict.fromkeys(value.strip() for value in payload.external_ids if value.strip())
        )
        if payload.mode == cls.ALL_CHATS and external_ids:
            raise RuleViolationError("All chats scope cannot include individual chat selections")
        catalog = TeamsReadService.list_sources(db)
        catalog_by_id = {item.external_id: item for item in catalog}
        unknown = [external_id for external_id in external_ids if external_id not in catalog_by_id]
        if unknown:
            raise RuleViolationError(
                "One or more selected Teams chats are no longer available. Refresh and choose again"
            )

        policy.mode = payload.mode
        policy.rules.clear()
        disposition = "include" if payload.mode == cls.INCLUDE_ONLY else "exclude"
        if payload.mode != cls.ALL_CHATS:
            for external_id in external_ids:
                source = catalog_by_id[external_id]
                policy.rules.append(
                    PrismTeamsSourceRule(
                        external_id=source.external_id,
                        disposition=disposition,
                        label=source.label,
                        chat_type=source.chat_type,
                        participants=source.participants,
                    )
                )
        policy.revision += 1
        policy.last_discovery_error = None
        db.commit()
        return cls.get(db, prism_id)

    @classmethod
    def allowed_sources(
        cls,
        db: Session,
        prism_id: uuid.UUID,
        *,
        catalog: list[TeamsChatSourceRead] | None = None,
    ) -> tuple[PrismTeamsSourcePolicy, list[TeamsChatSourceRead]]:
        """Return a policy and only chats it permits us to fetch/use as evidence."""

        policy = cls.get(db, prism_id)
        available = catalog if catalog is not None else TeamsReadService.list_sources(db)
        rules = {rule.external_id for rule in policy.rules}
        if policy.mode == cls.INCLUDE_ONLY:
            return policy, [source for source in available if source.external_id in rules]
        if policy.mode == cls.ALL_EXCEPT:
            return policy, [source for source in available if source.external_id not in rules]
        return policy, list(available)

    @classmethod
    def is_source_allowed(cls, db: Session, prism_id: uuid.UUID, external_id: str) -> bool:
        """A no-network policy check used immediately before a body fetch."""

        policy = cls.get(db, prism_id)
        restricted_ids = {rule.external_id for rule in policy.rules}
        if policy.mode == cls.INCLUDE_ONLY:
            return external_id in restricted_ids
        if policy.mode == cls.ALL_EXCEPT:
            return external_id not in restricted_ids
        return True

    @classmethod
    def sync(cls, db: Session, prism_id: uuid.UUID) -> PrismTeamsSyncRead:
        """Read a bounded slice of currently allowed chats and persist new events."""

        PrismLifecycleService.get(db, prism_id)
        policy = cls.get(db, prism_id)
        now = datetime.now(timezone.utc)
        try:
            catalog = TeamsReadService.list_sources(db)
        except DomainError as exc:
            policy.last_discovery_at = now
            policy.last_discovery_error = exc.detail
            db.commit()
            return cls._sync_result(
                prism_id,
                status="degraded",
                source_errors=[{"source_label": "Teams", "detail": exc.detail}],
                cursor=policy.discovery_cursor_external_id,
                discovered_at=now,
            )

        # One sync per Prism at a time; manual and scheduled runs must not insert the same events.
        db.execute(select(func.pg_advisory_xact_lock(prism_id.int & 0x7FFFFFFFFFFFFFFF)))
        policy, allowed = cls.allowed_sources(db, prism_id, catalog=catalog)
        scan_sources = cls._bounded_scan_sources(allowed, policy.discovery_cursor_external_id)
        settings = get_settings()
        connection = MicrosoftService.get_connection(db)
        graph = MicrosoftGraphClient(db, connection)
        source_errors: list[dict[str, str]] = []
        fetched = created = duplicates = 0
        seen_keys: set[str] = set()  # the session does not autoflush, so track this batch ourselves

        for source in scan_sources:
            cursor = cls._cursor(db, prism_id, source.external_id)
            try:
                raw_messages = graph.list_chat_messages(
                    source.external_id, limit=settings.v22_teams_poll_message_limit
                )
            except DomainError as exc:
                cursor.source_label = source.label
                cursor.last_polled_at = now
                cursor.status = "degraded"
                cursor.last_error = exc.detail
                source_errors.append({"source_label": source.label, "detail": exc.detail})
                continue

            fetched += len(raw_messages)
            newest: NormalizedTeamsActivityEvent | None = None
            for raw_message in raw_messages:
                event = cls.normalize_event(raw_message)
                if event is None:
                    continue
                if newest is None or (event.occurred_at, event.external_message_id) > (
                    newest.occurred_at,
                    newest.external_message_id,
                ):
                    newest = event
                dedupe_key = cls._dedupe_key(
                    connection.tenant_id,
                    connection.microsoft_user_id,
                    source.external_id,
                    event,
                )
                if dedupe_key in seen_keys:
                    duplicates += 1
                    continue
                seen_keys.add(dedupe_key)
                exists = db.scalar(
                    select(PrismExternalEvent.id).where(
                        PrismExternalEvent.prism_id == prism_id,
                        PrismExternalEvent.dedupe_key == dedupe_key,
                    )
                )
                if exists is not None:
                    duplicates += 1
                    continue
                db.add(
                    PrismExternalEvent(
                        prism_id=prism_id,
                        tenant_id=connection.tenant_id,
                        microsoft_user_id=connection.microsoft_user_id,
                        source_external_id=source.external_id,
                        source_label=source.label,
                        external_message_id=event.external_message_id,
                        event_kind=event.event_kind,
                        source_version=event.source_version,
                        dedupe_key=dedupe_key,
                        occurred_at=event.occurred_at,
                        sender_external_id=event.sender_external_id,
                        sender_display_name=event.sender_display_name,
                        body_text=event.body_text,
                        reply_to_external_id=event.reply_to_external_id,
                        event_metadata=event.metadata,
                    )
                )
                created += 1

            cursor.source_label = source.label
            cursor.last_polled_at = now
            cursor.status = "ok"
            cursor.last_error = None
            if newest is not None and (
                cursor.last_seen_at is None
                or (newest.occurred_at, newest.external_message_id)
                >= (cursor.last_seen_at, cursor.last_message_id or "")
            ):
                cursor.last_seen_at = newest.occurred_at
                cursor.last_message_id = newest.external_message_id
            policy.discovery_cursor_external_id = source.external_id

        policy.last_discovery_at = now
        policy.last_discovery_error = source_errors[0]["detail"] if source_errors else None
        db.commit()
        return cls._sync_result(
            prism_id,
            scanned=len(scan_sources),
            fetched=fetched,
            created=created,
            duplicates=duplicates,
            status="degraded" if source_errors else "ok",
            source_errors=source_errors,
            cursor=policy.discovery_cursor_external_id,
            discovered_at=now,
        )

    @staticmethod
    def events(db: Session, prism_id: uuid.UUID) -> tuple[list[PrismExternalEvent], int]:
        PrismLifecycleService.get(db, prism_id)
        limit = get_settings().v22_teams_event_limit
        statement = (
            select(PrismExternalEvent)
            .where(PrismExternalEvent.prism_id == prism_id)
            .order_by(PrismExternalEvent.occurred_at.desc(), PrismExternalEvent.id.desc())
        )
        return list(db.scalars(statement.limit(limit))), int(
            db.scalar(
                select(func.count(PrismExternalEvent.id)).where(
                    PrismExternalEvent.prism_id == prism_id
                )
            )
            or 0
        )

    @staticmethod
    def normalize_event(raw: dict[str, Any]) -> NormalizedTeamsActivityEvent | None:
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            return None
        if raw.get("messageType", "message") != "message":
            return None
        created_at = MicrosoftService._parse_graph_datetime(raw.get("createdDateTime"))
        deleted_at = MicrosoftService._parse_graph_datetime(raw.get("deletedDateTime"))
        modified_at = MicrosoftService._parse_graph_datetime(raw.get("lastModifiedDateTime"))
        occurred_at = deleted_at or modified_at or created_at
        if occurred_at is None:
            return None
        if deleted_at is not None:
            event_kind = "deleted"
        elif modified_at is not None and (created_at is None or modified_at != created_at):
            event_kind = "updated"
        else:
            event_kind = "created"
        sender: dict[str, Any] = raw.get("from") if isinstance(raw.get("from"), dict) else {}
        user_value = sender.get("user")
        application_value = sender.get("application")
        user: dict[str, Any] = user_value if isinstance(user_value, dict) else {}
        application: dict[str, Any] = (
            application_value if isinstance(application_value, dict) else {}
        )
        sender_id = user.get("id") or application.get("id")
        sender_name = user.get("displayName") or application.get("displayName") or "Unknown sender"
        attachments = raw.get("attachments")
        attachment_count = len(attachments) if isinstance(attachments, list) else 0
        reply_id, quote = MicrosoftService._reply_reference(raw)
        # Deleted Teams messages do not consistently retain a body.  We still
        # record the deletion so future phases can invalidate stale evidence.
        body_text = "" if deleted_at is not None else MicrosoftService._message_content(raw)
        version_time = deleted_at or modified_at or created_at or occurred_at
        return NormalizedTeamsActivityEvent(
            external_message_id=identifier,
            event_kind=event_kind,
            source_version=version_time.isoformat(),
            occurred_at=occurred_at,
            sender_external_id=str(sender_id) if sender_id else None,
            sender_display_name=str(sender_name)[:255],
            body_text=body_text[:12000],
            reply_to_external_id=reply_id,
            metadata={
                "created_at": created_at.isoformat() if created_at else None,
                "last_modified_at": modified_at.isoformat() if modified_at else None,
                "deleted_at": deleted_at.isoformat() if deleted_at else None,
                "importance": raw.get("importance"),
                "attachment_count": attachment_count,
                "has_unsupported_attachments": attachment_count > 0,
                "quoted_text": quote[:4000] if quote else None,
                "has_body": bool(body_text.strip()),
            },
        )

    @classmethod
    def _bounded_scan_sources(
        cls, sources: list[TeamsChatSourceRead], cursor_id: str | None
    ) -> list[TeamsChatSourceRead]:
        if not sources:
            return []
        limit = get_settings().v22_teams_poll_source_limit
        if cursor_id is None:
            return sources[:limit]
        index = next((i for i, source in enumerate(sources) if source.external_id == cursor_id), -1)
        ordered = sources[index + 1 :] + sources[: index + 1] if index >= 0 else sources
        return ordered[:limit]

    @staticmethod
    def _cursor(
        db: Session, prism_id: uuid.UUID, source_external_id: str
    ) -> PrismTeamsSourceCursor:
        cursor = db.scalar(
            select(PrismTeamsSourceCursor).where(
                PrismTeamsSourceCursor.prism_id == prism_id,
                PrismTeamsSourceCursor.source_external_id == source_external_id,
            )
        )
        if cursor is not None:
            return cursor
        cursor = PrismTeamsSourceCursor(prism_id=prism_id, source_external_id=source_external_id)
        db.add(cursor)
        return cursor

    @staticmethod
    def _dedupe_key(
        tenant_id: str,
        microsoft_user_id: str,
        source_external_id: str,
        event: NormalizedTeamsActivityEvent,
    ) -> str:
        raw = "|".join(
            (
                tenant_id,
                microsoft_user_id,
                source_external_id,
                event.external_message_id,
                event.event_kind,
                event.source_version,
                event.occurred_at.isoformat(),
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _sync_result(
        prism_id: uuid.UUID,
        *,
        scanned: int = 0,
        fetched: int = 0,
        created: int = 0,
        duplicates: int = 0,
        status: Literal["ok", "degraded"],
        source_errors: list[dict[str, str]],
        cursor: str | None,
        discovered_at: datetime,
    ) -> PrismTeamsSyncRead:
        return PrismTeamsSyncRead(
            prism_id=prism_id,
            scanned_chats=scanned,
            fetched_messages=fetched,
            created_events=created,
            duplicate_events=duplicates,
            status=status,
            source_errors=source_errors,
            next_discovery_cursor=cursor,
            last_discovery_at=discovered_at,
        )
