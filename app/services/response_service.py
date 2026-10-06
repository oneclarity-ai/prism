"""Issue-scoped response decisions, validated mutations, and durable sends."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.agents.response_prompt import RESPONSE_PROMPT, RESPONSE_REPAIR_PROMPT
from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.automation_action import AutomationAction
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.conversation import Conversation
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.enums import (ActivityEventType, AgentAnalysisType, AgentRunStatus,
    AutomationActionStatus, AutomationActionType, BlockerStatus, CommitmentStatus,
    MessageDirection, TaskStatus)
from app.models.message import Message
from app.models.response_state import BlockerDependency, ConversationQuestion, ConversationState
from app.models.task import Task
from app.schemas.blocker import BlockerCreate, BlockerUpdate
from app.schemas.commitment import CommitmentCreate, CommitmentRevisionCreate
from app.schemas.response_decision import (
    CommitmentDecision, IssueDecision, OutgoingDecision, ResponseDecision,
)
from app.services.blocker_service import BlockerService
from app.services.commitment_service import CommitmentService
from app.services.errors import ExternalServiceError, RuleViolationError
from app.services.llm_service import LLMService
from app.services.management_context_service import ManagementContextService
from app.services.memory_service import MemoryService
from app.services.microsoft_service import MicrosoftService
from app.services.management_state_service import ManagementStateService
from app.services.temporal_memory_service import TemporalMemoryService
from app.services.message_intent_service import MessageIntentService

logger = logging.getLogger(__name__)


class ResponseService:
    @staticmethod
    def process(db: Session, message_id, *, retry_skipped=False, retry_completed=False):
        message = db.get(Message, message_id)
        if message is None or message.direction != MessageDirection.INBOUND or message.employee_id is None:
            return None
        employee = db.get(Employee, message.employee_id)
        if employee is None or not employee.is_active:
            return None
        # A session advisory lock survives service commits and prevents concurrent
        # processing in this conversation. This runs after the webhook ACK, so a
        # short wait here cannot delay Microsoft Graph.
        key = int.from_bytes(message.conversation_id.bytes[:8], "big", signed=True)
        with db.get_bind().engine.connect() as lock:
            lock.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
            try:
                # Drain replies saved while another webhook held this lock.
                # Those replies must not wait for a scheduler or manual click.
                result = None
                processed = set()
                while len(processed) < 100:
                    pending = list(db.scalars(select(Message).outerjoin(AgentRun, AgentRun.inbound_message_id == Message.id).where(
                        Message.conversation_id == message.conversation_id,
                        Message.direction == MessageDirection.INBOUND,
                        Message.created_at >= message.created_at - timedelta(minutes=5),
                        Message.id.notin_(processed),
                        or_(AgentRun.id.is_(None), AgentRun.status == AgentRunStatus.PENDING),
                    ).order_by(Message.created_at, Message.id).limit(10)))
                    if not pending and message.id not in processed:
                        pending = [message]
                    if not pending:
                        break
                    for item in pending:
                        processed.add(item.id)
                        owner = db.get(Employee, item.employee_id)
                        if owner is None:
                            continue
                        item_result = ResponseService._process_locked(db, item, owner, retry_skipped)
                        if item.id == message.id:
                            result = item_result
                return result
            finally:
                lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})

    @staticmethod
    def _process_locked(db, message, employee, retry_skipped):
        run = db.scalar(select(AgentRun).where(AgentRun.inbound_message_id == message.id))
        if run is not None and (run.status == AgentRunStatus.COMPLETED or
                               (run.status == AgentRunStatus.SKIPPED and not retry_skipped)):
            return run
        policy_version = get_settings().response_policy_version
        if run is None:
            run = AgentRun(
                inbound_message_id=message.id,
                source_employee_id=employee.id,
                policy_version=policy_version,
            )
            db.add(run)
        else:
            policy_changed = run.policy_version != policy_version
            delivery_started = bool(run.source_reply_message_id or run.dependency_message_id)
            if not delivery_started:
                delivery_started = db.scalar(select(AutomationAction.id).where(
                    AutomationAction.idempotency_key.like(f"decision:{run.id}:%")
                ).limit(1)) is not None
            if run.status == AgentRunStatus.FAILED and not run.state_applied and not delivery_started:
                # Re-analyse rejected or malformed proposals. Once any delivery
                # has started the decision is frozen so idempotency keys remain
                # stable and a retry cannot send a different second half.
                run.decision_json = None
                run.context_json = None
                run.model_deployment = None
            if policy_changed:
                # A deployment with a new response policy gets a fresh bounded
                # recovery budget, even if the old code exhausted its attempts.
                run.attempt_count = 0
            run.policy_version = policy_version
        run.status = AgentRunStatus.PENDING
        run.failure_reason = None
        run.needs_yash_review = False
        run.attempt_count = (run.attempt_count or 0) + 1
        run.last_attempt_at = datetime.now(timezone.utc)
        run.next_retry_at = None
        db.commit()
        run_id = run.id
        try:
            if run.decision_json is None:
                context = ResponseService.context(db, message, employee)
                try:
                    decision = (
                        ResponseService.deterministic_decision(context, message, employee)
                        or ResponseService.decide(context, message)
                    )
                except ExternalServiceError as provider_error:
                    context = dict(context, provider_failure=provider_error.detail)
                    decision = ResponseService.safe_provider_fallback(message, employee)
                decision = ResponseService.normalize_response_intent(decision)
                decision = ResponseService.normalize_quoted_issue(context, decision)
                decision = ResponseService.normalize_explicit_eta(message, decision)
                decision = ResponseService.normalize_explicit_commitment(message, decision)
                run.context_json = context
                run.decision_json = decision.model_dump(mode="json")
                run.model_deployment = context.get("decision_deployment")
                db.commit()  # retain proposed decision for audit, including rejected proposals
            else:
                context = run.context_json
                decision = ResponseDecision.model_validate(run.decision_json)
            if not run.state_applied:
                try:
                    ResponseService.validate(db, message, employee, context, decision)
                except RuleViolationError as first_error:
                    # Deterministic recovery is preferred to a second provider
                    # call. Validation errors must never turn into a long silent
                    # timeout for an employee.
                    direct_fallback = ResponseService.safe_validation_fallback(
                        db, message, employee, context, decision, first_error.detail
                    )
                    if direct_fallback is not None:
                        context = dict(context)
                        context["validation_feedback"] = first_error.detail
                        decision = direct_fallback
                        run.context_json = context
                        run.decision_json = decision.model_dump(mode="json")
                        db.commit()
                        ResponseService.validate(db, message, employee, context, decision)
                    else:
                        # Only a genuinely issue-scoped ambiguity gets one bounded
                        # repair attempt. Provider failure also has a source-only
                        # fallback, so this path cannot leave Teams silent.
                        context = dict(context)
                        context["rejected_decision"] = decision.model_dump(mode="json")
                        context["validation_feedback"] = first_error.detail
                        try:
                            decision = ResponseService.repair(context, message)
                        except ExternalServiceError as provider_error:
                            context["provider_failure"] = provider_error.detail
                            decision = ResponseService.safe_provider_fallback(message, employee)
                        decision = ResponseService.normalize_response_intent(decision)
                        decision = ResponseService.normalize_quoted_issue(context, decision)
                        decision = ResponseService.normalize_explicit_eta(message, decision)
                        decision = ResponseService.normalize_explicit_commitment(message, decision)
                        run.context_json = context
                        run.decision_json = decision.model_dump(mode="json")
                        run.model_deployment = context.get("decision_deployment")
                        db.commit()
                        try:
                            ResponseService.validate(db, message, employee, context, decision)
                        except RuleViolationError as repair_error:
                            fallback = ResponseService.safe_validation_fallback(
                                db, message, employee, context, decision, repair_error.detail,
                                allow_generic=True,
                            )
                            if fallback is None:
                                raise
                            context["repair_validation_feedback"] = repair_error.detail
                            decision = fallback
                            run.context_json = context
                            run.decision_json = decision.model_dump(mode="json")
                            db.commit()
                            ResponseService.validate(db, message, employee, context, decision)
                # Delivery is deliberately completed before operational state is
                # mutated. A Graph failure may leave an auditable send attempt,
                # but cannot leave blockers/commitments applied without a reply.
                existing_issue_ids = ResponseService.resolve_existing_issue_ids(
                    db, employee, decision
                )
                ResponseService.validate_delivery(db, employee, decision, context)
                ResponseService.send(db, message, employee, run, decision, existing_issue_ids)
                issue_ids = ResponseService.apply(db, message, employee, run, decision)
                context = dict(context, applied_issue_ids=issue_ids)
                run.context_json = context
                run.state_applied = True
                ResponseService.link_delivery_records(db, run, decision, issue_ids)
                db.commit()  # operational changes and applied marker are atomic
            else:
                # Legacy failed rows may have applied state but unsafe stored
                # routing. Revalidate only their delivery plan against current
                # scope before an idempotent resend.
                try:
                    ResponseService.validate_delivery(db, employee, decision, context)
                except RuleViolationError as delivery_error:
                    context = dict(context, delivery_recovery_reason=delivery_error.detail)
                    decision = ResponseService.safe_applied_delivery_fallback(message, employee)
                    run.context_json = context
                    run.decision_json = decision.model_dump(mode="json")
                    db.commit()
                    ResponseService.validate_delivery(db, employee, decision, context)
                ResponseService.send(
                    db, message, employee, run, decision,
                    context.get("applied_issue_ids", {}),
                )
            run.status = AgentRunStatus.COMPLETED
            run.processed_at = datetime.now(timezone.utc)
            run.next_retry_at = None
            db.commit()
            return run
        except Exception as exc:
            db.rollback()
            run = db.get(AgentRun, run_id)
            run.status = AgentRunStatus.FAILED
            run.needs_yash_review = True
            run.failure_reason = (
                exc.detail
                if isinstance(exc, (RuleViolationError, ExternalServiceError))
                else "Response processing failed; inspect server logs"
            )
            run.processed_at = datetime.now(timezone.utc)
            run.next_retry_at = (
                datetime.now(timezone.utc) + timedelta(seconds=min(30 * (2 ** max(run.attempt_count - 1, 0)), 300))
                if run.attempt_count < 3 else None
            )
            db.commit()
            logger.exception("response_decision_failed message_id=%s run_id=%s", message.id, run.id)
            return run

    @staticmethod
    def context(db, message, employee) -> dict:
        settings = get_settings()
        signals = MessageIntentService.analyze(message.content)
        raw_turns = list(db.scalars(select(Message).where(
            Message.conversation_id == message.conversation_id,
            Message.created_at <= message.created_at, Message.id != message.id,
        ).order_by(Message.created_at.desc(), Message.id.desc()).limit(settings.agent_context_turns)))
        all_questions = list(db.scalars(select(ConversationQuestion).where(
            ConversationQuestion.conversation_id == message.conversation_id,
            ConversationQuestion.answered_at.is_(None),
        ).order_by(ConversationQuestion.created_at.desc()).limit(10)))
        people = list(db.scalars(select(Employee).where(Employee.is_active.is_(True))))
        mentioned_people = ResponseService._mentioned_people(message.content, people)
        quoted = None
        if message.reply_to_external_id:
            quoted = db.scalar(select(Message).where(
                Message.conversation_id == message.conversation_id,
                Message.external_message_id == message.reply_to_external_id,
                Message.direction == MessageDirection.OUTBOUND,
            ))
        if quoted is None and message.quoted_content:
            # A quote without a Graph ID is usable only when it uniquely contains
            # the exact local outgoing message body. No fuzzy cross-chat matching.
            normalize = lambda value: " ".join(value.casefold().split())
            matches = [turn for turn in raw_turns if turn.direction == MessageDirection.OUTBOUND
                       and normalize(turn.content) in normalize(message.quoted_content)]
            quoted = matches[0] if len(matches) == 1 else None
        latest_question = next((item for item in all_questions
                                if raw_turns and item.message_id == raw_turns[0].id), None)
        named_owner_reply = (
            latest_question is not None and latest_question.awaiting_field == "owner"
            and any(uuid.UUID(item["id"]) != employee.id for item in mentioned_people)
        )
        has_time_answer = bool(re.search(
            r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
            r"\b\d{1,2}(?::|\.)?\d{0,2}\s*(?:am|pm)\b",
            signals.normalized,
        ))
        # Literal signals count as a contextual answer only when they match the
        # immediately preceding question's expected field. For example,
        # "I completed deployment validation" must not answer "Who owns the API?".
        direct_answer_signal = bool(latest_question and (
            (latest_question.awaiting_field == "owner" and (
                named_owner_reply or signals.owner_unknown
            ))
            or (latest_question.awaiting_field == "eta" and (
                has_time_answer or signals.commitment
            ))
            or (latest_question.awaiting_field == "completion" and (
                signals.completion or signals.contextual_answer
            ))
            or (latest_question.awaiting_field in {"outcome", "issue", "work"}
                and not signals.courtesy_only)
        ))
        if quoted is not None:
            questions = [item for item in all_questions if item.message_id == quoted.id]
            turns = [quoted]
            message_focus = "existing_issue"
        elif direct_answer_signal and latest_question is not None:
            # An unquoted answer may use only the immediately preceding open
            # question. Older unanswered questions never join a new update.
            questions = [latest_question]
            turns = [raw_turns[0]]
            message_focus = "contextual_answer"
        elif signals.contextual_answer and len(all_questions) > 1:
            # A bare ambiguous answer with several live questions is allowed to
            # see their labels solely so it can ask which one was intended.
            questions = all_questions
            turns = raw_turns
            message_focus = "contextual_answer"
        else:
            questions = []
            turns = []
            message_focus = "standalone"
        source_ids = {str(message.id)}
        if quoted is not None:
            source_ids.add(str(quoted.id))
            if all(turn.id != quoted.id for turn in turns):
                turns.append(quoted)
        question_blocker_ids = {question.blocker_id for question in questions if question.blocker_id}
        # Legacy sent messages already have issue links in AutomationAction/AgentRun.
        related_actions = list(db.scalars(select(AutomationAction).where(
            AutomationAction.message_id.in_([turn.id for turn in turns]),
            AutomationAction.blocker_id.is_not(None),
        ))) if turns else []
        action_issue_ids = {action.blocker_id for action in related_actions}
        candidate_ids = question_blocker_ids | action_issue_ids
        owner_links = select(BlockerDependency.blocker_id).where(
            BlockerDependency.employee_id == employee.id, BlockerDependency.is_active.is_(True))
        possible_blockers = list(db.scalars(select(Blocker).where(Blocker.status == BlockerStatus.OPEN, or_(
            Blocker.blocked_employee_id == employee.id, Blocker.dependency_owner_id == employee.id,
            Blocker.id.in_(owner_links), Blocker.id.in_(candidate_ids),
        )).order_by(Blocker.updated_at.desc()).limit(settings.agent_context_issues)))
        reference_signal = bool(re.search(
            r"\b(?:still|same|previous|existing|instead|actually)\b|"
            r"\b(?:this|that)\s+(?:issue|blocker|dependency)\b|"
            r"\b(?:owns?|owner)\b",
            signals.normalized,
        ))
        content_terms = ResponseService._meaningful_terms(message.content)
        blockers = []
        for item in possible_blockers:
            overlap = content_terms & ResponseService._meaningful_terms(item.description)
            if item.id in candidate_ids or (reference_signal and len(overlap) >= 1):
                blockers.append(item)
        if (not blockers and reference_signal and len(possible_blockers) == 1
                and re.search(r"\b(?:owns?|owner)\b", signals.normalized)):
            blockers = [possible_blockers[0]]
        if signals.owner_unknown and quoted is None:
            # "I don't know who owns it" is an explicit refusal to inherit
            # ownership or issue identity from history.
            blockers = []
            candidate_ids = set()
            message_focus = "standalone"
        if blockers and message_focus == "standalone":
            message_focus = "existing_issue"
        # Old versions allowed self-owned dependencies. Keep those rows for audit,
        # but never offer them to the decision model as actionable blockers.
        blockers = [item for item in blockers if item.blocked_employee_id not in item.dependency_owner_ids]
        # Explicit reply references must not be displaced by newer unrelated issues.
        for blocker_id in candidate_ids:
            item = db.get(Blocker, blocker_id)
            if (item and item.status == BlockerStatus.OPEN
                    and item.blocked_employee_id not in item.dependency_owner_ids
                    and item not in blockers):
                blockers.append(item)
        focused_issue_ids = candidate_ids | {item.id for item in blockers}
        tasks = (list(db.scalars(select(Task).where(Task.owner_id == employee.id,
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])).order_by(Task.updated_at.desc()).limit(8)))
            if message_focus != "standalone" else [])
        local_now = datetime.now(ZoneInfo(settings.manager_timezone))
        current_update = db.scalar(select(DailyUpdate).where(
            DailyUpdate.employee_id == employee.id,
            DailyUpdate.update_date == local_now.date(),
        ))
        if current_update is not None:
            source_ids.add(str(current_update.id))
        for task in tasks:
            source_ids.add(str(task.id))
            if task.project_id:
                source_ids.add(str(task.project_id))
        issues = []
        for blocker in blockers:
            source_ids.add(str(blocker.id))
            commitments = list(db.scalars(select(Commitment).where(Commitment.blocker_id == blocker.id,
                Commitment.status.in_([CommitmentStatus.OPEN, CommitmentStatus.MISSED]))))
            evidence_messages = list(db.scalars(select(Message).join(AutomationAction,
                AutomationAction.message_id == Message.id).where(AutomationAction.blocker_id == blocker.id)
                .order_by(Message.created_at.desc()).limit(4)))
            source_ids.update(str(item.id) for item in evidence_messages)
            issues.append({"id": str(blocker.id), "task_id": str(blocker.task_id) if blocker.task_id else None,
                "description": blocker.description, "blocked_employee_id": str(blocker.blocked_employee_id),
                "dependency_owner_ids": [str(value) for value in blocker.dependency_owner_ids],
                "contributions": [{"employee_id": str(value.employee_id), "resolved": value.resolved_at is not None}
                                  for value in blocker.dependencies if value.is_active],
                "commitments": [{"id": str(value.id), "employee_id": str(value.employee_id),
                                 "deadline": value.deadline.isoformat(), "status": value.status.value}
                                for value in commitments],
                "related_messages": [{"id": str(value.id), "content": value.content[:1800]} for value in evidence_messages]})
        source_ids.update(str(turn.id) for turn in turns)
        state = db.get(ConversationState, message.conversation_id)
        management_state = ManagementStateService.employee_state(
            db, employee.id, as_of=message.external_created_at or message.created_at
        )
        temporal = (TemporalMemoryService.retrieve(
            db,
            # Supplying both employee_id and issue_id makes retrieval an OR,
            # which previously pulled unrelated facts about this employee into
            # a focused issue reply. Issue context must remain issue-scoped.
            issue_id=next(iter(focused_issue_ids)) if len(focused_issue_ids) == 1 else None,
            limit=6, as_of=message.external_created_at or message.created_at,
        ) if message_focus == "existing_issue" else {"facts": [], "relations": []})
        source_ids.update(item["id"] for item in temporal["facts"])
        source_ids.update(item["id"] for item in temporal["relations"])
        # No employee-wide episodic history: it previously contaminated new issues.
        active_run = MicrosoftService.active_run(db)
        return {"now": local_now.isoformat(),
            "timezone": settings.manager_timezone, "employee_id": str(employee.id),
            "latest_message": message.content, "latest_message_id": str(message.id),
            "latest_message_created_at": (message.external_created_at or message.created_at).isoformat(),
            "quoted_message_id": str(quoted.id) if quoted else None,
            "quote_unmatched": bool(message.quoted_content or message.reply_to_external_id) and quoted is None,
            "message_focus": message_focus,
            "literal_intent": signals.intent,
            "recent_turns": [{"id": str(turn.id), "direction": turn.direction.value, "content": turn.content[:1800]}
                             for turn in reversed(turns)],
            "unresolved_questions": [{"id": str(q.id), "message_id": str(q.message_id),
                "blocker_id": str(q.blocker_id) if q.blocker_id else None,
                "task_id": str(q.task_id) if q.task_id else None, "awaiting_field": q.awaiting_field} for q in questions],
            "legacy_message_issues": [{"message_id": str(a.message_id), "blocker_id": str(a.blocker_id)} for a in related_actions],
            "active_blocker_id": (str(state.active_blocker_id)
                                  if message_focus == "existing_issue" and state and state.active_blocker_id else None),
            "active_task_id": (str(state.active_task_id)
                               if message_focus == "existing_issue" and state and state.active_task_id else None),
            "current_daily_update": ({
                "id": str(current_update.id),
                "completed_summary": current_update.completed_summary,
                "today_summary": current_update.today_summary,
                "expected_outcome": current_update.expected_outcome,
                "blocker_summary": current_update.blocker_summary,
            } if current_update else None),
            "issues": issues, "tasks": [{"id": str(t.id), "title": t.title, "outcome": t.expected_outcome,
                "project": t.project.name if t.project else None} for t in tasks],
            "people": [{"id": str(p.id), "name": p.name, "email": p.email,
                        "aliases": [alias.alias for alias in p.alias_records],
                        "teams_reachable": bool(p.teams_user_id)} for p in people],
            "mentioned_people": mentioned_people,
            # A named directory user is not automatically authorised to receive
            # an agent message.  Follow-ups are limited to the people selected
            # when the current automation run started.
            "active_automation_target_ids": (
                list(active_run.target_employee_ids or []) if active_run is not None else []
            ),
            "management_state": {
                # Response decisions see only state for the issue explicitly in
                # focus. Employee-wide state remains available to dashboards,
                # but cannot contaminate an unrelated new chat message.
                "active_work": ([item.model_dump(mode="json") for item in management_state.active_work[:5]]
                                if message_focus == "existing_issue" else []),
                "current_blockers": [item.model_dump(mode="json") for item in management_state.current_blockers
                                     if str(item.id) in {str(value) for value in focused_issue_ids}][:5],
                "open_commitments": [item.model_dump(mode="json") for item in management_state.open_commitments
                                     if str(item.blocker_id) in {str(value) for value in focused_issue_ids}][:5],
                "awaiting_answers": [item.model_dump(mode="json") for item in management_state.awaiting_answers
                                     if str(item.id) in {str(value.id) for value in questions}][:5],
                "recent_changes": ([item.model_dump(mode="json") for item in management_state.recent_changes[:6]]
                                   if message_focus == "existing_issue" else []),
            },
            "temporal_memory": temporal,
            "manager_notes": (ManagementContextService.agent_prompt_context(
                db,
                employee.name,
                query=" ".join([message.content, *(item.description for item in blockers)]),
            )
                              if message_focus == "existing_issue" else None),
            "context_source_ids": sorted(source_ids)}

    @staticmethod
    def _mentioned_people(content: str, people: list[Employee]) -> list[dict]:
        """Resolve exact, unambiguous names and manager-confirmed aliases only."""

        folded = content.casefold()
        first_name_counts: dict[str, int] = {}
        for person in people:
            first = MicrosoftService.first_name(person.name).casefold()
            first_name_counts[first] = first_name_counts.get(first, 0) + 1

        matches = []
        for person in people:
            first = MicrosoftService.first_name(person.name)
            identifiers = [(person.name, "name"), (person.email, "email")]
            identifiers.extend((record.alias, "alias") for record in person.alias_records)
            if first_name_counts.get(first.casefold()) == 1:
                identifiers.append((first, "first_name"))
            matched = next((value for value, _kind in identifiers if re.search(
                r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)", folded)), None)
            if matched:
                matches.append({"id": str(person.id), "name": person.name, "matched_text": matched})
        return matches

    @staticmethod
    def _meaningful_terms(value: str) -> set[str]:
        stop = {
            "about", "after", "again", "being", "could", "from", "have", "into", "need",
            "needed", "still", "that", "their", "there", "these", "they", "this", "waiting",
            "will", "with", "work", "working", "your", "blocked", "blocker", "dependency",
        }
        return {
            token for token in re.findall(r"[a-z0-9]+", value.casefold())
            if len(token) >= 3 and token not in stop
        }

    @staticmethod
    def decide(context, message) -> ResponseDecision:
        settings = get_settings()
        complex_context = (len(context["unresolved_questions"]) > 1
                           or len(context["issues"]) > 2
                           or len(context.get("mentioned_people", [])) > 1)
        deployment = (settings.azure_openai_reasoning_deployment if complex_context else None) or settings.azure_openai_deployment
        kwargs = dict(prompt=RESPONSE_PROMPT, context=context, output_model=ResponseDecision,
                      feature="response_decisions", conversation_id=message.conversation_id,
                      user_id=message.employee_id, message_id=message.id)
        decision = LLMService.complete(deployment=deployment, **kwargs)
        if settings.azure_openai_reasoning_deployment and deployment != settings.azure_openai_reasoning_deployment and (
            decision.confidence < 0.8 or sum(len(issue.dependency_owner_ids) for issue in decision.issues) > 1
        ):
            deployment = settings.azure_openai_reasoning_deployment
            decision = LLMService.complete(deployment=deployment, **kwargs)
        context["decision_deployment"] = deployment
        return decision

    @staticmethod
    def repair(context, message) -> ResponseDecision:
        """Ask once for a corrected structured decision after policy rejection."""

        settings = get_settings()
        deployment = settings.azure_openai_reasoning_deployment or settings.azure_openai_deployment
        decision = LLMService.complete(
            prompt=RESPONSE_REPAIR_PROMPT,
            context=context,
            output_model=ResponseDecision,
            feature="response_decision_repair",
            deployment=deployment,
            conversation_id=message.conversation_id,
            user_id=message.employee_id,
            message_id=message.id,
        )
        context["decision_deployment"] = deployment
        return decision

    @staticmethod
    def normalize_explicit_eta(message, decision: ResponseDecision) -> ResponseDecision:
        """Fill a missing, explicit wall-clock ETA relative to message time.

        The model still decides whether the statement is an ETA and which exact
        issue it belongs to. This only normalizes an unambiguous time such as
        ``6.30pm`` so a delayed replay does not lose the original promise.
        """

        reference = message.external_created_at or message.created_at
        if reference is None:
            return decision
        timezone_name = get_settings().manager_timezone
        local_reference = reference.astimezone(ZoneInfo(timezone_name))
        for issue in decision.issues:
            if issue.operation != "eta" or issue.deadline is not None:
                continue
            evidence = issue.evidence
            match = re.search(
                r"(?<!\w)(\d{1,2})(?:[.:](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?!\w)",
                evidence,
                flags=re.I,
            )
            if match is None:
                continue
            hour, minute = int(match.group(1)), int(match.group(2) or 0)
            meridiem = match.group(3).casefold().replace(".", "")
            if not 1 <= hour <= 12 or not 0 <= minute <= 59:
                continue
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
            day_offset = 1 if re.search(r"(?<!\w)tomorrow(?!\w)", evidence, flags=re.I) else 0
            candidate = local_reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if day_offset:
                candidate += timedelta(days=day_offset)
            elif candidate <= local_reference:
                # A same-day time already past when the employee wrote it is
                # ambiguous; validation will ask the model to clarify safely.
                continue
            issue.deadline = candidate
        return decision

    @staticmethod
    def _literal_deadline(message, evidence: str) -> datetime | None:
        """Parse one unambiguous employee-stated wall-clock deadline."""

        reference = message.external_created_at or message.created_at
        if reference is None:
            return None
        match = re.search(
            r"(?<!\w)(\d{1,2})(?:[.:](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?!\w)",
            evidence,
            flags=re.I,
        )
        if match is None:
            return None
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            return None
        meridiem = match.group(3).casefold().replace(".", "")
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
        local_reference = reference.astimezone(ZoneInfo(get_settings().manager_timezone))
        candidate = local_reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if re.search(r"(?<!\w)tomorrow(?!\w)", evidence, flags=re.I):
            candidate += timedelta(days=1)
        elif candidate <= local_reference:
            return None
        return candidate

    @staticmethod
    def normalize_explicit_commitment(message, decision: ResponseDecision) -> ResponseDecision:
        """Add timezone information only when the model preserved literal evidence."""

        for commitment in decision.commitments:
            if commitment.deadline.tzinfo is not None:
                continue
            parsed = ResponseService._literal_deadline(message, commitment.evidence)
            if parsed is not None:
                commitment.deadline = parsed
        return decision

    @staticmethod
    def normalize_response_intent(decision: ResponseDecision) -> ResponseDecision:
        """Derive response intent from the structured outgoing-message list.

        This fixes a bookkeeping inconsistency only. Recipient, issue, and
        operation policy is still enforced by ``validate`` before any send.
        """

        decision.should_respond = bool(decision.messages)
        if not decision.messages:
            decision.response_type = "no_response"
        else:
            kinds = {item.kind for item in decision.messages}
            if "dependency_followup" in kinds:
                decision.response_type = "dependency_followup"
            elif "clarification" in kinds:
                decision.response_type = "clarification"
            elif "status_update" in kinds:
                decision.response_type = "status_update"
            elif "conversation" in kinds:
                decision.response_type = "conversation"
            else:
                decision.response_type = "acknowledgement"
        return decision

    @staticmethod
    def normalize_quoted_issue(context, decision: ResponseDecision) -> ResponseDecision:
        """Restore the one issue explicitly linked by a Teams reply quote."""

        quoted_id = context.get("quoted_message_id")
        if quoted_id is None:
            return decision
        blocker_ids = {
            item["blocker_id"] for item in context.get("unresolved_questions", [])
            if item["message_id"] == quoted_id and item.get("blocker_id")
        }
        blocker_ids.update(
            item["blocker_id"] for item in context.get("legacy_message_issues", [])
            if item["message_id"] == quoted_id and item.get("blocker_id")
        )
        if len(blocker_ids) != 1:
            return decision
        blocker_id = uuid.UUID(next(iter(blocker_ids)))
        known_ids = {uuid.UUID(item["id"]) for item in context.get("issues", [])}
        mentioned_ids = {uuid.UUID(item["id"]) for item in context.get("mentioned_people", [])}
        if blocker_id not in known_ids:
            return decision
        for issue in decision.issues:
            if issue.blocker_id is None and issue.operation in {"set_owners", "eta", "delivered"}:
                issue.blocker_id = blocker_id
            if issue.operation == "set_owners" and mentioned_ids:
                supported_owners = [value for value in issue.dependency_owner_ids if value in mentioned_ids]
                if supported_owners:
                    issue.dependency_owner_ids = supported_owners
        return decision

    @staticmethod
    def deterministic_decision(context, message, employee):
        """Handle ordinary or literally supported messages without Azure OpenAI."""

        return (
            ResponseService.non_actionable_acknowledgement(context, message)
            or ResponseService.explicit_no_blocker_update(context, message, employee)
            or ResponseService.unknown_owner_followup(context, message, employee)
            or ResponseService.named_owner_followup(context, message, employee)
            or ResponseService.unknown_owner_blocker(context, message, employee)
            or ResponseService.new_blocker_update(context, message, employee)
            or ResponseService.standalone_commitment_update(context, message, employee)
            or ResponseService.standalone_progress_update(context, message, employee)
            or ResponseService.plain_work_update(context, message, employee)
            or ResponseService.ordinary_conversation_update(context, message, employee)
        )

    @staticmethod
    def new_blocker_update(context, message, employee):
        """Create a new issue only from a standalone, literal blocker report.

        Existing issues are intentionally ignored here. An employee must quote,
        explicitly refer to, or lexically identify an existing issue before the
        issue-scoped model path may mutate it.
        """

        signals = MessageIntentService.analyze(message.content)
        if not signals.blocker or signals.owner_unknown or context.get("quoted_message_id"):
            return None
        if context.get("message_focus") in {"existing_issue", "contextual_answer"}:
            return None
        mentioned_owners = [item for item in context.get("mentioned_people", [])
                            if uuid.UUID(item["id"]) != employee.id]
        owners = [uuid.UUID(item["id"]) for item in mentioned_owners]
        target_ids = set(context.get("active_automation_target_ids", []))
        owners_in_run = [owner_id for owner_id in owners if str(owner_id) in target_ids]
        issue_key = "new-blocker"
        if owners and len(owners_in_run) == len(owners):
            messages = [OutgoingDecision(
                recipient_id=employee.id,
                issue_key=issue_key,
                kind="acknowledgement",
                text="Thanks for flagging this. I’ll check with the named owner and keep you posted.",
            )]
        elif owners:
            owner_names = " and ".join(
                MicrosoftService.first_name(item["name"]) for item in mentioned_owners
            )
            messages = [OutgoingDecision(
                recipient_id=employee.id,
                issue_key=issue_key,
                kind="clarification",
                text=(f"Thanks for flagging this. I’ve recorded that {owner_names}'s input is needed, "
                      "but I can’t contact them through the current managed-team run yet."),
            )]
        else:
            messages = [OutgoingDecision(
                recipient_id=employee.id,
                issue_key=issue_key,
                kind="clarification",
                text="Thanks for flagging this. Who should I follow up with about this blocker?",
                awaiting_field="owner",
            )]
        source_name = MicrosoftService.first_name(employee.name)
        for owner_id in owners_in_run:
            messages.append(OutgoingDecision(
                recipient_id=owner_id,
                issue_key=issue_key,
                kind="dependency_followup",
                text=f"{source_name} is blocked on this work. When do you expect your part to be ready?",
                awaiting_field="eta",
            ))
        return ResponseDecision(
            intent="blocker",
            should_respond=True,
            response_type="dependency_followup" if owners_in_run else "clarification",
            reason="Captured a standalone blocker only from the latest employee message",
            confidence=1.0,
            needs_clarification=not owners_in_run,
            missing_information=([] if owners_in_run else
                                 (["dependency_contact_authorization"] if owners else ["dependency_owner"])),
            today_summary=message.content.strip(),
            explicitly_no_blockers=False,
            issues=[IssueDecision(
                key=issue_key,
                operation="report_blocker",
                description=message.content.strip(),
                dependency_owner_ids=owners,
                evidence=message.content.strip(),
            )],
            messages=messages,
            answered_question_ids=[],
        )

    @staticmethod
    def ordinary_conversation_update(context, message, employee):
        """Represent normal work talk without inventing blocker operations."""

        signals = MessageIntentService.analyze(message.content)
        if context.get("message_focus") != "standalone":
            return None
        if signals.blocker:
            return None
        completed, current = MessageIntentService.split_progress(message.content)
        if signals.question:
            text_value = "I’ve noted your question and will make sure it is visible to Yash."
            response_type = "conversation"
            kind = "conversation"
        elif signals.correction:
            text_value = "Thanks for the correction. I’ve updated your latest work note."
            response_type = "acknowledgement"
            kind = "acknowledgement"
        elif signals.commitment:
            text_value = "Thanks, I’ve noted your planned next step."
            response_type = "acknowledgement"
            kind = "acknowledgement"
        else:
            text_value = "Thanks, I’ve noted your update."
            response_type = "acknowledgement"
            kind = "acknowledgement"
        # A terse noun phrase such as "Deployment" is a valid work update;
        # questions are conversational but must not replace today's work state.
        captures_work_state = signals.intent not in {"question", "courtesy"}
        return ResponseDecision(
            intent={
                "completion": "task_completion",
                "work_update": "work_update",
                "commitment": "commitment",
                "correction": "correction",
                "question": "question",
                "conversation": "conversation",
            }.get(signals.intent, "conversation"),
            should_respond=True,
            response_type=response_type,
            reason="Handled ordinary work conversation without issue operations",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=(current or message.content.strip()) if captures_work_state else None,
            completed_summary=completed if captures_work_state else None,
            expected_outcome=message.content.strip() if signals.commitment else None,
            explicitly_no_blockers=False,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind=kind,
                text=text_value,
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def standalone_commitment_update(context, message, employee):
        """Track a concrete standalone promise without inventing blocker work."""

        signals = MessageIntentService.analyze(message.content)
        if (context.get("message_focus") != "standalone" or not signals.commitment
                or signals.blocker or signals.question):
            return None
        deadline = ResponseService._literal_deadline(message, message.content)
        if deadline is None:
            return None
        raw = message.content.strip()
        return ResponseDecision(
            intent="commitment",
            should_respond=True,
            response_type="acknowledgement",
            reason="Captured a literal standalone promise with a concrete deadline",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=raw,
            expected_outcome=raw,
            explicitly_no_blockers=False,
            issues=[],
            commitments=[CommitmentDecision(
                description=raw,
                evidence=raw,
                deadline=deadline,
            )],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="Thanks, I’ve recorded that commitment and its deadline.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def non_actionable_acknowledgement(context, message):
        """Skip courtesy-only replies when no operational answer is pending."""

        normalized = re.sub(r"[^a-z\s]", " ", message.content.casefold())
        words = [word for word in normalized.split() if word not in {
            "hi", "hello", "hey", "sir", "maam", "mam", "ji",
        }]
        if not words or not all(word in {
            "ok", "okay", "sure", "yes", "yeah", "yep", "thanks", "thank", "you",
            "got", "it", "noted", "fine", "for", "the", "update",
        } for word in words):
            return None
        # A bare yes can answer an outstanding yes/no or completion question.
        # Courtesy-only phrases such as "okay", "sure", and "thanks" remain
        # non-actionable even when older questions are still open in the chat.
        if context.get("unresolved_questions") and any(
            word in {"yes", "yeah", "yep"} for word in words
        ):
            return None
        return ResponseDecision(
            should_respond=False,
            response_type="no_response",
            reason="Courtesy acknowledgement contains no new operational information",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            issues=[],
            messages=[],
            answered_question_ids=[],
        )

    @staticmethod
    def plain_work_update(context, message, employee):
        """Handle an unambiguous progress statement without consulting memory/LLM.

        A sentence that says only what the employee is working on must not be
        contaminated by an older blocker. Anything suggesting a dependency,
        completion, promise, deadline, or answer to an open question continues
        through the semantic decision pipeline.
        """

        # An old unanswered question elsewhere in the same Teams chat must not
        # contaminate a new standalone work update. Treat it as an answer only
        # when the employee explicitly replied to/quoted the agent's question.
        if context.get("quoted_message_id") and context.get("unresolved_questions"):
            return None
        normalized = " ".join(message.content.casefold().split())
        work_signal = re.search(
            r"\b(i(?:'m| am)?|currently)\s+(?:am\s+)?work(?:ing|in)\s+on\b",
            normalized,
        )
        operational_signal = re.search(
            r"\b(block(?:ed|er|ing)?|wait(?:ing)?|depend(?:s|ed|ency|ent)?|pending|"
            r"need(?:s|ed)?|stuck|cannot|can't|done|complete(?:d)?|deployed|finish(?:ed)?|"
            r"eta|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            normalized,
        )
        if work_signal is None or operational_signal is not None:
            return None
        return ResponseDecision(
            should_respond=True,
            response_type="acknowledgement",
            reason="Captured an unambiguous work update without reviving historical issues",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=message.content.strip(),
            completed_summary=None,
            expected_outcome=None,
            explicitly_no_blockers=False,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="Thanks, I’ve noted your update.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def standalone_progress_update(context, message, employee):
        """Capture completed work plus current work without reviving old issues."""

        if context.get("quoted_message_id") and context.get("unresolved_questions"):
            return None
        raw = message.content.strip()
        normalized = " ".join(raw.casefold().split())
        completion = re.search(
            r"\b(finished|completed|wrapped\s+up|done)\b", normalized
        )
        current_activity = re.search(
            r"\b(now|currently)\b.{0,60}\b(working|testing|reviewing|validating|"
            r"checking|implementing|building|fixing|developing)\b",
            normalized,
        )
        dependency = re.search(
            r"\b(block(?:ed|er|ing)?|wait(?:ing)?|depend(?:s|ed|ency|ent)?|"
            r"pending|need(?:s|ed)?|stuck|cannot|can't|unclear|missing)\b",
            normalized,
        )
        if completion is None or current_activity is None or dependency is not None:
            return None

        completed_summary = raw
        today_summary = raw
        completed_match = re.search(
            r"(?:^|[.!?]\s*)([^.!?]*?\b(?:finished|completed|wrapped\s+up|done)\b.*?)"
            r"(?=,?\s+and\s+now\b|[.!?]|$)",
            raw,
            flags=re.I,
        )
        current_match = re.search(
            r"\bnow\b\s+(.+)$", raw, flags=re.I
        )
        if completed_match:
            completed_summary = completed_match.group(1).strip(" ,.;")
        if current_match:
            today_summary = current_match.group(1).strip(" ,.;")

        return ResponseDecision(
            should_respond=True,
            response_type="acknowledgement",
            reason="Captured completed and current work without unrelated historical issues",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=today_summary,
            completed_summary=completed_summary,
            expected_outcome=None,
            explicitly_no_blockers=False,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="Thanks, I’ve noted what you finished and what you’re working on now.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def unknown_owner_blocker(context, message, employee):
        """Record a new ownerless blocker when the employee says ownership is unknown."""

        if context.get("quoted_message_id"):
            return None
        raw = message.content.strip()
        normalized = " ".join(raw.casefold().replace("’", "'").split())
        blocker_signal = re.search(
            r"\b(blocked|blocker|blocking|stuck|cannot|can't|waiting)\b",
            normalized,
        )
        owner_unknown = re.search(
            r"\b(?:i\s+)?(?:do\s+not|don't)\s+know\s+(?:who\s+owns\s+it|the\s+owner)\b|"
            r"\bnot\s+sure\s+who\s+owns\s+it\b|"
            r"\b(?:the\s+)?owner\s+is\s+unknown\b|\bunknown\s+owner\b",
            normalized,
        )
        if blocker_signal is None or owner_unknown is None:
            return None
        issue_key = "new-ownerless-blocker"
        return ResponseDecision(
            should_respond=True,
            response_type="clarification",
            reason="Employee reported a new blocker and explicitly said its owner is unknown",
            confidence=1.0,
            needs_clarification=True,
            missing_information=["dependency_owner"],
            today_summary=raw,
            completed_summary=None,
            expected_outcome=None,
            explicitly_no_blockers=False,
            issues=[IssueDecision(
                key=issue_key,
                blocker_id=None,
                task_id=None,
                operation="report_blocker",
                description=raw,
                dependency_owner_ids=[],
                evidence=raw,
                deadline=None,
                missed_reason=None,
            )],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                issue_key=issue_key,
                kind="clarification",
                text="Thanks for flagging this. Who should I follow up with about this blocker?",
                awaiting_field="owner",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def unknown_owner_followup(context, message, employee):
        """Keep an owner question open when a quoted reply says it is still unknown."""

        quoted_id = context.get("quoted_message_id")
        if quoted_id is None:
            return None
        normalized = " ".join(message.content.casefold().replace("’", "'").split())
        owner_unknown = re.search(
            r"\b(?:i\s+)?(?:still\s+)?(?:do\s+not|don't)\s+know\s+"
            r"(?:who\s+owns\s+it|the\s+owner)\b|"
            r"\b(?:still\s+)?not\s+sure\s+who\s+owns\s+it\b|"
            r"\b(?:the\s+)?owner\s+is\s+(?:still\s+)?unknown\b",
            normalized,
        )
        matching_questions = [
            item for item in context.get("unresolved_questions", [])
            if item.get("message_id") == quoted_id and item.get("awaiting_field") == "owner"
        ]
        if owner_unknown is None or not matching_questions:
            return None
        return ResponseDecision(
            should_respond=True,
            response_type="acknowledgement",
            reason="Employee confirmed that the blocker owner is still unknown",
            confidence=1.0,
            needs_clarification=True,
            missing_information=["dependency_owner"],
            today_summary=None,
            completed_summary=None,
            expected_outcome=None,
            explicitly_no_blockers=False,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                issue_key=None,
                kind="acknowledgement",
                text="No problem—I’ll keep the blocker open until you know who owns it.",
                awaiting_field=None,
            )],
            # The owner question deliberately remains unanswered.
            answered_question_ids=[],
        )

    @staticmethod
    def named_owner_followup(context, message, employee):
        """Assign an owner named in a bare reply to the one open owner question.

        Counterpart to ``unknown_owner_followup``: once exactly one open "owner"
        question is live and exactly one known person (the same exact name/
        alias/email match ``validate`` requires) is named, this closes the loop
        without sending a fact this codebase can already verify to Azure OpenAI.
        """

        if context.get("quoted_message_id"):
            return None
        owner_questions = [
            item for item in context.get("unresolved_questions", [])
            if item.get("awaiting_field") == "owner" and item.get("blocker_id")
        ]
        mentioned = [item for item in context.get("mentioned_people", [])
                     if item["id"] != str(employee.id)]
        if len(owner_questions) != 1 or len(mentioned) != 1:
            return None
        blocker_id = owner_questions[0]["blocker_id"]
        issue = next((item for item in context.get("issues", []) if item["id"] == blocker_id), None)
        if issue is None:
            return None
        owner_id = uuid.UUID(mentioned[0]["id"])
        source_name = MicrosoftService.first_name(employee.name)
        owner_first_name = MicrosoftService.first_name(mentioned[0]["name"])
        issue_key = "named-owner"
        return ResponseDecision(
            should_respond=True,
            response_type="dependency_followup",
            reason="Employee named the single known owner for the one open owner question",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=None,
            completed_summary=None,
            expected_outcome=None,
            explicitly_no_blockers=False,
            issues=[IssueDecision(
                key=issue_key, blocker_id=uuid.UUID(blocker_id), operation="set_owners",
                description=issue["description"], dependency_owner_ids=[owner_id],
                evidence=message.content.strip(),
            )],
            messages=[
                OutgoingDecision(recipient_id=employee.id, issue_key=issue_key, kind="acknowledgement",
                    text=f"Thanks, I’ve noted that {owner_first_name} owns this. I’ll check with them."),
                OutgoingDecision(recipient_id=owner_id, issue_key=issue_key, kind="dependency_followup",
                    text=f"{source_name} says your input is needed for their current work. When do you expect it to be ready?",
                    awaiting_field="eta"),
            ],
            answered_question_ids=[uuid.UUID(owner_questions[0]["id"])],
        )

    @staticmethod
    def explicit_no_blocker_update(context, message, employee):
        """Capture a literal no-blocker statement without asking the model.

        Historical issues and model guesses must never turn phrases such as
        "no dependency or blocker" into new dependency communication.
        """

        normalized = " ".join(message.content.casefold().split())
        if not re.search(
            r"\b(no|without)\s+(?:(?:dependency|dependencies)\s+(?:or|and)\s+)?"
            r"(?:blocker|blockers)\b|"
            r"\bno\s+(?:dependency|dependencies)\b|"
            r"\bnot\s+blocked\b|\bnothing\s+(?:is\s+)?block(?:ed|ing)\b",
            normalized,
        ):
            return None
        # If the agent is awaiting a concrete answer about an existing issue,
        # let the issue-scoped decision path interpret it instead of globally
        # clearing historical state.
        if context.get("quoted_message_id") and any(
            item.get("blocker_id") for item in context.get("unresolved_questions", [])
        ):
            return None
        return ResponseDecision(
            should_respond=True,
            response_type="acknowledgement",
            reason="Captured the employee's explicit no-blocker update",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=message.content.strip(),
            completed_summary=None,
            expected_outcome=None,
            explicitly_no_blockers=True,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="Thanks, I’ve noted the consolidated update and that there are no blockers.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def safe_unmapped_update_fallback(message, employee, decision):
        """Downgrade only a fully unmapped completion proposal to a safe update.

        This is deliberately narrow: it never creates, resolves, reassigns, or
        messages a third party. The employee's exact statement remains available
        for later manager review instead of making the whole response loop fail.
        """

        if not decision.issues or not all(
            (item.operation == "delivered" and item.blocker_id is None)
            or (item.operation == "complete_task" and item.task_id is None)
            for item in decision.issues
        ):
            return None
        if any(item.recipient_id != employee.id for item in decision.messages):
            return None
        return ResponseDecision(
            should_respond=True,
            response_type="acknowledgement",
            reason="Safely captured an update that could not be linked to a tracked item",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=message.content.strip(),
            completed_summary=decision.completed_summary,
            expected_outcome=decision.expected_outcome,
            explicitly_no_blockers=decision.explicitly_no_blockers,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="Thanks, I’ve noted this update.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def safe_no_blocker_fallback(message, employee, decision, error_detail):
        """Keep an explicit no-blocker update and discard invented dependencies."""

        if error_detail != "A no-blocker update cannot introduce dependency actions":
            return None
        normalized = " ".join(message.content.casefold().split())
        if not re.search(
            r"\b(no|without)\s+(?:dependency|dependencies|blocker|blockers)\b|"
            r"\bnot\s+blocked\b|\bnothing\s+(?:is\s+)?block(?:ed|ing)\b",
            normalized,
        ):
            return None
        return ResponseDecision(
            should_respond=True,
            response_type="acknowledgement",
            reason="Captured an explicit no-blocker update without invented dependency actions",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=decision.today_summary or message.content.strip(),
            completed_summary=decision.completed_summary,
            expected_outcome=decision.expected_outcome,
            explicitly_no_blockers=True,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="Thanks, I’ve noted the update and that there are no blockers.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def safe_stale_issue_fallback(message, employee, context, decision, error_detail):
        """Keep a real work update but discard actions based on a stale issue ID.

        The LLM may recognise language from older organisational memory and then
        attach a new reply to that historical blocker. Deterministic validation
        correctly rejects it. If repair repeats the same mistake, this fallback
        records only the employee's literal update and acknowledges that person;
        it never creates a blocker or contacts the hallucinated owner.
        """

        supported_errors = {
            "Issue is outside this conversation's active context",
            "This action requires an existing issue",
        }
        if error_detail not in supported_errors:
            return None
        known_ids = {uuid.UUID(item["id"]) for item in context.get("issues", [])}
        if not decision.issues:
            return None
        if error_detail == "Issue is outside this conversation's active context":
            if any(item.blocker_id is None or item.blocker_id in known_ids for item in decision.issues):
                return None
        else:
            if known_ids or any(
                item.blocker_id is not None or item.operation not in {"eta", "delivered", "set_owners"}
                for item in decision.issues
            ):
                return None
        return ResponseDecision(
            should_respond=True,
            response_type="acknowledgement",
            reason="Discarded a stale issue link and safely retained the literal employee update",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=message.content.strip(),
            completed_summary=None,
            expected_outcome=None,
            explicitly_no_blockers=False,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="Thanks, I’ve noted your update.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def safe_issue_communication_fallback(db, message, employee, context, decision, error_detail):
        """Complete only the missing messages around an already safe issue action."""

        communication_errors = {
            "A dependency request must target an owner of that exact issue",
            "An ETA or delivery update cannot be sent as a dependency request",
            "An ETA or delivery confirmation must acknowledge the speaking owner",
            "An ETA or delivery confirmation must update the blocked employee",
            "The matching ETA or completion question must be marked answered",
            "Acknowledgements and status updates cannot open a pending question",
        }
        if error_detail not in communication_errors or not decision.issues:
            return None
        known_issue_ids = {uuid.UUID(item["id"]) for item in context.get("issues", [])}
        repaired = decision.model_copy(deep=True)
        repaired_messages = [
            item for item in repaired.messages
            if item.issue_key not in {issue.key for issue in repaired.issues}
        ]
        answered = set(repaired.answered_question_ids)
        for issue in repaired.issues:
            if issue.operation not in {"eta", "delivered"} or issue.blocker_id not in known_issue_ids:
                return None
            blocker = db.get(Blocker, issue.blocker_id)
            if (blocker is None or blocker.status != BlockerStatus.OPEN
                    or employee.id not in blocker.dependency_owner_ids
                    or issue.evidence.casefold() not in message.content.casefold()):
                return None
            if issue.operation == "eta" and issue.deadline is None:
                return None
            existing = [item for item in decision.messages if item.issue_key == issue.key]
            acknowledgement = next((item for item in existing
                if item.recipient_id == employee.id and item.kind == "acknowledgement"
                and item.awaiting_field is None), None)
            status_update = next((item for item in existing
                if item.recipient_id == blocker.blocked_employee_id and item.kind == "status_update"
                and item.awaiting_field is None), None)
            if acknowledgement is None:
                if issue.operation == "eta":
                    local_deadline = issue.deadline.astimezone(ZoneInfo(get_settings().manager_timezone))
                    time_label = local_deadline.strftime("%I:%M %p").lstrip("0")
                    acknowledgement = OutgoingDecision(
                        recipient_id=employee.id, issue_key=issue.key, kind="acknowledgement",
                        text=f"Thanks, I’ve noted the {time_label} ETA.",
                    )
                else:
                    acknowledgement = OutgoingDecision(
                        recipient_id=employee.id, issue_key=issue.key, kind="acknowledgement",
                        text="Thanks, I’ve noted that your part is complete.",
                    )
            repaired_messages.append(acknowledgement)
            if blocker.blocked_employee_id != employee.id:
                if status_update is None:
                    first_name = MicrosoftService.first_name(employee.name)
                    if issue.operation == "eta":
                        local_deadline = issue.deadline.astimezone(ZoneInfo(get_settings().manager_timezone))
                        time_label = local_deadline.strftime("%I:%M %p").lstrip("0")
                        text_value = f"{first_name} expects to have their part ready by {time_label}."
                    else:
                        text_value = f"{first_name} has confirmed that their part is complete."
                    status_update = OutgoingDecision(
                        recipient_id=blocker.blocked_employee_id, issue_key=issue.key,
                        kind="status_update", text=text_value,
                    )
                repaired_messages.append(status_update)
            awaiting = "eta" if issue.operation == "eta" else "completion"
            answered.update(
                uuid.UUID(item["id"])
                for item in context.get("unresolved_questions", [])
                if item["blocker_id"] == str(issue.blocker_id) and item["awaiting_field"] == awaiting
            )
        repaired.messages = repaired_messages
        repaired.answered_question_ids = list(answered)
        repaired.should_respond = bool(repaired_messages)
        repaired.response_type = "status_update" if repaired_messages else "no_response"
        repaired.reason = f"{repaired.reason}; completed required issue-loop communication"
        return repaired

    @staticmethod
    def safe_owner_handoff_fallback(db, message, employee, context, decision, error_detail):
        """Complete an explicit, quoted owner handoff without guessing identity."""

        if error_detail not in {
            "Known dependency owner is missing its follow-up request",
            "Acknowledgements and status updates cannot open a pending question",
        }:
            return None
        if not decision.issues or any(item.operation != "set_owners" for item in decision.issues):
            return None
        known_issue_ids = {uuid.UUID(item["id"]) for item in context.get("issues", [])}
        mentioned_ids = {uuid.UUID(item["id"]) for item in context.get("mentioned_people", [])}
        repaired = decision.model_copy(deep=True)
        issue_keys = {item.key for item in repaired.issues}
        messages = [item for item in repaired.messages if item.issue_key not in issue_keys]
        answered = set(repaired.answered_question_ids)
        for issue in repaired.issues:
            if issue.blocker_id not in known_issue_ids or not issue.dependency_owner_ids:
                return None
            blocker = db.get(Blocker, issue.blocker_id)
            if (blocker is None or blocker.status != BlockerStatus.OPEN
                    or (employee.id != blocker.blocked_employee_id
                        and employee.id not in blocker.dependency_owner_ids)
                    or not set(issue.dependency_owner_ids) <= mentioned_ids
                    or issue.evidence.casefold() not in message.content.casefold()):
                return None
            issue.description = blocker.description
            owner_names = [MicrosoftService.first_name(db.get(Employee, value).name)
                           for value in issue.dependency_owner_ids]
            owner_label = " and ".join(owner_names)
            messages.append(OutgoingDecision(
                recipient_id=employee.id,
                issue_key=issue.key,
                kind="acknowledgement",
                text=f"Thanks, I’ve noted that {owner_label} owns this. I’ll check with them.",
            ))
            source_name = MicrosoftService.first_name(employee.name)
            for owner_id in issue.dependency_owner_ids:
                messages.append(OutgoingDecision(
                    recipient_id=owner_id,
                    issue_key=issue.key,
                    kind="dependency_followup",
                    text=(f"{source_name} says your input is needed for their current work. "
                          "When do you expect it to be ready?"),
                    awaiting_field="eta",
                ))
            answered.update(
                uuid.UUID(item["id"])
                for item in context.get("unresolved_questions", [])
                if item["blocker_id"] == str(issue.blocker_id)
                and item["message_id"] == context.get("quoted_message_id")
            )
        repaired.messages = messages
        repaired.answered_question_ids = list(answered)
        repaired.should_respond = True
        repaired.response_type = "dependency_followup"
        repaired.reason = f"{repaired.reason}; completed explicit quoted owner handoff"
        return repaired

    @staticmethod
    def safe_provider_fallback(message, employee):
        """Acknowledge a provider timeout without claiming an operational change."""

        signals = MessageIntentService.analyze(message.content)
        is_blocker = signals.blocker
        return ResponseDecision(
            intent="blocker" if is_blocker else {
                "completion": "task_completion",
                "work_update": "work_update",
                "commitment": "commitment",
                "correction": "correction",
                "question": "question",
                "conversation": "conversation",
                "courtesy": "acknowledgement",
            }.get(signals.intent, "unclear"),
            should_respond=True,
            response_type="clarification" if is_blocker else "acknowledgement",
            reason="Provider was unavailable; returned a source-only safe response",
            confidence=1.0,
            needs_clarification=is_blocker,
            missing_information=["safe_routing_review"] if is_blocker else [],
            today_summary=message.content.strip(),
            completed_summary=message.content.strip() if signals.completion else None,
            explicitly_no_blockers=signals.explicit_no_blocker,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="clarification" if is_blocker else "acknowledgement",
                text=("I received your blocker update, but I couldn’t safely route it yet. "
                      "I’ll leave it for Yash to review."
                      if is_blocker else "Thanks, I’ve received your update."),
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def safe_applied_delivery_fallback(message, employee):
        """Replace unsafe legacy routing after state was already applied."""

        return ResponseDecision(
            intent="unclear",
            should_respond=True,
            response_type="acknowledgement",
            reason="Rebuilt unsafe legacy delivery as a source-only acknowledgement",
            confidence=1.0,
            needs_clarification=False,
            missing_information=[],
            today_summary=None,
            completed_summary=None,
            expected_outcome=None,
            explicitly_no_blockers=False,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="acknowledgement",
                text="I recorded your update, but the follow-up routing needs Yash’s review.",
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def safe_generic_validation_fallback(message, employee, error_detail):
        """Never leave a source silent because an unsafe model action was rejected."""

        signals = MessageIntentService.analyze(message.content)
        is_blocker = signals.blocker
        return ResponseDecision(
            intent="blocker" if is_blocker else {
                "completion": "task_completion",
                "work_update": "work_update",
                "commitment": "commitment",
                "correction": "correction",
                "question": "question",
                "conversation": "conversation",
                "courtesy": "acknowledgement",
            }.get(signals.intent, "unclear"),
            should_respond=True,
            response_type="clarification" if is_blocker else "acknowledgement",
            reason=f"Unsafe proposal was reduced to a source-only response: {error_detail}",
            confidence=1.0,
            needs_clarification=is_blocker,
            missing_information=["manager_review"] if is_blocker else [],
            today_summary=message.content.strip(),
            completed_summary=message.content.strip() if signals.completion else None,
            expected_outcome=message.content.strip() if signals.commitment else None,
            explicitly_no_blockers=signals.explicit_no_blocker,
            issues=[],
            messages=[OutgoingDecision(
                recipient_id=employee.id,
                kind="clarification" if is_blocker else "acknowledgement",
                text=("I received the blocker update, but I couldn’t safely determine the follow-up. "
                      "I’ll leave it for Yash to review."
                      if is_blocker else "Thanks, I’ve noted this update."),
            )],
            answered_question_ids=[],
        )

    @staticmethod
    def safe_validation_fallback(
        db, message, employee, context, decision, error_detail, *, allow_generic=False
    ):
        """Return the first deterministic correction that cannot widen authority."""

        fallback = (
            ResponseService.safe_no_blocker_fallback(message, employee, decision, error_detail)
            or ResponseService.safe_unmapped_update_fallback(message, employee, decision)
            or ResponseService.safe_stale_issue_fallback(
                message, employee, context, decision, error_detail
            )
            or ResponseService.safe_issue_communication_fallback(
                db, message, employee, context, decision, error_detail
            )
            or ResponseService.safe_owner_handoff_fallback(
                db, message, employee, context, decision, error_detail
            )
        )
        if fallback is not None:
            return ResponseService.normalize_response_intent(fallback)
        generic_errors = {
            "Inconsistent response intent",
            "Unknown outgoing issue key",
            "Issue evidence must occur in the actual employee reply",
            "Proposed owner is not supported by current evidence",
            "Outgoing recipient is outside the active automation run",
            "Recipient does not belong to this issue",
            "Dependency owner cannot be reached through Teams",
            "This action requires an existing issue",
            "Issue is outside this conversation's active context",
            "A dependency request must target an owner of that exact issue",
            "Known dependency owner is missing its follow-up request",
        }
        if allow_generic or error_detail in generic_errors:
            return ResponseService.safe_generic_validation_fallback(
                message, employee, error_detail
            )
        return None

    @staticmethod
    def validate_delivery(db, employee, decision, context):
        """Recheck current recipient authority immediately before every retry."""

        def require(condition, detail):
            if not condition:
                raise RuleViolationError(detail)

        require(decision.should_respond == bool(decision.messages), "Inconsistent response intent")
        issue_keys = {item.key for item in decision.issues}
        issue_keys.update((context.get("applied_issue_ids") or {}).keys())
        people = {
            item.id: item for item in db.scalars(
                select(Employee).where(Employee.is_active.is_(True))
            )
        }
        active_run = MicrosoftService.active_run(db)
        for outgoing in decision.messages:
            require(outgoing.recipient_id in people, "Unknown message recipient")
            require(outgoing.issue_key is None or outgoing.issue_key in issue_keys,
                    "Unknown outgoing issue key")
            if outgoing.recipient_id != employee.id:
                require(outgoing.issue_key is not None,
                        "Third-party messages require an issue link")
                require(active_run is not None and str(outgoing.recipient_id) in set(
                    active_run.target_employee_ids or []
                ), "Outgoing recipient is outside the active automation run")
                require(bool(people[outgoing.recipient_id].teams_user_id),
                        "Dependency owner cannot be reached through Teams")

    @staticmethod
    def validate(db, message, employee, context, decision):
        def require(condition, detail):
            if not condition:
                raise RuleViolationError(detail)
        require(decision.should_respond == bool(decision.messages), "Inconsistent response intent")
        normalized_source = " ".join(message.content.casefold().replace("’", "'").split())
        explicitly_unknown_owner = bool(re.search(
            r"\b(?:i\s+)?(?:do\s+not|don't)\s+know\s+(?:who\s+owns\s+it|the\s+owner)\b|"
            r"\bnot\s+sure\s+who\s+owns\s+it\b|"
            r"\b(?:the\s+)?owner\s+is\s+unknown\b|\bunknown\s+owner\b",
            normalized_source,
        ))
        if explicitly_unknown_owner:
            require(not any(
                issue.blocker_id is not None or issue.dependency_owner_ids
                for issue in decision.issues
                if issue.operation in {"report_blocker", "set_owners"}
            ), "An explicitly unknown owner cannot be inherited from historical issues")
            require(not any(
                outgoing.recipient_id != employee.id or outgoing.kind == "dependency_followup"
                for outgoing in decision.messages
            ), "An owner-unknown blocker may only clarify with the reporting employee")
        require(not decision.explicitly_no_blockers or not decision.issues,
                "A no-blocker update cannot introduce dependency actions")
        require(decision.confidence >= 0.8 or (
            not decision.issues and not decision.commitments and all(
            m.recipient_id == employee.id and m.kind == "clarification" for m in decision.messages)),
            "Uncertain decisions may only clarify with the source")
        known = {uuid.UUID(item["id"]): item for item in context["issues"]}
        people = {uuid.UUID(item["id"]): item for item in context["people"]}
        task_ids = {uuid.UUID(item["id"]) for item in context["tasks"]}
        questions = {uuid.UUID(item["id"]): item for item in context["unresolved_questions"]}
        require(set(decision.answered_question_ids) <= questions.keys(), "Unknown outstanding question")
        require(len({issue.key for issue in decision.issues}) == len(decision.issues), "Duplicate issue keys")
        issue_facts = [
            (item.operation, item.blocker_id, item.task_id, " ".join(item.description.casefold().split()))
            for item in decision.issues
        ]
        require(len(issue_facts) == len(set(issue_facts)), "One stated fact cannot be duplicated")
        stated_at = message.external_created_at or message.created_at
        commitment_facts = set()
        for commitment in decision.commitments:
            require(commitment.evidence.casefold() in message.content.casefold(),
                    "Commitment evidence must occur in the actual employee reply")
            require(commitment.deadline.tzinfo is not None and commitment.deadline > stated_at,
                    "Commitment deadline must be future and timezone-aware")
            require(commitment.task_id is None or commitment.task_id in task_ids,
                    "Unknown task link")
            fact = (
                commitment.task_id,
                " ".join(commitment.description.casefold().split()),
                commitment.deadline,
            )
            require(fact not in commitment_facts, "One stated commitment cannot be duplicated")
            commitment_facts.add(fact)
        allowed = {}
        for issue in decision.issues:
            require(issue.evidence.casefold() in message.content.casefold(), "Issue evidence must occur in the actual employee reply")
            require(issue.blocker_id is None or issue.blocker_id in known, "Issue is outside this conversation's active context")
            previous = known.get(issue.blocker_id)
            quoted_id = context.get("quoted_message_id")
            quoted_issues = {q["blocker_id"] for q in questions.values() if q["message_id"] == quoted_id and q["blocker_id"]}
            quoted_issues.update(item["blocker_id"] for item in context.get("legacy_message_issues", []) if item["message_id"] == quoted_id)
            if issue.operation in {"eta", "delivered", "complete_task"}:
                require(not context.get("quote_unmatched"), "Quoted message could not be linked; clarify before applying a promise")
                if quoted_issues:
                    require(str(issue.blocker_id) in quoted_issues, "Decision conflicts with the issue explicitly quoted by the employee")
                for qid in decision.answered_question_ids:
                    q = questions[qid]
                    if q["message_id"] == quoted_id and q["task_id"]:
                        require(str(issue.task_id) == q["task_id"], "Completion conflicts with the quoted task")
            blocker = db.scalar(select(Blocker).where(Blocker.id == issue.blocker_id).with_for_update()) if issue.blocker_id else None
            require(not blocker or blocker.status == BlockerStatus.OPEN, "A resolved issue cannot be changed")
            if previous and blocker:
                require(set(previous["dependency_owner_ids"]) == {str(value) for value in blocker.dependency_owner_ids},
                        "Issue ownership changed during analysis; review the decision against fresh state")
            if issue.task_id:
                require(issue.task_id in task_ids or (blocker and blocker.task_id == issue.task_id), "Unknown task link")
            if issue.operation in {"eta", "delivered", "set_owners"}:
                require(blocker is not None, "This action requires an existing issue")
            if issue.operation == "report_blocker" and issue.blocker_id is None:
                require(context.get("message_focus") == "standalone" or not known,
                        "A contextual reply cannot silently create a different issue")
            if issue.operation in {"eta", "delivered"}:
                require(employee.id in blocker.dependency_owner_ids, "Only that dependency's owner can confirm an ETA or delivery")
            if issue.operation in {"report_blocker", "set_owners"}:
                blocked_id = blocker.blocked_employee_id if blocker else employee.id
                if blocker:
                    require(employee.id == blocked_id or employee.id in blocker.dependency_owner_ids, "Unrelated employee cannot change this issue")
                for owner_id in issue.dependency_owner_ids:
                    require(owner_id in people and owner_id != blocked_id, "Unknown or self-referential dependency owner")
                    person = people[owner_id]
                    first = person["name"].split()[0]
                    evidence = message.content.casefold()
                    named = any(
                        re.search(r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)", evidence)
                        for value in [person["name"], person["email"], first, *person.get("aliases", [])]
                    )
                    # A first name shared by two people is not a verified identity.
                    if named and sum(p["name"].split()[0].casefold() == first.casefold() for p in people.values()) > 1:
                        named = any(re.search(
                            r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)", evidence
                        ) for value in [person["name"], person["email"], *person.get("aliases", [])])
                    known_owner = previous and str(owner_id) in previous["dependency_owner_ids"]
                    require(named or known_owner, "Proposed owner is not supported by current evidence")
                if previous and issue.operation == "report_blocker":
                    require(not issue.dependency_owner_ids or set(issue.dependency_owner_ids) == set(blocker.dependency_owner_ids),
                            "Owner changes require an explicit set_owners decision")
            if issue.deadline is not None:
                require(issue.operation == "eta", "Deadline mutation requires an ETA action")
                stated_at = message.external_created_at or message.created_at
                require(issue.deadline.tzinfo is not None and issue.deadline > stated_at,
                        "ETA must be later than the employee message and timezone-aware")
                existing = db.scalar(select(Commitment).where(Commitment.blocker_id == issue.blocker_id,
                    Commitment.employee_id == employee.id, Commitment.status == CommitmentStatus.OPEN))
                require(existing is None or existing.deadline == issue.deadline, "An open commitment deadline cannot silently change")
            if issue.operation == "eta":
                require(issue.deadline is not None, "ETA needs a concrete deadline")
            if issue.operation == "complete_task":
                task = db.get(Task, issue.task_id) if issue.task_id else None
                require(task is not None and task.owner_id == employee.id, "Task completion requires the actual task owner")
                require(not db.scalar(select(Blocker.id).where(Blocker.task_id == task.id, Blocker.status == BlockerStatus.OPEN).limit(1)),
                        "Resolve outstanding task blockers before completing the task")
            recipients = {employee.id}
            if blocker:
                recipients.add(blocker.blocked_employee_id)
                recipients.update(blocker.dependency_owner_ids)
            recipients.update(issue.dependency_owner_ids)
            allowed[issue.key] = recipients
        for outgoing in decision.messages:
            require(outgoing.recipient_id in people, "Unknown message recipient")
            active_run = MicrosoftService.active_run(db)
            if active_run is not None and outgoing.recipient_id != employee.id:
                require(
                    str(outgoing.recipient_id) in set(active_run.target_employee_ids or []),
                    "Outgoing recipient is outside the active automation run",
                )
            require(outgoing.issue_key is None or outgoing.issue_key in allowed, "Unknown outgoing issue key")
            require(outgoing.recipient_id == employee.id or (
                outgoing.issue_key in allowed and outgoing.recipient_id in allowed[outgoing.issue_key]), "Recipient does not belong to this issue")
            if outgoing.recipient_id != employee.id:
                require(people[outgoing.recipient_id]["teams_reachable"], "Dependency owner cannot be reached through Teams")
            if outgoing.kind == "dependency_followup":
                operation = next((item for item in decision.issues if item.key == outgoing.issue_key), None)
                require(operation is not None and outgoing.recipient_id in operation.dependency_owner_ids,
                        "A dependency request must target an owner of that exact issue")
            if outgoing.kind in {"acknowledgement", "status_update"}:
                require(outgoing.awaiting_field is None,
                        "Acknowledgements and status updates cannot open a pending question")
            normalized_text = " ".join(outgoing.text.casefold().split())
            require(not any(fragment in normalized_text for fragment in (
                "waiting on awaiting", "needs awaiting", "dependency owned by",
            )), "Generated message is too mechanical or grammatically invalid")
        message_keys = [
            (item.recipient_id, item.issue_key, item.kind, " ".join(item.text.casefold().split()))
            for item in decision.messages
        ]
        require(len(message_keys) == len(set(message_keys)), "Duplicate outgoing message in one decision")
        # ETA/delivery changes close a loop between two people. They must not be
        # mislabeled as a new owner request, and neither participant may be left
        # without the appropriate acknowledgement/update.
        for issue in decision.issues:
            if issue.operation not in {"eta", "delivered"}:
                continue
            blocker = db.get(Blocker, issue.blocker_id)
            related = [item for item in decision.messages if item.issue_key == issue.key]
            require(not any(item.kind == "dependency_followup" for item in related),
                    "An ETA or delivery update cannot be sent as a dependency request")
            require(any(item.recipient_id == employee.id and item.kind == "acknowledgement" for item in related),
                    "An ETA or delivery confirmation must acknowledge the speaking owner")
            if blocker.blocked_employee_id != employee.id:
                require(any(item.recipient_id == blocker.blocked_employee_id and item.kind == "status_update"
                            for item in related),
                        "An ETA or delivery confirmation must update the blocked employee")
            awaiting = "eta" if issue.operation == "eta" else "completion"
            matching_questions = {
                question_id for question_id, item in questions.items()
                if item["blocker_id"] == str(issue.blocker_id) and item["awaiting_field"] == awaiting
            }
            if matching_questions:
                require(bool(matching_questions & set(decision.answered_question_ids)),
                        "The matching ETA or completion question must be marked answered")
        # Each reported owner must have an associated request, unless one is
        # already outstanding. This prevents a model from dropping the second owner.
        for issue in decision.issues:
            if issue.operation not in {"report_blocker", "set_owners"}:
                continue
            if issue.operation == "report_blocker" and issue.blocker_id is not None:
                continue
            for owner_id in issue.dependency_owner_ids:
                proposed = any(m.recipient_id == owner_id and m.issue_key == issue.key and m.kind == "dependency_followup" for m in decision.messages)
                existing_request = db.scalar(select(AutomationAction.id).where(
                    AutomationAction.blocker_id == issue.blocker_id, AutomationAction.employee_id == owner_id,
                    AutomationAction.action_type == AutomationActionType.BLOCKER_OWNER_REQUEST,
                    AutomationAction.status.in_([AutomationActionStatus.PENDING, AutomationActionStatus.DELIVERED])).limit(1)) if issue.blocker_id else None
                require(proposed or existing_request is not None, "Known dependency owner is missing its follow-up request")

    @staticmethod
    def apply(db, message, employee, run, decision):
        now = datetime.now(timezone.utc)
        run.today_summary, run.completed_summary, run.expected_outcome = decision.today_summary, decision.completed_summary, decision.expected_outcome
        run.analysis_type = AgentAnalysisType.BLOCKER if any(i.operation == "report_blocker" for i in decision.issues) else AgentAnalysisType.UPDATE
        active_run = MicrosoftService.active_run(db)
        is_run_participant = bool(active_run and str(employee.id) in set(active_run.target_employee_ids or []))
        if (employee.is_managed or is_run_participant) and any([decision.today_summary, decision.completed_summary, decision.expected_outcome, decision.explicitly_no_blockers]):
            day = (message.external_created_at or message.created_at).astimezone(ZoneInfo(get_settings().manager_timezone)).date()
            update = db.scalar(select(DailyUpdate).where(DailyUpdate.employee_id == employee.id, DailyUpdate.update_date == day))
            previous = None if update is None else {"today_summary": update.today_summary, "expected_outcome": update.expected_outcome,
                "completed_summary": update.completed_summary, "blocker_summary": update.blocker_summary}
            if update is None:
                update = DailyUpdate(employee_id=employee.id, update_date=day)
                db.add(update)
            for field in ("today_summary", "completed_summary", "expected_outcome"):
                value = getattr(decision, field)
                if value is not None:
                    setattr(update, field, value)
            reports = [i.description for i in decision.issues if i.operation == "report_blocker"]
            if reports or decision.explicitly_no_blockers:
                update.blocker_summary = "; ".join(reports) or None
            update.raw_message = message.content
            db.flush()
            current = {"today_summary": update.today_summary, "expected_outcome": update.expected_outcome,
                "completed_summary": update.completed_summary, "blocker_summary": update.blocker_summary}
            if current != previous:
                MemoryService.record_transition(db, event_type=ActivityEventType.DAILY_UPDATE_CREATED if previous is None else ActivityEventType.DAILY_UPDATE_CHANGED,
                    entity_type="daily_update", entity_id=update.id, previous=previous, current=current, subject_employee_id=employee.id)
        applied = {}
        for promised in decision.commitments:
            existing = db.scalar(select(Commitment).where(
                Commitment.employee_id == employee.id,
                Commitment.blocker_id.is_(None),
                Commitment.task_id == promised.task_id,
                Commitment.deadline == promised.deadline,
                func.lower(Commitment.description) == promised.description.casefold(),
                Commitment.status == CommitmentStatus.OPEN,
            ))
            if existing is None:
                existing = CommitmentService.create(db, CommitmentCreate(
                    employee_id=employee.id,
                    task_id=promised.task_id,
                    description=promised.description,
                    deadline=promised.deadline,
                    source_message_id=message.id,
                    confidence=decision.confidence,
                ), commit=False)
            run.commitment_id, run.eta_deadline = existing.id, existing.deadline
        for issue in decision.issues:
            blocker = db.get(Blocker, issue.blocker_id) if issue.blocker_id else None
            if issue.operation == "report_blocker" and blocker is None:
                # Exact duplicate facts reuse the record; semantic matching must be
                # an explicit existing ID selected by the decision, never a broad heuristic.
                candidates = list(db.scalars(select(Blocker).where(Blocker.blocked_employee_id == employee.id,
                    Blocker.status == BlockerStatus.OPEN, func.lower(Blocker.description) == issue.description.casefold())))
                blocker = next((b for b in candidates if set(b.dependency_owner_ids) == set(issue.dependency_owner_ids)), None)
                if blocker is None:
                    blocker = BlockerService.create(db, BlockerCreate(blocked_employee_id=employee.id,
                        task_id=issue.task_id, description=issue.description, dependency_owner_ids=issue.dependency_owner_ids), commit=False)
            elif issue.operation == "set_owners":
                blocker = BlockerService.update(db, blocker.id, BlockerUpdate(dependency_owner_ids=issue.dependency_owner_ids), commit=False)
            elif issue.operation == "eta":
                existing = db.scalar(select(Commitment).where(Commitment.blocker_id == blocker.id,
                    Commitment.employee_id == employee.id, Commitment.status == CommitmentStatus.OPEN))
                missed = list(db.scalars(select(Commitment).where(Commitment.blocker_id == blocker.id,
                    Commitment.employee_id == employee.id, Commitment.status == CommitmentStatus.MISSED)))
                if existing is None and missed:
                    if len(missed) != 1 or not issue.missed_reason:
                        raise RuleViolationError("Revising a missed promise requires the specific promise and delay reason")
                    existing = CommitmentService.revise(db, missed[0].id, CommitmentRevisionCreate(
                        description=missed[0].description, deadline=issue.deadline,
                        missed_reason=issue.missed_reason, source_message_id=message.id,
                        confidence=decision.confidence), commit=False)
                elif existing is None:
                    existing = CommitmentService.create(db, CommitmentCreate(employee_id=employee.id,
                        blocker_id=blocker.id, description=blocker.description, deadline=issue.deadline,
                        source_message_id=message.id, confidence=decision.confidence), commit=False)
                elif existing.source_message_id is None:
                    existing.source_message_id = message.id
                    existing.confidence = decision.confidence
                run.commitment_id, run.eta_deadline = existing.id, issue.deadline
            elif issue.operation == "delivered":
                contribution = next((x for x in blocker.dependencies if x.employee_id == employee.id and x.is_active), None)
                if contribution:
                    contribution.resolved_at = now
                for commitment in db.scalars(select(Commitment).where(Commitment.blocker_id == blocker.id,
                    Commitment.employee_id == employee.id, Commitment.status == CommitmentStatus.OPEN)):
                    CommitmentService.complete(db, commitment.id, commit=False)
                MemoryService.record_transition(db, event_type=ActivityEventType.BLOCKER_STATUS_CHANGED,
                    entity_type="blocker", entity_id=blocker.id, previous={"owner_delivered": False},
                    current={"owner_delivered": True, "owner_id": employee.id}, subject_employee_id=blocker.blocked_employee_id,
                    actor_employee_id=employee.id, reason="Dependency owner confirmed delivery")
                if not blocker.dependencies or all(x.resolved_at for x in blocker.dependencies if x.is_active):
                    BlockerService.update(db, blocker.id, BlockerUpdate(status=BlockerStatus.RESOLVED), commit=False)
            elif issue.operation == "complete_task":
                task = db.get(Task, issue.task_id)
                previous = {"status": task.status}
                task.status, task.completed_at = TaskStatus.DONE, now
                MemoryService.record_transition(db, event_type=ActivityEventType.TASK_STATUS_CHANGED,
                    entity_type="task", entity_id=task.id, previous=previous, current={"status": task.status},
                    subject_employee_id=employee.id, task_id=task.id)
            if blocker:
                applied[issue.key] = str(blocker.id)
                run.blocker_id, run.blocker_description = blocker.id, blocker.description
                run.dependency_owner_id = blocker.dependency_owner_id
        for question_id in decision.answered_question_ids:
            question = db.get(ConversationQuestion, question_id)
            question.answered_at, question.answered_by_message_id = now, message.id
            question.status = "answered"
        state = db.get(ConversationState, message.conversation_id)
        if state is None:
            state = ConversationState(conversation_id=message.conversation_id)
            db.add(state)
        state.last_user_message_id = message.id
        state.active_blocker_id = uuid.UUID(next(iter(applied.values()))) if len(applied) == 1 else None
        state.active_task_id = decision.issues[0].task_id if len(decision.issues) == 1 else None
        db.flush()
        return applied

    @staticmethod
    def resolve_existing_issue_ids(db, employee, decision) -> dict[str, str]:
        """Resolve exact open duplicates read-only before any delivery begins."""

        resolved = {
            item.key: str(item.blocker_id)
            for item in decision.issues if item.blocker_id is not None
        }
        for issue in decision.issues:
            if issue.operation != "report_blocker" or issue.blocker_id is not None:
                continue
            candidates = list(db.scalars(select(Blocker).where(
                Blocker.blocked_employee_id == employee.id,
                Blocker.status == BlockerStatus.OPEN,
                func.lower(Blocker.description) == issue.description.casefold(),
            )))
            blocker = next((item for item in candidates
                            if set(item.dependency_owner_ids) == set(issue.dependency_owner_ids)), None)
            if blocker is not None:
                resolved[issue.key] = str(blocker.id)
        return resolved

    @staticmethod
    def send(db, message, employee, run, decision, applied):
        from app.agents.management_agent import ManagementAgent
        for index, outgoing in enumerate(decision.messages):
            recipient = db.get(Employee, outgoing.recipient_id)
            blocker = db.get(Blocker, applied[outgoing.issue_key]) if outgoing.issue_key in applied else None
            action_type = AutomationActionType.BLOCKER_OWNER_REQUEST if outgoing.kind == "dependency_followup" else AutomationActionType.BLOCKER_SOURCE_ACKNOWLEDGEMENT
            if outgoing.kind == "clarification":
                action_type = AutomationActionType.BLOCKER_OWNER_CLARIFICATION
            key = "decision:{}:{}".format(run.id, index)
            issue = next((item for item in decision.issues
                          if item.key == outgoing.issue_key), None)
            if blocker and issue and issue.operation in {"report_blocker", "set_owners"}:
                # Exact duplicate reports must reuse the first delivery audit
                # row. This check works even when the first send preceded issue
                # creation and therefore used a decision-scoped key.
                prior = db.scalar(select(AutomationAction).where(
                    AutomationAction.blocker_id == blocker.id,
                    AutomationAction.employee_id == recipient.id,
                    AutomationAction.action_type == action_type,
                    AutomationAction.status.in_([
                        AutomationActionStatus.PENDING,
                        AutomationActionStatus.DELIVERED,
                        AutomationActionStatus.SKIPPED,
                    ]),
                ).order_by(AutomationAction.created_at).limit(1))
                if prior is not None:
                    key = prior.idempotency_key
                elif outgoing.kind == "dependency_followup":
                    key = "issue-owner-request:{}:{}".format(blocker.id, recipient.id)
            content = outgoing.text
            for person in db.scalars(select(Employee).where(Employee.is_active.is_(True))):
                content = re.sub(r"(?<!\w)" + re.escape(person.name) + r"(?!\w)", MicrosoftService.first_name(person.name), content, flags=re.I)
            sent = ManagementAgent._send_blocker_message_once(db, action_type=action_type, idempotency_key=key,
                employee=recipient, blocker=blocker, content=MicrosoftService.follow_up_message_for(recipient.name, content))
            if sent is None:
                action = db.scalar(select(AutomationAction).where(AutomationAction.idempotency_key == key))
                if action and action.status == AutomationActionStatus.PENDING:
                    raise RuleViolationError("Delivery is uncertain; inspect the reserved send before retrying")
                sent = db.get(Message, action.message_id) if action and action.message_id else None
            if sent is not None:
                if recipient.id == employee.id:
                    run.source_reply_message_id = sent.id
                else:
                    run.dependency_message_id = sent.id
                if outgoing.awaiting_field and not db.scalar(select(ConversationQuestion.id).where(ConversationQuestion.message_id == sent.id)):
                    db.add(ConversationQuestion(conversation_id=sent.conversation_id, message_id=sent.id,
                        blocker_id=blocker.id if blocker else None,
                        task_id=blocker.task_id if blocker else next((i.task_id for i in decision.issues if i.key == outgoing.issue_key), None),
                        awaiting_field=outgoing.awaiting_field,
                        expected_answer_type=outgoing.awaiting_field,
                        asked_to_employee_id=recipient.id,
                        status="awaiting_response"))
                db.commit()

    @staticmethod
    def link_delivery_records(db, run, decision, applied):
        """Attach pre-state delivery audit rows to the issues just created."""

        for index, outgoing in enumerate(decision.messages):
            blocker_id = applied.get(outgoing.issue_key) if outgoing.issue_key else None
            if blocker_id is None:
                continue
            issue = next((item for item in decision.issues if item.key == outgoing.issue_key), None)
            if (outgoing.kind == "dependency_followup" and issue is not None
                    and issue.blocker_id is not None):
                key = "issue-owner-request:{}:{}".format(blocker_id, outgoing.recipient_id)
            else:
                key = "decision:{}:{}".format(run.id, index)
            action = db.scalar(select(AutomationAction).where(
                AutomationAction.idempotency_key == key
            ))
            if action is None:
                continue
            action.blocker_id = uuid.UUID(str(blocker_id))
            if action.message_id is not None:
                question = db.scalar(select(ConversationQuestion).where(
                    ConversationQuestion.message_id == action.message_id
                ))
                if question is not None:
                    question.blocker_id = uuid.UUID(str(blocker_id))
                    blocker = db.get(Blocker, uuid.UUID(str(blocker_id)))
                    if blocker is not None and question.task_id is None:
                        question.task_id = blocker.task_id
