from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.agent_v21 import AgentJob, AgentJobSource, AgentSourceMessage, AgentThread
from app.models.employee import Employee
from app.schemas.agent_sources import AgentEvidenceRead, TeamsChatSourceRead, TeamsEvidenceSyncRead
from app.services.errors import DomainError, NotFoundError, RuleViolationError
from app.services.microsoft_service import MicrosoftGraphClient, MicrosoftService


@dataclass(frozen=True)
class NormalizedTeamsMessage:
    external_message_id: str
    sender_external_id: str | None
    sender_display_name: str
    sent_at: datetime
    body_text: str
    quoted_text: str | None
    reply_to_external_id: str | None
    metadata: dict[str, Any]


# Listing every chat is a slow Microsoft call (several seconds) that the chat picker, the scope editor and
# saving a choice all repeat. The catalog is kept briefly per manager so those clicks feel instant.
_CATALOG: dict[str, tuple[float, list[TeamsChatSourceRead]]] = {}


class TeamsReadService:
    SOURCE_KIND = "teams_chat"
    MAX_JOB_SOURCE_LIMIT = 50

    @staticmethod
    def list_sources(db: Session) -> list[TeamsChatSourceRead]:
        connection = MicrosoftService.get_connection(db)
        manager_id = connection.microsoft_user_id
        ttl = get_settings().teams_catalog_cache_seconds
        hit = _CATALOG.get(manager_id)
        if ttl and hit and hit[0] > time.monotonic():
            return list(hit[1])
        sources = TeamsReadService._fetch_sources(db, connection, manager_id)
        if ttl:
            _CATALOG[manager_id] = (time.monotonic() + ttl, sources)
        return list(sources)

    @staticmethod
    def _fetch_sources(db: Session, connection, manager_id: str) -> list[TeamsChatSourceRead]:
        sources = [
            source
            for chat in MicrosoftGraphClient(db, connection).list_chats()
            if (source := TeamsReadService._normalize_chat(chat, manager_id)) is not None
        ]
        aliases_by_user_id = {
            employee.teams_user_id: employee.aliases
            for employee in db.scalars(
                select(Employee)
                .options(selectinload(Employee.alias_records))
                .where(Employee.is_active.is_(True), Employee.teams_user_id.is_not(None))
            )
        }
        sources = [
            source.model_copy(
                update={
                    "participant_details": [
                        participant.model_copy(
                            update={
                                "aliases": aliases_by_user_id.get(
                                    participant.external_id, participant.aliases
                                )
                            }
                        )
                        for participant in source.participant_details
                    ]
                }
            )
            for source in sources
        ]
        return sorted(
            sources,
            key=lambda item: item.last_updated_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    @staticmethod
    def select_source(db: Session, thread_id: uuid.UUID, external_id: str) -> AgentThread:
        thread = db.get(AgentThread, thread_id)
        if thread is None:
            raise NotFoundError("Agent thread was not found")
        source = next(
            (item for item in TeamsReadService.list_sources(db) if item.external_id == external_id),
            None,
        )
        if source is None:
            raise RuleViolationError("Choose a Teams chat available to the connected manager")
        thread.source_kind = TeamsReadService.SOURCE_KIND
        thread.source_external_id = source.external_id
        thread.source_label = source.label
        thread.source_metadata = {
            "chat_type": source.chat_type,
            "participants": source.participants,
        }
        db.commit()
        db.refresh(thread)
        return thread

    @staticmethod
    def clear_source(db: Session, thread_id: uuid.UUID) -> AgentThread:
        thread = db.get(AgentThread, thread_id)
        if thread is None:
            raise NotFoundError("Agent thread was not found")
        thread.source_kind = None
        thread.source_external_id = None
        thread.source_label = None
        thread.source_metadata = {}
        db.commit()
        db.refresh(thread)
        return thread

    @staticmethod
    def sync_job_evidence(db: Session, job_id: uuid.UUID) -> TeamsEvidenceSyncRead:
        job = db.get(AgentJob, job_id)
        if job is None:
            raise NotFoundError("Agent job was not found")
        sources = list(
            db.scalars(
                select(AgentJobSource)
                .where(
                    AgentJobSource.job_id == job.id,
                    AgentJobSource.source_kind == TeamsReadService.SOURCE_KIND,
                    AgentJobSource.selection_reason != "destination",
                )
                .order_by(AgentJobSource.created_at, AgentJobSource.id)
            )
        )
        if not sources:
            raise RuleViolationError("This job does not have a resolved Teams source")

        # A Prism's policy can change after a job is created but before the
        # browser asks us to fetch evidence.  Re-check it here, immediately
        # before Graph reads, so queued work cannot bypass a newly added
        # exclusion.  Destination-only records are never read as evidence.
        thread = db.get(AgentThread, job.thread_id)
        if thread is not None and thread.prism_id is not None:
            from app.services.prism_teams_policy_service import PrismTeamsPolicyService

            blocked = [
                source
                for source in sources
                if source.selection_reason != "destination"
                and not PrismTeamsPolicyService.is_source_allowed(
                    db, thread.prism_id, source.external_id
                )
            ]
            if blocked:
                sources = [source for source in sources if source not in blocked]
                if not sources:
                    raise RuleViolationError(
                        "The current Teams monitoring scope no longer allows the selected chat"
                    )

        connection = MicrosoftService.get_connection(db)
        settings = get_settings()
        limit = settings.v21_teams_message_limit
        graph = MicrosoftGraphClient(db, connection)
        requested_history_days = job.requested_scope.get("limits", {}).get(
            "history_days", settings.v21_teams_history_days
        )
        history_days = min(
            max(1, int(requested_history_days)),
            settings.v21_teams_history_days,
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=history_days)
        character_limit = settings.v21_teams_evidence_character_limit
        per_source_character_limit = max(1000, character_limit // max(1, len(sources)))
        requested_source_limit = job.requested_scope.get("limits", {}).get(
            "sources", settings.v21_teams_source_limit
        )
        source_limit = min(
            max(1, int(requested_source_limit)),
            TeamsReadService.MAX_JOB_SOURCE_LIMIT,
        )
        used_characters = 0
        skipped = 0
        stored = 0
        fetched = 0
        source_errors: list[dict[str, str]] = []
        empty_sources: list[str] = []
        successful_sources = 0
        bounds_skipped = 0
        message_limit_reached = False
        for source in sources[:source_limit]:
            try:
                remote_messages = graph.list_chat_messages(source.external_id, limit=limit)
            except DomainError as exc:
                source_errors.append(
                    {
                        "source_external_id": source.external_id,
                        "source_label": source.label or "Teams chat",
                        "detail": exc.detail,
                    }
                )
                source.source_metadata = {
                    **source.source_metadata,
                    "retrieval_error": exc.detail,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
                continue
            successful_sources += 1
            fetched += len(remote_messages)
            message_limit_reached = message_limit_reached or len(remote_messages) >= limit
            accepted_for_source: list[NormalizedTeamsMessage] = []
            used_for_source = 0
            for remote in remote_messages:
                normalized = TeamsReadService.normalize_message(remote)
                if normalized is None:
                    skipped += 1
                    continue
                if normalized.sent_at < cutoff:
                    skipped += 1
                    bounds_skipped += 1
                    continue
                evidence_size = len(normalized.body_text) + len(normalized.quoted_text or "")
                if (
                    used_characters + evidence_size > character_limit
                    or used_for_source + evidence_size > per_source_character_limit
                ):
                    skipped += 1
                    bounds_skipped += 1
                    continue
                used_characters += evidence_size
                used_for_source += evidence_size
                accepted_for_source.append(normalized)
                existing = db.scalar(
                    select(AgentSourceMessage).where(
                        AgentSourceMessage.job_id == job.id,
                        AgentSourceMessage.external_conversation_id == source.external_id,
                        AgentSourceMessage.external_message_id == normalized.external_message_id,
                    )
                )
                if existing is None:
                    existing = AgentSourceMessage(
                        job_id=job.id,
                        external_conversation_id=source.external_id,
                        external_message_id=normalized.external_message_id,
                        sender_external_id=normalized.sender_external_id,
                        sender_display_name=normalized.sender_display_name,
                        sent_at=normalized.sent_at,
                        body_text=normalized.body_text,
                        quoted_text=normalized.quoted_text,
                        reply_to_external_id=normalized.reply_to_external_id,
                        message_metadata=normalized.metadata,
                    )
                    db.add(existing)
                    stored += 1
                else:
                    existing.sender_external_id = normalized.sender_external_id
                    existing.sender_display_name = normalized.sender_display_name
                    existing.sent_at = normalized.sent_at
                    existing.body_text = normalized.body_text
                    existing.quoted_text = normalized.quoted_text
                    existing.reply_to_external_id = normalized.reply_to_external_id
                    existing.message_metadata = normalized.metadata
            if not accepted_for_source:
                empty_sources.append(source.label or source.external_id)
            timestamps = [item.sent_at for item in accepted_for_source]
            source.source_metadata = {
                **source.source_metadata,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "retrieved_message_count": len(accepted_for_source),
                "oldest_message_at": min(timestamps).isoformat() if timestamps else None,
                "newest_message_at": max(timestamps).isoformat() if timestamps else None,
                "retrieval_error": None,
            }
        if successful_sources == 0 and source_errors:
            db.rollback()
            raise RuleViolationError("Prism could not read any of the resolved Teams sources")
        job.requested_scope = {
            **job.requested_scope,
            "retrieval_errors": source_errors,
            "empty_sources": empty_sources,
            "retrieved_source_count": successful_sources,
            "evidence_truncated": bounds_skipped > 0,
            "message_limit_reached": message_limit_reached,
        }
        db.commit()
        evidence = TeamsReadService.evidence(db, job.id)
        return TeamsEvidenceSyncRead(
            job_id=job.id,
            source_label=(sources[0].label or "Selected Teams chat"),
            source_labels=[item.label or "Teams chat" for item in sources],
            fetched=fetched,
            stored=stored,
            skipped=skipped,
            source_errors=source_errors,
            evidence=evidence,
        )

    @staticmethod
    def evidence(db: Session, job_id: uuid.UUID) -> list[AgentEvidenceRead]:
        job = db.get(AgentJob, job_id)
        if job is None:
            raise NotFoundError("Agent job was not found")
        sources = {
            item.external_id: item.label or "Teams chat"
            for item in db.scalars(select(AgentJobSource).where(AgentJobSource.job_id == job.id))
        }
        messages = db.scalars(
            select(AgentSourceMessage)
            .where(AgentSourceMessage.job_id == job.id)
            .order_by(
                AgentSourceMessage.external_conversation_id,
                AgentSourceMessage.sent_at,
                AgentSourceMessage.id,
            )
        )
        return [
            AgentEvidenceRead(
                id=item.id,
                source_message_id=item.external_message_id,
                source_external_id=item.external_conversation_id,
                source_label=sources.get(item.external_conversation_id, "Teams chat"),
                sender_display_name=item.sender_display_name,
                sent_at=item.sent_at,
                excerpt=TeamsReadService._excerpt(item.body_text),
                quoted_excerpt=TeamsReadService._excerpt(item.quoted_text)
                if item.quoted_text
                else None,
                reply_to_source_id=item.reply_to_external_id,
            )
            for item in messages
        ]

    @staticmethod
    def normalize_message(remote: dict[str, Any]) -> NormalizedTeamsMessage | None:
        identifier = remote.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            return None
        if remote.get("deletedDateTime") or remote.get("messageType", "message") != "message":
            return None
        sent_at = MicrosoftService._parse_graph_datetime(remote.get("createdDateTime"))
        if sent_at is None:
            return None
        body = MicrosoftService._message_content(remote)
        if not body:
            return None
        reply_id, quote = MicrosoftService._reply_reference(remote)
        sender = remote.get("from") if isinstance(remote.get("from"), dict) else {}
        user = sender.get("user") if isinstance(sender.get("user"), dict) else {}
        application = (
            sender.get("application") if isinstance(sender.get("application"), dict) else {}
        )
        sender_id = user.get("id") or application.get("id")
        sender_name = user.get("displayName") or application.get("displayName") or "Unknown sender"
        attachments = remote.get("attachments")
        attachment_count = len(attachments) if isinstance(attachments, list) else 0
        return NormalizedTeamsMessage(
            external_message_id=identifier,
            sender_external_id=str(sender_id) if sender_id else None,
            sender_display_name=str(sender_name)[:255],
            sent_at=sent_at,
            body_text=body[:12000],
            quoted_text=quote[:4000] if quote else None,
            reply_to_external_id=reply_id,
            metadata={
                "last_modified_at": remote.get("lastModifiedDateTime"),
                "importance": remote.get("importance"),
                "attachment_count": attachment_count,
                "has_unsupported_attachments": attachment_count > 0,
            },
        )

    @staticmethod
    def _normalize_chat(chat: dict[str, Any], manager_id: str) -> TeamsChatSourceRead | None:
        external_id = chat.get("id")
        chat_type = chat.get("chatType")
        if not isinstance(external_id, str) or chat_type not in {"oneOnOne", "group"}:
            return None
        members = chat.get("members") if isinstance(chat.get("members"), list) else []
        participants: list[str] = []
        participant_details: list[dict[str, Any]] = []
        for member in members:
            if not isinstance(member, dict):
                continue
            member_id = member.get("userId") or member.get("id")
            name = member.get("displayName")
            if member_id == manager_id or not isinstance(name, str) or not name.strip():
                continue
            participants.append(name.strip())
            participant_details.append(
                {
                    "external_id": str(member_id) if member_id else None,
                    "display_name": name.strip(),
                    "aliases": [],
                }
            )
        topic = chat.get("topic")
        if isinstance(topic, str) and topic.strip():
            label = topic.strip()
        elif participants:
            label = ", ".join(participants[:4])
            if len(participants) > 4:
                label += f" +{len(participants) - 4}"
        else:
            label = "Private Teams chat" if chat_type == "oneOnOne" else "Teams group chat"
        last_message = (
            chat.get("lastMessagePreview")
            if isinstance(chat.get("lastMessagePreview"), dict)
            else {}
        )
        return TeamsChatSourceRead(
            external_id=external_id,
            label=label[:255],
            chat_type="private" if chat_type == "oneOnOne" else "group",
            participants=participants,
            participant_details=participant_details,
            last_updated_at=MicrosoftService._parse_graph_datetime(
                last_message.get("createdDateTime")
            )
            or MicrosoftService._parse_graph_datetime(chat.get("lastUpdatedDateTime")),
        )

    @staticmethod
    def _excerpt(value: str, limit: int = 600) -> str:
        clean = re.sub(r"\s+", " ", value).strip()
        return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"
