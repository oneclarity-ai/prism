"""Small, auditable first management loop for inbound Teams updates."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.automation_action import AutomationAction
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.enums import (
    AgentAnalysisType,
    AgentRunStatus,
    ActivityEventType,
    AutomationActionStatus,
    AutomationActionType,
    BlockerSeverity,
    BlockerStatus,
    CommitmentStatus,
    MessageDirection,
)
from app.models.message import Message
from app.schemas.blocker import BlockerCreate, BlockerUpdate
from app.schemas.commitment import CommitmentCreate, CommitmentRevisionCreate
from app.services.blocker_service import BlockerService
from app.services.commitment_service import CommitmentService
from app.services.errors import ExternalServiceError, RuleViolationError
from app.services.microsoft_service import MicrosoftService
from app.services.memory_service import MemoryService
from app.services.management_context_service import ManagementContextService


class ReplyAnalysis(BaseModel):
    """The limited structured facts the model is allowed to return."""

    model_config = ConfigDict(extra="forbid")

    classification: Literal["blocker", "update", "unclear"]
    completed_summary: Optional[str]
    today_summary: Optional[str]
    expected_outcome: Optional[str]
    blocker_description: Optional[str]
    dependency_owner_name: Optional[str]
    eta_deadline: Optional[datetime]
    missed_reason: Optional[str]
    delivery_confirmed: bool



class ManagementAgent:
    @staticmethod
    def process_message(db: Session, message_id: str, *, retry_skipped: bool = False,
                        retry_completed: bool = False) -> Optional[AgentRun]:
        from app.services.response_service import ResponseService
        return ResponseService.process(db, message_id, retry_skipped=retry_skipped,
                                       retry_completed=retry_completed)

    @staticmethod
    def _is_non_actionable_acknowledgement(content: str) -> bool:
        normalized = re.sub(r"[^a-z\s]", " ", content.casefold())
        words = [word for word in normalized.split() if word not in {"hi", "hello", "hey", "sir", "maam", "mam", "ji"}]
        # These carry no delivery, ETA, owner, work, or blocker information.
        # Do not send them to the model or let them move a management workflow.
        if not words:
            return bool(normalized.split())
        return all(word in {
            "ok", "okay", "sure", "yes", "yeah", "yep", "thanks", "thank", "you",
            "got", "it", "noted", "done", "fine",
        } for word in words)

    @staticmethod
    def _is_noncommittal_dependency_response(content: str) -> bool:
        """Recognise a reply that promises a future answer but supplies no owner/ETA."""

        normalized = " ".join(re.findall(r"[a-z0-9]+", content.casefold()))
        if not normalized:
            return False
        noncommittal_phrases = (
            "let you know",
            "will let you know",
            "will discuss",
            "discuss with",
            "check with the team",
            "check with team",
            "will check",
        )
        has_specific_eta = bool(re.search(r"\b(?:by|at|before|tomorrow|today|am|pm)\b|\d", normalized))
        return any(phrase in normalized for phrase in noncommittal_phrases) and not has_specific_eta

    @staticmethod
    def _is_explicit_owner_handoff(content: str, owner: Employee) -> bool:
        """Do not let a new work update overwrite an older unresolved blocker."""

        normalized = " ".join(ManagementAgent._name_parts_without_honorifics(content))
        owner_parts = ManagementAgent._name_parts_without_honorifics(owner.name)
        if not owner_parts:
            return False
        owner_name = " ".join(owner_parts)
        owner_only = normalized == owner_name or normalized == owner_parts[0]
        if owner_only:
            return True
        # A named person alone is accepted only for the direct answer to an
        # owner question. Otherwise require clear ownership / delegation
        # language. "I'll talk to Raunak" is not enough to make Raunak the
        # dependency owner.
        handoff_pattern = r"\b(?:owner|owns|owned|follow(?:\s+this)?(?:\s+up)?|contact)\b"
        return bool(re.search(handoff_pattern, normalized))

    @staticmethod
    def _upsert_daily_update(
        db: Session, employee: Employee, raw_message: str, analysis: ReplyAnalysis
    ) -> None:
        """Keep one current daily record while the immutable message audit keeps history."""

        if not employee.is_managed or not (analysis.today_summary or analysis.completed_summary):
            return
        try:
            update_date = datetime.now(ZoneInfo(get_settings().manager_timezone)).date()
        except Exception:
            update_date = date.today()
        daily_update = db.scalar(
            select(DailyUpdate).where(
                DailyUpdate.employee_id == employee.id, DailyUpdate.update_date == update_date
            )
        )
        created = daily_update is None
        if daily_update is None:
            daily_update = DailyUpdate(employee_id=employee.id, update_date=update_date)
            db.add(daily_update)
        previous = {
            "update_date": daily_update.update_date,
            "completed_summary": daily_update.completed_summary,
            "today_summary": daily_update.today_summary,
            "expected_outcome": daily_update.expected_outcome,
            "blocker_summary": daily_update.blocker_summary,
            "raw_message": daily_update.raw_message,
        }
        if analysis.completed_summary:
            daily_update.completed_summary = analysis.completed_summary
        if analysis.today_summary:
            daily_update.today_summary = analysis.today_summary
        if analysis.expected_outcome:
            daily_update.expected_outcome = analysis.expected_outcome
        if analysis.blocker_description:
            daily_update.blocker_summary = analysis.blocker_description
        daily_update.raw_message = raw_message
        db.flush()
        current = {
            "update_date": daily_update.update_date,
            "completed_summary": daily_update.completed_summary,
            "today_summary": daily_update.today_summary,
            "expected_outcome": daily_update.expected_outcome,
            "blocker_summary": daily_update.blocker_summary,
            "raw_message": daily_update.raw_message,
        }
        if created:
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.DAILY_UPDATE_CREATED,
                entity_type="daily_update",
                entity_id=daily_update.id,
                previous=None,
                current=current,
                subject_employee_id=employee.id,
            )
        elif current != previous:
            MemoryService.record_transition(
                db,
                event_type=ActivityEventType.DAILY_UPDATE_CHANGED,
                entity_type="daily_update",
                entity_id=daily_update.id,
                previous=previous,
                current=current,
                subject_employee_id=employee.id,
            )
        db.commit()

    @staticmethod
    def _organisational_context(db: Session, employee: Employee) -> Optional[str]:
        """Combine existing operational evidence with a small manager-curated context slice."""

        context: list[str] = []
        if get_settings().memory_engine_enabled:
            memory_context = MemoryService.compile_context(db, employee.id).as_prompt()
            if memory_context:
                context.append(memory_context)
        manager_context = ManagementContextService.agent_prompt_context(db, employee.name)
        if manager_context:
            context.append(manager_context)
        return "\n\n".join(context) or None

    @staticmethod
    def _single_missed_commitment(db: Session, employee: Employee) -> Optional[Commitment]:
        commitments = list(
            db.scalars(
                select(Commitment)
                .where(Commitment.employee_id == employee.id, Commitment.status == CommitmentStatus.MISSED)
                .order_by(Commitment.missed_at.desc())
                .limit(2)
            )
        )
        return commitments[0] if len(commitments) == 1 else None

    @staticmethod
    def _record_revised_commitment(
        db: Session,
        run: AgentRun,
        owner: Employee,
        original: Commitment,
        deadline: datetime,
        reason: str,
    ) -> AgentRun:
        if deadline.tzinfo is None or deadline.utcoffset() is None or deadline <= original.deadline:
            run.status = AgentRunStatus.SKIPPED
            run.needs_yash_review = True
            run.failure_reason = "Revised ETA must be a later timezone-aware deadline"
            run.processed_at = datetime.now(timezone.utc)
            db.commit()
            return run
        revised = CommitmentService.revise(
            db,
            original.id,
            CommitmentRevisionCreate(
                description=original.description,
                deadline=deadline,
                missed_reason=reason,
            ),
        )
        run.commitment_id = revised.id
        acknowledgement = MicrosoftService.send_management_message(
            db,
            owner,
            MicrosoftService.follow_up_message_for(
                owner.name,
                "Thanks — I’ve recorded the revised ETA as {}.".format(
                    ManagementAgent._format_deadline(deadline)
                ),
            ),
        )
        run.dependency_message_id = acknowledgement.id
        if revised.blocker_id is not None:
            blocker = db.get(Blocker, revised.blocker_id)
            blocked_employee = db.get(Employee, blocker.blocked_employee_id) if blocker else None
            if blocked_employee is not None:
                update = MicrosoftService.send_management_message(
                    db,
                    blocked_employee,
                    MicrosoftService.follow_up_message_for(
                        blocked_employee.name,
                        "{} provided a revised ETA: {}. I’ll keep track of it.".format(
                            MicrosoftService.first_name(owner.name), ManagementAgent._format_deadline(deadline)
                        ),
                    ),
                )
                run.source_reply_message_id = update.id
        run.status = AgentRunStatus.COMPLETED
        run.processed_at = datetime.now(timezone.utc)
        db.commit()
        return run

    @staticmethod
    def _resolve_dependency_blocker(
        db: Session, run: AgentRun, owner: Employee, blocker: Blocker
    ) -> AgentRun:
        BlockerService.update(db, blocker.id, BlockerUpdate(status=BlockerStatus.RESOLVED))
        blocked_employee = db.get(Employee, blocker.blocked_employee_id)
        if blocked_employee is not None:
            sent = MicrosoftService.send_management_message(
                db,
                blocked_employee,
                MicrosoftService.follow_up_message_for(
                    blocked_employee.name,
                    "{} confirmed the dependency is delivered. Your blocker is resolved; please resume when ready."
                    .format(MicrosoftService.first_name(owner.name)),
                ),
            )
            run.source_reply_message_id = sent.id
        run.blocker_id = blocker.id
        run.status = AgentRunStatus.COMPLETED
        run.processed_at = datetime.now(timezone.utc)
        db.commit()
        return run

    @staticmethod
    def _format_deadline(deadline: datetime) -> str:
        try:
            return deadline.astimezone(ZoneInfo(get_settings().manager_timezone)).strftime("%d %b, %-I:%M %p %Z")
        except Exception:
            return deadline.isoformat()

    @staticmethod
    def _single_open_dependency_blocker(db: Session, employee: Employee) -> Optional[Blocker]:
        blockers = list(
            db.scalars(
                select(Blocker)
                .where(
                    Blocker.dependency_owner_id == employee.id,
                    Blocker.status == BlockerStatus.OPEN,
                )
                .order_by(Blocker.created_at.desc())
                .limit(2)
            )
        )
        return blockers[0] if len(blockers) == 1 else None

    @staticmethod
    def _dependency_blocker_for_reply(
        db: Session, message: Message, employee: Employee
    ) -> Optional[Blocker]:
        """Use only the outstanding request in this Teams conversation.

        An employee can own more than one dependency.  Looking across all of
        them lets a vague reply be accidentally applied to the wrong blocker.
        If two requests are outstanding in one chat, we deliberately return no
        implicit context and wait for an explicit reference or ETA.
        """

        requests = list(
            db.scalars(
                select(AgentRun)
                .join(Blocker, AgentRun.blocker_id == Blocker.id)
                .join(Message, AgentRun.dependency_message_id == Message.id)
                .where(
                    AgentRun.dependency_owner_id == employee.id,
                    AgentRun.dependency_message_id.is_not(None),
                    Blocker.dependency_owner_id == employee.id,
                    Blocker.status == BlockerStatus.OPEN,
                    Message.conversation_id == message.conversation_id,
                    Message.created_at <= message.created_at,
                )
                .order_by(Message.created_at.desc())
                .limit(2)
            )
        )
        if len(requests) != 1 or requests[0].blocker_id is None:
            return None
        return db.get(Blocker, requests[0].blocker_id)

    @staticmethod
    def _single_open_unassigned_blocker(db: Session, employee: Employee) -> Optional[Blocker]:
        blockers = list(
            db.scalars(
                select(Blocker)
                .where(
                    Blocker.blocked_employee_id == employee.id,
                    Blocker.dependency_owner_id.is_(None),
                    Blocker.status == BlockerStatus.OPEN,
                )
                .order_by(Blocker.created_at.desc())
                .limit(2)
            )
        )
        return blockers[0] if len(blockers) == 1 else None

    @staticmethod
    def _single_pending_owner_run(db: Session, employee: Employee) -> Optional[AgentRun]:
        """Find one historical blocker where the agent had to ask who owns it."""

        runs = list(
            db.scalars(
                select(AgentRun)
                .where(
                    AgentRun.source_employee_id == employee.id,
                    AgentRun.status == AgentRunStatus.COMPLETED,
                    AgentRun.blocker_description.is_not(None),
                    AgentRun.blocker_id.is_(None),
                    AgentRun.source_reply_message_id.is_not(None),
                )
                .order_by(AgentRun.processed_at.desc())
                .limit(2)
            )
        )
        return runs[0] if len(runs) == 1 else None

    @staticmethod
    def _latest_pending_owner_context(
        db: Session, employee: Employee
    ) -> Optional[tuple[Blocker, AgentRun]]:
        """Return the latest open blocker for which this person was asked to name an owner.

        A Teams reply such as just ``Vaibhav`` is an answer to that pending question,
        not a new daily update.  Selecting the latest explicit owner request keeps the
        conversation thread intact even if an older, similar blocker remains in history.
        """

        prior_run = db.scalar(
            select(AgentRun)
            .join(Blocker, AgentRun.blocker_id == Blocker.id)
            .where(
                AgentRun.source_employee_id == employee.id,
                AgentRun.status == AgentRunStatus.COMPLETED,
                AgentRun.source_reply_message_id.is_not(None),
                Blocker.status == BlockerStatus.OPEN,
                Blocker.dependency_owner_id.is_(None),
            )
            .order_by(AgentRun.processed_at.desc(), AgentRun.created_at.desc())
            .limit(1)
        )
        if prior_run is None or prior_run.blocker_id is None:
            return None
        blocker = db.get(Blocker, prior_run.blocker_id)
        return (blocker, prior_run) if blocker is not None else None

    @staticmethod
    def _owner_question_already_sent(db: Session, employee: Employee, blocker: Blocker) -> bool:
        return db.scalar(
            select(AutomationAction.id)
            .where(
                AutomationAction.action_type == AutomationActionType.BLOCKER_OWNER_CLARIFICATION,
                AutomationAction.employee_id == employee.id,
                AutomationAction.blocker_id == blocker.id,
                AutomationAction.status.in_(
                    [AutomationActionStatus.PENDING, AutomationActionStatus.DELIVERED]
                ),
            )
            .limit(1)
        ) is not None

    @staticmethod
    def _send_blocker_message_once(
        db: Session,
        *,
        action_type: AutomationActionType,
        idempotency_key: str,
        employee: Employee,
        blocker: Optional[Blocker],
        content: str,
    ) -> Optional[Message]:
        """Reserve one management message before calling Microsoft Graph.

        Teams can redeliver a webhook and two worker requests can overlap.  The
        unique key is committed *before* Graph is called, so only one worker
        can send a particular acknowledgement, owner request, or clarification.
        A genuinely failed Graph call is recorded as failed and can be retried
        by reprocessing the failed inbound message.
        """

        action = db.scalar(
            select(AutomationAction).where(
                AutomationAction.idempotency_key == idempotency_key
            )
        )
        if action is not None and action.status in {
            AutomationActionStatus.PENDING,
            AutomationActionStatus.DELIVERED,
            AutomationActionStatus.SKIPPED,
        }:
            return None
        if action is None:
            action = AutomationAction(
                action_type=action_type,
                status=AutomationActionStatus.PENDING,
                idempotency_key=idempotency_key,
                employee_id=employee.id,
                blocker_id=blocker.id if blocker else None,
                detail="Reserved by the management-agent duplicate guard",
                executed_at=datetime.now(timezone.utc),
            )
            db.add(action)
            try:
                db.commit()
            except IntegrityError:
                # A concurrent worker reserved the same action.  It owns the
                # send; this worker must not create a second Teams message.
                db.rollback()
                return None
        else:
            action.status = AutomationActionStatus.PENDING
            action.detail = "Retrying a previously failed management-agent send"
            action.executed_at = datetime.now(timezone.utc)
            db.commit()
        try:
            sent = MicrosoftService.send_management_message(db, employee, content)
        except (ExternalServiceError, RuleViolationError) as exc:
            action = db.get(AutomationAction, action.id)
            if action is not None:
                action.status = AutomationActionStatus.FAILED
                action.detail = exc.detail
                action.executed_at = datetime.now(timezone.utc)
                db.commit()
            raise
        action = db.get(AutomationAction, action.id)
        if action is not None:
            action.status = AutomationActionStatus.DELIVERED
            action.message_id = sent.id
            action.detail = None
            action.executed_at = datetime.now(timezone.utc)
            db.commit()
        return sent

    @staticmethod
    def _assign_dependency_owner_and_notify(
        db: Session,
        run: AgentRun,
        employee: Employee,
        owner: Employee,
        description: str,
        *,
        blocker: Optional[Blocker] = None,
        prior_run: Optional[AgentRun] = None,
    ) -> AgentRun:
        """Attach an owner to a blocker, then notify the employee and owner."""

        if owner.id == employee.id:
            # A person cannot be made the dependency owner for their own
            # blocker through an automated inference.  Preserve the run for
            # audit and ask Yash to resolve the ambiguity instead of creating
            # a self-message loop.
            run.status = AgentRunStatus.SKIPPED
            run.needs_yash_review = True
            run.failure_reason = "A blocker cannot depend on its own blocked employee"
            run.processed_at = datetime.now(timezone.utc)
            db.commit()
            return run
        if blocker is None:
            blocker = ManagementAgent._get_or_create_blocker(db, employee, owner, description)
        elif blocker.dependency_owner_id != owner.id:
            blocker = BlockerService.update(
                db, blocker.id, BlockerUpdate(dependency_owner_id=owner.id)
            )
        run.analysis_type = AgentAnalysisType.BLOCKER
        run.dependency_owner_id = owner.id
        run.blocker_id = blocker.id
        if prior_run is not None:
            prior_run.dependency_owner_id = owner.id
            prior_run.blocker_id = blocker.id
        sent_source_reply = ManagementAgent._send_blocker_message_once(
            db,
            action_type=AutomationActionType.BLOCKER_SOURCE_ACKNOWLEDGEMENT,
            idempotency_key="blocker-source-acknowledgement:{}:{}".format(
                blocker.id, employee.id
            ),
            employee=employee,
            blocker=blocker,
            content=MicrosoftService.follow_up_message_for(
                employee.name,
                "Thanks — I’ve noted that {} owns this. I’ll check with them and get back to you."
                .format(MicrosoftService.first_name(owner.name)),
            ),
        )
        if sent_source_reply is not None:
            run.source_reply_message_id = sent_source_reply.id
        sent_dependency_message = None
        if not ManagementAgent._similar_open_owner_request_exists(db, owner, blocker):
            sent_dependency_message = ManagementAgent._send_blocker_message_once(
                db,
                action_type=AutomationActionType.BLOCKER_OWNER_REQUEST,
                idempotency_key="blocker-owner-request:{}:{}".format(blocker.id, owner.id),
                employee=owner,
                blocker=blocker,
                content=MicrosoftService.follow_up_message_for(
                    owner.name,
                    ManagementAgent._natural_dependency_eta_request(employee, blocker.description),
                ),
            )
        if sent_dependency_message is not None:
            run.dependency_message_id = sent_dependency_message.id
        run.status = AgentRunStatus.COMPLETED
        run.processed_at = datetime.now(timezone.utc)
        db.commit()
        return run

    @staticmethod
    def _similar_open_owner_request_exists(
        db: Session, owner: Employee, blocker: Blocker
    ) -> bool:
        """Avoid spamming one owner about the same active dependency.

        Different blockers remain separate records for audit.  This guard only
        suppresses a second owner ping when its meaningful dependency tokens
        match an already-open blocker that has a delivered/pending request.
        Once the earlier blocker is resolved, a future occurrence can notify
        the owner normally.
        """

        signature = ManagementAgent._dependency_signature(db, blocker.description)
        if not signature:
            return False
        actions = list(
            db.scalars(
                select(AutomationAction)
                .join(Blocker, AutomationAction.blocker_id == Blocker.id)
                .where(
                    AutomationAction.action_type == AutomationActionType.BLOCKER_OWNER_REQUEST,
                    AutomationAction.employee_id == owner.id,
                    AutomationAction.blocker_id != blocker.id,
                    AutomationAction.status.in_(
                        [AutomationActionStatus.PENDING, AutomationActionStatus.DELIVERED]
                    ),
                    Blocker.status == BlockerStatus.OPEN,
                )
                .order_by(AutomationAction.executed_at.desc())
                .limit(20)
            )
        )
        for action in actions:
            related = db.get(Blocker, action.blocker_id)
            if related is not None and ManagementAgent._dependency_signature(
                db, related.description
            ) == signature:
                return True
        return False

    @staticmethod
    def _dependency_signature(db: Session, description: str) -> tuple[str, ...]:
        """A cautious normalisation used only for short-term owner-ping de-dupe."""

        text = description.casefold().replace("updation", "updates")
        text = re.sub(r"\b(?:sir|maam|mam|mr|mrs|ms|dr|ji)\b", "", text)
        for person in db.scalars(select(Employee).where(Employee.is_active.is_(True))):
            name_parts = ManagementAgent._name_parts_without_honorifics(person.name)
            if name_parts:
                text = re.sub(
                    r"\b{}\b".format(re.escape(" ".join(name_parts))), " ", text
                )
                text = re.sub(r"\b{}\b".format(re.escape(name_parts[0])), " ", text)
        ignored = {
            "a", "an", "the", "and", "are", "awaiting", "before", "by", "can", "changes",
            "continue", "continuing", "dependency", "for", "from", "has", "i", "in", "input",
            "inputs", "is", "it", "need", "needs", "of", "on", "please", "proceed", "required",
            "to", "update", "updates", "waiting", "with", "work",
        }
        tokens = {token for token in re.findall(r"[a-z0-9]+", text) if token not in ignored}
        return tuple(sorted(tokens))

    @staticmethod
    def _record_eta_and_update_blocked_employee(
        db: Session,
        run: AgentRun,
        owner: Employee,
        blocker: Blocker,
        deadline: datetime,
    ) -> AgentRun:
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            run.status = AgentRunStatus.SKIPPED
            run.processed_at = datetime.now(timezone.utc)
            db.commit()
            return run
        now = datetime.now(timezone.utc)
        if deadline <= now:
            run.status = AgentRunStatus.SKIPPED
            run.needs_yash_review = True
            run.failure_reason = "The stated ETA is already in the past"
            run.processed_at = now
            db.commit()
            return run
        commitment = db.scalar(
            select(Commitment)
            .where(
                Commitment.blocker_id == blocker.id,
                Commitment.employee_id == owner.id,
                Commitment.status == CommitmentStatus.OPEN,
            )
            .order_by(Commitment.created_at.desc())
            .limit(1)
        )
        if commitment is None:
            commitment = CommitmentService.create(
                db,
                CommitmentCreate(
                    employee_id=owner.id,
                    blocker_id=blocker.id,
                    description="Provide: {}".format(blocker.description),
                    deadline=deadline,
                ),
            )
        run.commitment_id = commitment.id
        try:
            local_deadline = deadline.astimezone(ZoneInfo(get_settings().manager_timezone))
            acknowledgement_deadline = local_deadline.strftime("%-I:%M %p %Z")
        except Exception:
            acknowledgement_deadline = deadline.isoformat()
        sent_acknowledgement = MicrosoftService.send_management_message(
            db,
            owner,
            MicrosoftService.follow_up_message_for(
                owner.name,
                "Thanks — I’ve recorded {} as the ETA. I’ll keep track of it.".format(
                    acknowledgement_deadline
                ),
            ),
        )
        run.dependency_message_id = sent_acknowledgement.id
        blocked_employee = db.get(Employee, blocker.blocked_employee_id)
        if blocked_employee is None:
            raise RuleViolationError("The employee affected by this blocker no longer exists")
        timezone_name = get_settings().manager_timezone
        try:
            local_deadline = deadline.astimezone(ZoneInfo(timezone_name))
            formatted_deadline = local_deadline.strftime("%d %b, %-I:%M %p %Z")
        except Exception:
            formatted_deadline = deadline.isoformat()
        sent_update = MicrosoftService.send_management_message(
            db,
            blocked_employee,
            MicrosoftService.follow_up_message_for(
                blocked_employee.name,
                "{} expects to provide this by {}. I’ll keep track of it.".format(
                    MicrosoftService.first_name(owner.name), formatted_deadline
                ),
            ),
        )
        run.source_reply_message_id = sent_update.id
        run.status = AgentRunStatus.COMPLETED
        run.processed_at = datetime.now(timezone.utc)
        db.commit()
        return run

    @staticmethod
    def _exact_dependency_owner(db: Session, supplied_name: Optional[str]) -> Optional[Employee]:
        if not supplied_name or not supplied_name.strip():
            return None
        candidate = supplied_name.strip().casefold()
        active_employees = list(db.scalars(select(Employee).where(Employee.is_active.is_(True))))
        matches = [
            employee
            for employee in active_employees
            if employee.name.strip().casefold() == candidate or employee.email.strip().casefold() == candidate
        ]
        if len(matches) == 1 and matches[0].teams_user_id:
            return matches[0]
        # Azure may return a unique first name such as "Shubham" when the
        # directory display name is "Shubham Fating". Resolve only when it is
        # unambiguous among active Teams-reachable employees.
        name_parts = ManagementAgent._name_parts_without_honorifics(candidate)
        if len(name_parts) == 1:
            first_name_matches = [
                employee
                for employee in active_employees
                if employee.teams_user_id
                and re.findall(r"[a-z0-9]+", employee.name.casefold())[:1] == name_parts
            ]
            if len(first_name_matches) == 1:
                return first_name_matches[0]
        return None

    @staticmethod
    def _referenced_active_employee(
        db: Session, content: str, *, exclude_employee_id: object
    ) -> Optional[Employee]:
        """Resolve an explicit person named in a short reply without relying on the LLM."""

        message_parts = ManagementAgent._name_parts_without_honorifics(content)
        if not message_parts:
            return None
        message_text = " ".join(message_parts)
        matches: list[Employee] = []
        for employee in db.scalars(
            select(Employee).where(
                Employee.is_active.is_(True),
                Employee.teams_user_id.is_not(None),
                Employee.id != exclude_employee_id,
            )
        ):
            employee_parts = ManagementAgent._name_parts_without_honorifics(employee.name)
            if not employee_parts:
                continue
            full_name = " ".join(employee_parts)
            full_pattern = r"(?<![a-z0-9]){}(?![a-z0-9])".format(re.escape(full_name))
            first_pattern = r"(?<![a-z0-9]){}(?![a-z0-9])".format(re.escape(employee_parts[0]))
            if re.search(full_pattern, message_text) or re.search(first_pattern, message_text):
                matches.append(employee)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _name_parts_without_honorifics(value: str) -> list[str]:
        honorifics = {"sir", "maam", "mam", "mr", "mrs", "ms", "dr", "ji"}
        return [part for part in re.findall(r"[a-z0-9]+", value.casefold()) if part not in honorifics]

    @staticmethod
    def _natural_dependency_eta_request(employee: Employee, description: str) -> str:
        """Turn stored blocker facts into a short, human-sounding ETA request."""

        employee_name = MicrosoftService.first_name(employee.name)
        cleaned = " ".join(description.strip().split()).rstrip(". ")
        # Never reproduce honourifics or full-name boilerplate from a raw Teams
        # message.  The recipient already knows they are being asked.
        cleaned = re.sub(r"\b(?:sir|maam|mam|mr|mrs|ms|dr|ji)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;.")
        cleaned = re.sub(
            r"\b([A-Z][a-z]+)\s+[A-Z][a-z]+(?:['’]s)?\b",
            lambda match: match.group(1) + ("'s" if match.group(0).endswith(("'s", "’s")) else ""),
            cleaned,
        )
        match = re.match(
            r"^awaiting changes/inputs to the (?P<dependency>.+?) from .+? to continue "
            r"(?P<work>.+)$",
            cleaned,
            flags=re.IGNORECASE,
        )
        if match:
            dependency = match.group("dependency").strip()
            work = match.group("work").strip().replace("updation", "updates")
            suffix = " changes" if "change" not in dependency.casefold() else ""
            return (
                "{} is waiting on the {}{} before continuing with the {}. "
                "Any idea when this might be ready?"
            ).format(employee_name, dependency, suffix, work)
        structured = re.match(
            r"^(?P<subject>[A-Za-z]+)\s+needs\s+(?:need\s+)?(?:awaiting\s+)?"
            r"(?P<dependency>.+?)(?:\s+from\s+.+?)?"
            r"(?:\s+to\s+(?:unblock\s+progress\s+on|proceed\s+with|continue\s+with)\s+"
            r"(?P<work>.+?))?(?:\s*;.*)?$",
            cleaned,
            flags=re.IGNORECASE,
        )
        if structured:
            dependency = structured.group("dependency").strip(" ,;.")
            dependency = re.sub(r"\bchanges/inputs\b", "changes", dependency, flags=re.IGNORECASE)
            dependency = re.sub(r"\binputs?\s+from\b.*$", "input", dependency, flags=re.IGNORECASE)
            dependency = re.sub(r"\bto\s+continue$", "", dependency, flags=re.IGNORECASE).strip()
            work = structured.group("work")
            if work:
                work = re.sub(r"\bupdation\b", "updates", work, flags=re.IGNORECASE).strip(" ,;.")
                return "{} is waiting for {} before continuing with {}. Any idea when this might be ready?".format(
                    employee_name, dependency, work
                )
            return "{} is waiting for {}. Any idea when this might be ready?".format(
                employee_name, dependency
            )
        fallback = cleaned[:1].lower() + cleaned[1:] if cleaned else "this"
        return "{} is waiting on {}. Any idea when this might be ready?".format(
            employee_name, fallback
        )

    @staticmethod
    def _get_or_create_blocker(
        db: Session, employee: Employee, owner: Employee, description: str
    ) -> Blocker:
        normalized = " ".join(description.split()).casefold()
        existing = db.scalar(
            select(Blocker)
            .where(
                Blocker.status == BlockerStatus.OPEN,
                Blocker.blocked_employee_id == employee.id,
                Blocker.dependency_owner_id == owner.id,
                func.lower(func.trim(Blocker.description)) == normalized,
            )
            .order_by(Blocker.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            return existing
        return BlockerService.create(
            db,
            BlockerCreate(
                blocked_employee_id=employee.id,
                dependency_owner_id=owner.id,
                description=" ".join(description.split()),
                severity=BlockerSeverity.MEDIUM,
            ),
        )

    @staticmethod
    def _get_or_create_unassigned_blocker(
        db: Session, employee: Employee, description: str
    ) -> Blocker:
        normalized = " ".join(description.split()).casefold()
        existing = db.scalar(
            select(Blocker)
            .where(
                Blocker.status == BlockerStatus.OPEN,
                Blocker.blocked_employee_id == employee.id,
                Blocker.dependency_owner_id.is_(None),
                func.lower(func.trim(Blocker.description)) == normalized,
            )
            .order_by(Blocker.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            return existing
        return BlockerService.create(
            db,
            BlockerCreate(
                blocked_employee_id=employee.id,
                description=" ".join(description.split()),
                severity=BlockerSeverity.MEDIUM,
            ),
        )
