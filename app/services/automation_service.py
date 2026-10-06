"""Deterministic daily manager automation with durable idempotency records."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from html import escape as html_escape
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.automation_action import AutomationAction
from app.models.agent_run import AgentRun
from app.models.blocker import Blocker
from app.models.commitment import Commitment
from app.models.daily_update import DailyUpdate
from app.models.employee import Employee
from app.models.enums import (
    AutomationActionStatus,
    AutomationActionType,
    AgentRunStatus,
    BlockerSeverity,
    BlockerStatus,
    CommitmentStatus,
    EscalationStatus,
    EscalationType,
    MicrosoftSubscriptionStatus,
    MessageDirection,
)
from app.models.escalation import Escalation
from app.models.microsoft_subscription import MicrosoftTeamsSubscription
from app.models.project import Project
from app.models.task import Task
from app.models.message import Message
from app.models.intelligence import ManagementDecision, ManagementRisk
from app.schemas.escalation import EscalationCreate
from app.services.commitment_service import CommitmentService
from app.services.errors import DomainError
from app.services.escalation_service import EscalationService
from app.services.microsoft_service import (
    SUBSCRIPTION_RENEWAL_LEAD_MINUTES,
    MicrosoftGraphClient,
    MicrosoftService,
)
from app.services.memory_consolidation_service import MemoryConsolidationService
from app.services.followup_intelligence_service import FollowUpIntelligenceService
from app.services.management_intelligence_service import ManagementIntelligenceService
from app.services.daily_brief_service import DailyBriefService
from app.services.proactive_action_service import ProactiveActionService
from app.services.response_recovery_service import ResponseRecoveryService


class DailyAutomationService:
    """Runs the approved V1 automation actions once, safely and repeatably."""

    @staticmethod
    def run_cycle(
        db: Session,
        *,
        now: Optional[datetime] = None,
        force: bool = False,
        include_later_day_actions: bool = False,
    ) -> dict[str, int]:
        local_now = DailyAutomationService._local_now(now)
        result = {"checkins": 0, "followups": 0, "missed": 0, "digests": 0, "escalations": 0, "listeners": 0, "intelligence": 0, "recovered_replies": 0}
        result["recovered_replies"] = ResponseRecoveryService.process_due(
            db, now=local_now.astimezone(timezone.utc)
        )
        result["listeners"] = DailyAutomationService.renew_listener_if_due(db, local_now)
        if force or DailyAutomationService._is_within_schedule_window(
            local_now, get_settings().daily_checkin_time
        ):
            result["checkins"] = DailyAutomationService.send_daily_checkins(db, local_now)
        if (force and include_later_day_actions) or DailyAutomationService._is_within_schedule_window(
            local_now, get_settings().daily_followup_time
        ):
            result["followups"] = DailyAutomationService.send_no_response_followups(db, local_now)
        result["missed"] = DailyAutomationService.monitor_commitments(db, local_now)
        intelligence = ManagementIntelligenceService.run(db, as_of=local_now.astimezone(timezone.utc))
        result["intelligence"] = intelligence.decisions_created
        result["followups"] += ProactiveActionService.execute_validated(db)
        result["escalations"] = DailyAutomationService.escalate_management_risks(db, local_now)
        # Memory is consolidated off the Teams/webhook path during its own
        # scheduled window. Its database jobs make a retry harmless.
        MemoryConsolidationService.run_if_due(db, local_now)
        if (force and include_later_day_actions) or DailyAutomationService._is_due(local_now, get_settings().daily_digest_time):
            result["digests"] = DailyAutomationService.send_daily_digest(db, local_now)
        return result

    @staticmethod
    def renew_listener_if_due(db: Session, local_now: datetime) -> int:
        run = MicrosoftService.active_run(db)
        if run is None:
            return 0
        now_utc = local_now.astimezone(timezone.utc)
        next_expiry = db.scalar(
            select(func.min(MicrosoftTeamsSubscription.expires_at)).where(
                MicrosoftTeamsSubscription.automation_run_id == run.id,
                MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
            )
        )
        active_listener_count = db.scalar(
            select(func.count(func.distinct(MicrosoftTeamsSubscription.conversation_id))).where(
                MicrosoftTeamsSubscription.automation_run_id == run.id,
                MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                MicrosoftTeamsSubscription.expires_at > now_utc + timedelta(minutes=2),
            )
        ) or 0
        # Renew near expiry, and repair immediately whenever any run target has
        # lost its listener. Previously one failed renewal could remain failed
        # while the other healthy subscriptions delayed the next repair.
        coverage_incomplete = active_listener_count < len(run.target_employee_ids or [])
        if (
            not coverage_incomplete
            and next_expiry is not None
            and next_expiry > now_utc + timedelta(minutes=SUBSCRIPTION_RENEWAL_LEAD_MINUTES)
        ):
            return 0
        result = MicrosoftService.renew_listener(db)
        return result.renewed

    @staticmethod
    def send_daily_checkins(db: Session, local_now: datetime) -> int:
        sent = 0
        for employee in DailyAutomationService._managed_employees(db):
            key = DailyAutomationService._daily_checkin_key(db, local_now.date().isoformat(), employee.id)
            message = MicrosoftService.follow_up_message_for(
                employee.name,
                "What are you working on, what’s the expected outcome, and is anything blocking you? "
                "If yes, who can unblock it?",
            )
            if DailyAutomationService._send_once(
                db, AutomationActionType.DAILY_CHECKIN, key, employee, message, local_now
            ):
                sent += 1
        return sent

    @staticmethod
    def send_no_response_followups(db: Session, local_now: datetime) -> int:
        sent = 0
        responded_ids = set(
            db.scalars(select(DailyUpdate.employee_id).where(DailyUpdate.update_date == local_now.date()))
        )
        for employee in DailyAutomationService._managed_employees(db):
            if employee.id in responded_ids:
                continue
            checkin_key = DailyAutomationService._daily_checkin_key(
                db, local_now.date().isoformat(), employee.id
            )
            checkin = db.scalar(
                select(AutomationAction).where(AutomationAction.idempotency_key == checkin_key)
            )
            if checkin is None or checkin.status != AutomationActionStatus.DELIVERED:
                continue
            # A received reply counts even while analysis is pending/failed or
            # the update is incomplete. Never tell that person they did not reply.
            received = db.scalar(select(Message.id).where(
                Message.employee_id == employee.id,
                Message.direction == MessageDirection.INBOUND,
                func.coalesce(Message.external_created_at, Message.created_at) >= checkin.executed_at,
            ).limit(1))
            if received is not None:
                continue
            try:
                followup_time = time.fromisoformat(get_settings().daily_followup_time)
                followup_at = datetime.combine(local_now.date(), followup_time, tzinfo=local_now.tzinfo)
            except ValueError:
                continue
            if checkin.executed_at.astimezone(local_now.tzinfo) >= followup_at:
                continue
            key = "daily-followup:{}:{}".format(local_now.date().isoformat(), employee.id)
            message = MicrosoftService.follow_up_message_for(
                employee.name,
                "Haven’t received your update yet. Please send today’s work, expected outcome, and any blockers.",
            )
            if DailyAutomationService._send_once(
                db, AutomationActionType.NO_RESPONSE_FOLLOWUP, key, employee, message, local_now
            ):
                sent += 1
        return sent

    @staticmethod
    def monitor_commitments(db: Session, local_now: datetime) -> int:
        missed = CommitmentService.mark_overdue(db, local_now.astimezone(timezone.utc))
        useful_followups = {
            item["id"] for item in FollowUpIntelligenceService.candidates(
                db, as_of=local_now.astimezone(timezone.utc)
            ) if item["kind"] == "overdue_commitment"
        }
        followups = 0
        for commitment in db.scalars(
            select(Commitment).where(Commitment.status == CommitmentStatus.MISSED)
        ):
            if commitment.id not in useful_followups:
                continue
            employee = db.get(Employee, commitment.employee_id)
            if employee is None:
                continue
            key = "missed-commitment:{}".format(commitment.id)
            message = MicrosoftService.follow_up_message_for(
                employee.name,
                "Your commitment due {} has passed. What caused the delay, and what’s the revised ETA?".format(
                    DailyAutomationService._format_deadline(commitment.deadline)
                ),
            )
            if DailyAutomationService._send_once(
                db,
                AutomationActionType.MISSED_COMMITMENT_FOLLOWUP,
                key,
                employee,
                message,
                local_now,
                commitment=commitment,
            ):
                followups += 1
        return len(missed) + followups

    @staticmethod
    def escalate_management_risks(db: Session, local_now: datetime) -> int:
        """Create approval-required escalation candidates only for urgent, evidenced risks."""
        created = 0
        urgent_risks = list(db.scalars(select(ManagementRisk).where(
            ManagementRisk.status == "active",
            ManagementRisk.severity == "urgent",
            ManagementRisk.source_entity_type == "blocker",
        )))
        for risk in urgent_risks:
            decision = db.scalar(select(ManagementDecision).where(
                ManagementDecision.trigger_id == risk.id,
                ManagementDecision.action == "REQUEST_MANAGER_APPROVAL",
                ManagementDecision.status == "validated",
            ).order_by(ManagementDecision.decided_at.desc()).limit(1))
            blocker = db.get(Blocker, risk.source_entity_id)
            if decision is None or blocker is None:
                continue
            reason = "Management attention requested: " + risk.summary
            exists = db.scalar(
                select(Escalation.id).where(
                    Escalation.status != EscalationStatus.RESOLVED,
                    Escalation.escalation_type == EscalationType.BLOCKER,
                    Escalation.employee_id == blocker.blocked_employee_id,
                    Escalation.reason == reason,
                )
            )
            if exists is None:
                EscalationService.create(
                    db,
                    EscalationCreate(
                        employee_id=blocker.blocked_employee_id,
                        escalation_type=EscalationType.BLOCKER,
                        severity=blocker.severity,
                        reason=reason,
                        context="{} Evidence: {}".format(risk.reason, ", ".join(risk.evidence)),
                        requires_yash_approval=True,
                    ),
                )
                created += 1
        notified = 0
        for escalation in db.scalars(
            select(Escalation).where(
                Escalation.status.in_([EscalationStatus.OPEN, EscalationStatus.PENDING_APPROVAL]),
                or_(
                    Escalation.requires_yash_approval.is_(True),
                    Escalation.severity == BlockerSeverity.CRITICAL,
                    Escalation.escalation_type == EscalationType.MISSED_COMMITMENT,
                ),
            )
        ):
            target = DailyAutomationService._yash_notification_target(db)
            if target is None:
                continue
            key = "escalation:{}".format(escalation.id)
            message = MicrosoftService.follow_up_message_for(
                target.name,
                "Escalation: {}. {}".format(escalation.escalation_type.value.replace("_", " "), escalation.reason),
            )
            if DailyAutomationService._send_once(
                db,
                AutomationActionType.ESCALATION_NOTIFICATION,
                key,
                target,
                message,
                local_now,
                escalation=escalation,
            ):
                notified += 1
        return created + notified

    @staticmethod
    def send_daily_digest(db: Session, local_now: datetime) -> int:
        target = DailyAutomationService._yash_notification_target(db)
        if target is None:
            return 0
        content = DailyAutomationService._daily_digest_content(db, local_now)
        key = "daily-digest:{}".format(local_now.date().isoformat())
        return int(DailyAutomationService._send_once(
            db,
            AutomationActionType.DAILY_DIGEST,
            key,
            target,
            MicrosoftService.follow_up_message_for(target.name, content),
            local_now,
        ))

    @staticmethod
    def send_daily_digest_email(db: Session) -> str:
        """Send the manager's five-section HTML brief to the connected mailbox."""

        connection = MicrosoftService.get_connection(db)
        local_now = DailyAutomationService._local_now(None)
        digest = DailyAutomationService._daily_digest_content(db, local_now)
        MicrosoftGraphClient(db, connection).send_mail(
            connection.user_principal_name,
            "Daily manager brief — {}".format(local_now.strftime("%d %b %Y")),
            DailyAutomationService._daily_digest_email_html(digest, local_now),
            content_type="HTML",
        )
        return connection.user_principal_name

    @staticmethod
    def _daily_digest_email_html(digest: str, local_now: datetime) -> str:
        """Turn the durable digest into a short, five-section manager email."""

        parsed: dict[str, list[str]] = {}
        active_section: str | None = None
        response_line = "No managed-team response data was recorded."
        for raw_line in digest.splitlines():
            line = raw_line.strip()
            if not line or line == "Daily manager digest":
                continue
            if line.startswith("Responded:"):
                response_line = "Team response: {}".format(line.removeprefix("Responded:").strip())
                continue
            if line.endswith(":") and not line.startswith("-"):
                active_section = line[:-1]
                parsed.setdefault(active_section, [])
                continue
            if line.startswith("- ") and active_section:
                value = line[2:].strip()
                if value and value != "None":
                    parsed[active_section].append(value)

        groups = [
            ("Overview", [("Today", [response_line])]),
            ("Work updates", [
                ("Completed", parsed.get("Completed", [])),
                ("In progress", parsed.get("Working on", [])),
                ("Expected outcomes", parsed.get("Expected outcomes", [])),
            ]),
            ("Blockers & commitments", [
                ("Blockers", parsed.get("Blocked", [])),
                ("Due today", parsed.get("Commitments due today", [])),
                ("Due soon", parsed.get("Commitments due soon", [])),
                ("Missed", parsed.get("Missed commitments", [])),
            ]),
            ("Agent handling", [("Actions", parsed.get("Agent handling today", []))]),
            ("Manager attention", [
                ("Needs approval", parsed.get("Needs approval", [])),
                ("Open escalations", parsed.get("Open escalations", [])),
                ("Important changes", parsed.get("Important changes since yesterday", [])),
                ("Needs attention", parsed.get("Needs your attention", [])),
            ]),
        ]

        def render_group(title: str, subsections: list[tuple[str, list[str]]]) -> str:
            content = []
            for subtitle, values in subsections:
                if not values:
                    continue
                items = "".join("<li>{}</li>".format(html_escape(value)) for value in values)
                content.append(
                    '<p style="margin:14px 0 6px;font-weight:600;color:#252b3a">{}</p><ul '
                    'style="margin:0;padding-left:20px;color:#4c5565">{}</ul>'.format(
                        html_escape(subtitle), items
                    )
                )
            if not content:
                content.append('<p style="margin:0;color:#6b7280">No updates.</p>')
            return (
                '<section style="padding:20px 0;border-top:1px solid #e7e9ee">'
                '<h2 style="margin:0;font-size:16px;color:#172033">{}</h2>{}</section>'
            ).format(html_escape(title), "".join(content))

        sections = "".join(render_group(title, subsections) for title, subsections in groups)
        report_date = local_now.strftime("%A, %d %B %Y")
        return (
            """<!doctype html><html><body style="margin:0;background:#f5f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#172033"><main style="max-width:680px;margin:0 auto;padding:28px 16px"><article style="background:#fff;border:1px solid #e7e9ee;border-radius:14px;padding:28px"><p style="margin:0 0 8px;color:#4169a8;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">Personal Agent</p><h1 style="margin:0;font-size:24px">Daily manager brief</h1><p style="margin:8px 0 24px;color:#6b7280">{}</p>{}<footer style="padding-top:18px;color:#6b7280;font-size:12px">Sent by Yash's Agent.</footer></article></main></body></html>"""
        ).format(html_escape(report_date), sections)

    @staticmethod
    def _daily_digest_content(db: Session, local_now: datetime) -> str:
        """Build the shared plain-text digest used by Teams and email."""

        managed = DailyAutomationService._managed_team_employees(db)
        managed_ids = {employee.id for employee in managed}
        updates = list(
            db.scalars(
                select(DailyUpdate).where(
                    DailyUpdate.update_date == local_now.date(),
                    DailyUpdate.employee_id.in_(managed_ids),
                )
            )
        ) if managed_ids else []
        responded = {update.employee_id for update in updates}
        blockers = list(
            db.scalars(
                select(Blocker).where(
                    Blocker.status == BlockerStatus.OPEN,
                    Blocker.blocked_employee_id.in_(managed_ids),
                )
            )
        ) if managed_ids else []
        open_commitments = list(
            db.scalars(
                select(Commitment).where(
                    Commitment.status == CommitmentStatus.OPEN,
                    Commitment.employee_id.in_(managed_ids),
                )
            )
        ) if managed_ids else []
        today = local_now.date()
        due_today = [
            commitment
            for commitment in open_commitments
            if commitment.deadline.astimezone(local_now.tzinfo).date() == today
        ]
        due_soon_cutoff = local_now.astimezone(timezone.utc) + timedelta(
            hours=get_settings().digest_due_soon_hours
        )
        due_soon = [
            commitment
            for commitment in open_commitments
            if commitment.deadline.astimezone(timezone.utc) > local_now.astimezone(timezone.utc)
            and commitment.deadline.astimezone(timezone.utc) <= due_soon_cutoff
            and commitment not in due_today
        ]
        missed = list(
            db.scalars(
                select(Commitment).where(
                    Commitment.status == CommitmentStatus.MISSED,
                    Commitment.employee_id.in_(managed_ids),
                )
            )
        ) if managed_ids else []
        managed_project_ids = select(Project.id).where(Project.owner_id.in_(managed_ids))
        managed_task_ids = select(Task.id).where(Task.owner_id.in_(managed_ids))
        escalation_scope = or_(
            Escalation.employee_id.in_(managed_ids),
            Escalation.project_id.in_(managed_project_ids),
            Escalation.task_id.in_(managed_task_ids),
        )
        pending_approvals = list(
            db.scalars(
                select(Escalation).where(
                    escalation_scope,
                    Escalation.status == EscalationStatus.PENDING_APPROVAL,
                )
            )
        ) if managed_ids else []
        open_escalations = list(
            db.scalars(
                select(Escalation).where(
                    escalation_scope,
                    Escalation.status.in_([EscalationStatus.OPEN, EscalationStatus.ACKNOWLEDGED]),
                )
            )
        ) if managed_ids else []
        # A relevant blocker can depend on someone outside the managed team.
        blocker_commitments = list(db.scalars(select(Commitment).where(
            Commitment.blocker_id.in_([blocker.id for blocker in blockers]),
            Commitment.status == CommitmentStatus.OPEN))) if blockers else []
        day_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        agent_runs = list(db.scalars(
            select(AgentRun).where(
                AgentRun.source_employee_id.in_(managed_ids),
                AgentRun.processed_at >= day_start,
                AgentRun.processed_at <= local_now,
            ).order_by(AgentRun.processed_at, AgentRun.id)
        )) if managed_ids else []

        def employee_name(employee_id: object) -> str:
            employee = db.get(Employee, employee_id)
            return MicrosoftService.first_name(employee.name) if employee is not None else "Unknown"

        def section(title: str, values: list[str]) -> list[str]:
            return ["", title + ":"] + (["- " + value for value in values] or ["- None"])

        def agent_handling(run: AgentRun) -> str:
            """Describe durable agent outcomes, never hidden model reasoning."""

            source = employee_name(run.source_employee_id)
            if run.status == AgentRunStatus.FAILED:
                return f"{source}: could not complete the response and needs review."
            if run.status == AgentRunStatus.SKIPPED:
                return f"{source}: recorded a non-actionable reply; no follow-up was needed."

            actions: list[str] = []
            blocker = db.get(Blocker, run.blocker_id) if run.blocker_id else None
            if blocker is not None:
                actions.append("recorded blocker: {}".format(blocker.description))
            if run.commitment_id:
                actions.append("recorded a commitment")

            proposed_messages = (
                run.decision_json.get("messages", []) if isinstance(run.decision_json, dict) else []
            )
            message_kinds = {
                item.get("kind") for item in proposed_messages if isinstance(item, dict)
            }
            if "dependency_followup" in message_kinds or run.dependency_message_id:
                owners = (
                    ", ".join(employee_name(owner_id) for owner_id in blocker.dependency_owner_ids)
                    if blocker is not None else "the dependency owner"
                )
                actions.append("asked {} for an ETA".format(owners))
            elif "status_update" in message_kinds:
                actions.append("sent the affected person a status update")
            if run.source_reply_message_id:
                actions.append("acknowledged the update")
            if run.needs_yash_review:
                actions.append("flagged it for your review")
            if not actions:
                actions.append("recorded the update; no follow-up was needed")
            return "{}: {}.".format(source, "; ".join(actions))

        lines = ["Daily manager digest", "", "Responded: {}/{}".format(len(responded), len(managed))]
        lines += section(
            "Completed",
            ["{}: {}".format(employee_name(update.employee_id), update.completed_summary) for update in updates if update.completed_summary],
        )
        lines += section(
            "Working on",
            ["{}: {}".format(employee_name(update.employee_id), update.today_summary or "Not stated") for update in updates],
        )
        lines += section(
            "Expected outcomes",
            ["{}: {}".format(employee_name(update.employee_id), update.expected_outcome) for update in updates if update.expected_outcome],
        )
        blocker_values = []
        for blocker in blockers:
            owner = ", ".join(employee_name(owner_id) for owner_id in blocker.dependency_owner_ids) or "Unassigned"
            detail = "{} — {} (dependency: {}; severity: {})".format(
                employee_name(blocker.blocked_employee_id),
                blocker.description,
                owner,
                blocker.severity.value,
            )
            for linked in blocker_commitments:
                if linked.blocker_id == blocker.id:
                    detail += "; {} ETA: {}".format(employee_name(linked.employee_id), DailyAutomationService._format_deadline(linked.deadline))
            blocker_values.append(detail)
        lines += section("Blocked", blocker_values)
        lines += section(
            "Commitments due today",
            ["{}: {} — {}".format(employee_name(item.employee_id), item.description, DailyAutomationService._format_deadline(item.deadline)) for item in due_today],
        )
        lines += section(
            "Commitments due soon",
            ["{}: {} — {}".format(employee_name(item.employee_id), item.description, DailyAutomationService._format_deadline(item.deadline)) for item in due_soon],
        )
        lines += section(
            "Missed commitments",
            ["{}: {}".format(employee_name(item.employee_id), item.description) for item in missed],
        )
        lines += section(
            "Needs approval",
            ["{}: {}".format(item.escalation_type.value.replace("_", " "), item.reason) for item in pending_approvals],
        )
        lines += section(
            "Open escalations",
            ["{}: {}".format(item.escalation_type.value.replace("_", " "), item.reason) for item in open_escalations],
        )
        handling_lines = [agent_handling(run) for run in agent_runs]
        if len(handling_lines) > 20:
            handling_lines = handling_lines[:20] + [
                "{} additional agent response(s) are available in the dashboard.".format(
                    len(agent_runs) - 20
                )
            ]
        lines += section("Agent handling today", handling_lines)
        brief = DailyBriefService.build(db, as_of=local_now)
        lines += section("Important changes since yesterday", brief.important_changes)
        lines += section("Needs your attention", brief.needs_attention)
        lines += section("No action required", brief.no_action_required)
        return "\n".join(lines)

    @staticmethod
    def list_daily_digests(db: Session, *, limit: int = 30) -> list[AutomationAction]:
        """Retrieve exactly the digest messages that were actually persisted/sent."""

        return list(
            db.scalars(
                select(AutomationAction)
                .where(
                    AutomationAction.action_type == AutomationActionType.DAILY_DIGEST,
                    AutomationAction.status == AutomationActionStatus.DELIVERED,
                    AutomationAction.message_id.is_not(None),
                )
                .order_by(AutomationAction.executed_at.desc())
                .limit(limit)
            )
        )

    @staticmethod
    def _send_once(
        db: Session,
        action_type: AutomationActionType,
        key: str,
        employee: Employee,
        content: str,
        local_now: datetime,
        *,
        commitment: Optional[Commitment] = None,
        escalation: Optional[Escalation] = None,
    ) -> bool:
        action = db.scalar(select(AutomationAction).where(AutomationAction.idempotency_key == key))
        if action is not None and action.status in (AutomationActionStatus.DELIVERED, AutomationActionStatus.SKIPPED):
            return False
        if action is None:
            action = AutomationAction(
                action_type=action_type,
                status=AutomationActionStatus.FAILED,
                idempotency_key=key,
                employee_id=employee.id,
                commitment_id=commitment.id if commitment else None,
                escalation_id=escalation.id if escalation else None,
                executed_at=local_now.astimezone(timezone.utc),
            )
            db.add(action)
            db.commit()
        try:
            message = MicrosoftService.send_management_message(db, employee, content)
        except DomainError as exc:
            action.status = AutomationActionStatus.FAILED
            action.detail = exc.detail
            action.executed_at = datetime.now(timezone.utc)
            db.commit()
            return False
        action.status = AutomationActionStatus.DELIVERED
        action.message_id = message.id
        action.detail = None
        action.executed_at = datetime.now(timezone.utc)
        db.commit()
        return True

    @staticmethod
    def _managed_employees(db: Session) -> list[Employee]:
        employees = [
            employee for employee in DailyAutomationService._managed_team_employees(db)
            if employee.teams_user_id is not None
        ]
        run = MicrosoftService.active_run(db)
        if run is None:
            return []
        allowed_ids = set(run.target_employee_ids or [])
        return [employee for employee in employees if str(employee.id) in allowed_ids]

    @staticmethod
    def _managed_team_employees(db: Session) -> list[Employee]:
        return list(db.scalars(select(Employee).where(
            Employee.is_active.is_(True), Employee.is_managed.is_(True)
        ).order_by(Employee.name)))

    @staticmethod
    def _daily_checkin_key(db: Session, checkin_day: str, employee_id: object) -> str:
        """Keep check-ins idempotent per day and per sending Microsoft account."""

        connection = MicrosoftService.get_connection(db)
        return "daily-checkin:{}:{}:{}".format(
            checkin_day, employee_id, connection.microsoft_user_id
        )

    @staticmethod
    def _yash_notification_target(db: Session) -> Optional[Employee]:
        email = (get_settings().yash_notification_email or "").strip().lower()
        if not email:
            return None
        return db.scalar(select(Employee).where(Employee.email == email, Employee.is_active.is_(True)))

    @staticmethod
    def _local_now(now: Optional[datetime]) -> datetime:
        current = now or datetime.now(timezone.utc)
        return current.astimezone(ZoneInfo(get_settings().manager_timezone))

    @staticmethod
    def _is_due(local_now: datetime, configured_time: str) -> bool:
        try:
            due_time = time.fromisoformat(configured_time)
        except ValueError:
            return False
        return local_now.timetz().replace(tzinfo=None) >= due_time

    @staticmethod
    def _is_within_schedule_window(
        local_now: datetime, configured_time: str, grace_minutes: int = 10
    ) -> bool:
        """Prevent a morning check-in from being sent as a late-night catch-up."""

        try:
            scheduled_time = time.fromisoformat(configured_time)
        except ValueError:
            return False
        scheduled_at = datetime.combine(local_now.date(), scheduled_time, tzinfo=local_now.tzinfo)
        return scheduled_at <= local_now < scheduled_at + timedelta(minutes=grace_minutes)

    @staticmethod
    def _format_deadline(value: datetime) -> str:
        return value.astimezone(ZoneInfo(get_settings().manager_timezone)).strftime("%d %b, %-I:%M %p %Z")
