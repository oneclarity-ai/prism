from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.automation_action import AutomationAction
from app.models.automation_run import AutomationRun
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.enums import (
    AutomationStatus,
    AutomationActionStatus,
    AutomationActionType,
    ConversationChannel,
    ConversationType,
    MessageDeliveryStatus,
    MessageDirection,
    MicrosoftSubscriptionStatus,
    SenderType,
)
from app.models.message import Message
from app.models.microsoft_connection import MicrosoftConnection
from app.models.microsoft_oauth_state import MicrosoftOAuthState
from app.models.microsoft_subscription import MicrosoftTeamsSubscription
from app.schemas.microsoft import (
    AutomationRunRead,
    AutomationStart,
    DirectorySyncResult,
    MicrosoftStatusRead,
    SubscriptionRenewalResult,
)
from app.services.errors import ConflictError, ExternalServiceError, RuleViolationError
from app.services.memory_service import MemoryService


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
OAUTH_STATE_TTL_MINUTES = 10
# Teams chat-message subscriptions support up to three days when a lifecycle
# notification URL is supplied. Stay slightly below that boundary so clock
# skew cannot make Microsoft reject the request.
SUBSCRIPTION_LIFETIME_MINUTES = 4_200
SUBSCRIPTION_RENEWAL_LEAD_MINUTES = 360
TOKEN_REFRESH_SKEW_SECONDS = 300
SIGNATURE = "Sent by Yash's Agent"
DELEGATED_SCOPES = (
    "openid",
    "profile",
    "offline_access",
    "User.Read",
    "User.Read.All",
    "Chat.Create",
    "Chat.Read",
    "ChatMessage.Send",
    "Mail.Send",
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.quoted_parts: list[str] = []
        self.quote_depth = 0
        self.reply_id: Optional[str] = None

    def handle_starttag(self, tag, attrs) -> None:
        attributes = dict(attrs)
        if tag == "blockquote":
            self.quote_depth += 1
            self.reply_id = attributes.get("itemid") or attributes.get("data-message-id") or self.reply_id

    def handle_endtag(self, tag) -> None:
        if tag == "blockquote" and self.quote_depth:
            self.quote_depth -= 1

    def handle_data(self, data: str) -> None:
        (self.quoted_parts if self.quote_depth else self.parts).append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


class TokenCipher:
    """Encrypt Graph credentials before they are persisted in PostgreSQL."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        resolved_settings = settings or get_settings()
        if not resolved_settings.microsoft_token_encryption_key:
            raise RuleViolationError(
                "MICROSOFT_TOKEN_ENCRYPTION_KEY is required before Microsoft sign-in can be used"
            )
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise RuleViolationError(
                "Microsoft support needs the cryptography dependency. Run pip install -r requirements.txt"
            ) from exc
        try:
            self._fernet = Fernet(resolved_settings.microsoft_token_encryption_key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise RuleViolationError("MICROSOFT_TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            raise RuleViolationError("Stored Microsoft credentials cannot be decrypted") from exc


class MicrosoftGraphClient:
    """Minimal synchronous Microsoft Graph client for the delegated Yash connection."""

    def __init__(self, db: Session, connection: MicrosoftConnection) -> None:
        self.db = db
        self.connection = connection
        self.settings = get_settings()
        self.cipher = TokenCipher(self.settings)

    @staticmethod
    def require_auth_configuration(settings: Optional[Settings] = None) -> Settings:
        resolved_settings = settings or get_settings()
        required = {
            "MICROSOFT_TENANT_ID": resolved_settings.microsoft_tenant_id,
            "MICROSOFT_CLIENT_ID": resolved_settings.microsoft_client_id,
            "MICROSOFT_CLIENT_SECRET": resolved_settings.microsoft_client_secret,
            "MICROSOFT_TOKEN_ENCRYPTION_KEY": resolved_settings.microsoft_token_encryption_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuleViolationError("Microsoft setup is incomplete: " + ", ".join(missing))
        return resolved_settings

    @staticmethod
    def authorization_url(db: Session) -> str:
        settings = MicrosoftGraphClient.require_auth_configuration()
        cipher = TokenCipher(settings)
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("utf-8")).digest()
        ).rstrip(b"=").decode("ascii")
        now = datetime.now(timezone.utc)
        db.add(
            MicrosoftOAuthState(
                state_hash=hashlib.sha256(state.encode("utf-8")).hexdigest(),
                encrypted_code_verifier=cipher.encrypt(code_verifier),
                expires_at=now + timedelta(minutes=OAUTH_STATE_TTL_MINUTES),
            )
        )
        db.commit()
        params = {
            "client_id": settings.microsoft_client_id,
            "response_type": "code",
            "redirect_uri": settings.microsoft_redirect_uri,
            "response_mode": "query",
            "scope": " ".join(DELEGATED_SCOPES),
            "prompt": "select_account",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return "https://login.microsoftonline.com/{}/oauth2/v2.0/authorize?{}".format(
            settings.microsoft_tenant_id, urlencode(params)
        )

    @staticmethod
    def complete_authorization(db: Session, *, code: str, state: str) -> MicrosoftConnection:
        settings = MicrosoftGraphClient.require_auth_configuration()
        state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
        pending_state = db.scalar(
            select(MicrosoftOAuthState).where(MicrosoftOAuthState.state_hash == state_hash)
        )
        if pending_state is None or pending_state.expires_at <= datetime.now(timezone.utc):
            if pending_state is not None:
                db.delete(pending_state)
                db.commit()
            raise RuleViolationError("Microsoft sign-in has expired. Start the connection again from the dashboard")

        code_verifier = TokenCipher(settings).decrypt(pending_state.encrypted_code_verifier)
        token_data = MicrosoftGraphClient._exchange_code(settings, code, code_verifier)
        refresh_token = token_data.get("refresh_token")
        access_token = token_data.get("access_token")
        if not isinstance(refresh_token, str) or not isinstance(access_token, str):
            raise ExternalServiceError("Microsoft did not return the refresh token needed for local automation")
        profile = MicrosoftGraphClient._request_with_access_token(
            access_token,
            "GET",
            "/me?$select=id,displayName,userPrincipalName",
        )
        microsoft_user_id = profile.get("id")
        user_principal_name = profile.get("userPrincipalName")
        if not isinstance(microsoft_user_id, str) or not isinstance(user_principal_name, str):
            raise ExternalServiceError("Microsoft returned an incomplete signed-in user profile")

        cipher = TokenCipher(settings)
        expires_at = MicrosoftGraphClient._expires_at(token_data)
        connection = db.scalar(
            select(MicrosoftConnection).where(MicrosoftConnection.tenant_id == settings.microsoft_tenant_id)
        )
        if connection is not None and MicrosoftService.active_run(db) is not None:
            raise RuleViolationError(
                "Stop Teams automation before switching the connected Microsoft account"
            )
        if connection is None:
            connection = MicrosoftConnection(
                tenant_id=settings.microsoft_tenant_id,
                microsoft_user_id=microsoft_user_id,
                user_principal_name=user_principal_name,
                display_name=str(profile.get("displayName") or user_principal_name),
                encrypted_access_token=cipher.encrypt(access_token),
                encrypted_refresh_token=cipher.encrypt(refresh_token),
                access_token_expires_at=expires_at,
                granted_scopes=str(token_data.get("scope") or " ".join(DELEGATED_SCOPES)),
                last_connected_at=datetime.now(timezone.utc),
                last_error=None,
            )
            db.add(connection)
        else:
            connection.microsoft_user_id = microsoft_user_id
            connection.user_principal_name = user_principal_name
            connection.display_name = str(profile.get("displayName") or user_principal_name)
            connection.encrypted_access_token = cipher.encrypt(access_token)
            connection.encrypted_refresh_token = cipher.encrypt(refresh_token)
            connection.access_token_expires_at = expires_at
            connection.granted_scopes = str(token_data.get("scope") or " ".join(DELEGATED_SCOPES))
            connection.last_connected_at = datetime.now(timezone.utc)
            connection.last_error = None
        db.delete(pending_state)
        db.commit()
        db.refresh(connection)
        return connection

    @staticmethod
    def _exchange_code(settings: Settings, code: str, code_verifier: str) -> dict[str, Any]:
        response = httpx.post(
            "https://login.microsoftonline.com/{}/oauth2/v2.0/token".format(settings.microsoft_tenant_id),
            data={
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.microsoft_redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=20.0,
        )
        return MicrosoftGraphClient._json_or_error(response, "Microsoft sign-in failed")

    @staticmethod
    def _request_with_access_token(access_token: str, method: str, path: str) -> dict[str, Any]:
        response = httpx.request(
            method,
            GRAPH_BASE_URL + path,
            headers={"Authorization": "Bearer " + access_token},
            timeout=20.0,
        )
        return MicrosoftGraphClient._json_or_error(response, "Microsoft Graph request failed")

    @staticmethod
    def _json_or_error(response: httpx.Response, fallback_detail: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_error:
            graph_error = payload.get("error", {}) if isinstance(payload, dict) else {}
            message = graph_error.get("message") if isinstance(graph_error, dict) else None
            raise ExternalServiceError(message or fallback_detail)
        if not isinstance(payload, dict):
            raise ExternalServiceError(fallback_detail)
        return payload

    @staticmethod
    def _expires_at(token_data: dict[str, Any]) -> datetime:
        try:
            expires_in = int(token_data.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600
        return datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    def _access_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self.connection.access_token_expires_at > now + timedelta(seconds=TOKEN_REFRESH_SKEW_SECONDS):
            return self.cipher.decrypt(self.connection.encrypted_access_token)
        refresh_token = self.cipher.decrypt(self.connection.encrypted_refresh_token)
        response = httpx.post(
            "https://login.microsoftonline.com/{}/oauth2/v2.0/token".format(self.settings.microsoft_tenant_id),
            data={
                "client_id": self.settings.microsoft_client_id,
                "client_secret": self.settings.microsoft_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(DELEGATED_SCOPES),
            },
            timeout=20.0,
        )
        token_data = self._json_or_error(response, "Microsoft connection has expired; reconnect it from the dashboard")
        new_access_token = token_data.get("access_token")
        if not isinstance(new_access_token, str):
            raise ExternalServiceError("Microsoft did not return an access token while refreshing the connection")
        self.connection.encrypted_access_token = self.cipher.encrypt(new_access_token)
        if isinstance(token_data.get("refresh_token"), str):
            self.connection.encrypted_refresh_token = self.cipher.encrypt(token_data["refresh_token"])
        self.connection.access_token_expires_at = self._expires_at(token_data)
        self.connection.granted_scopes = str(token_data.get("scope") or self.connection.granted_scopes)
        self.connection.last_error = None
        self.db.commit()
        return new_access_token

    def request(self, method: str, path_or_url: str, *, json_body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("https://") else GRAPH_BASE_URL + path_or_url
        response = httpx.request(
            method,
            url,
            headers={"Authorization": "Bearer " + self._access_token()},
            json=json_body,
            timeout=20.0,
        )
        return self._json_or_error(response, "Microsoft Graph request failed")

    def delete(self, path: str) -> None:
        response = httpx.request(
            "DELETE",
            GRAPH_BASE_URL + path,
            headers={"Authorization": "Bearer " + self._access_token()},
            timeout=20.0,
        )
        if response.status_code not in (202, 204, 404):
            self._json_or_error(response, "Microsoft Graph subscription deletion failed")

    def list_active_users(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        url = (
            "/users?$select=id,displayName,mail,userPrincipalName,jobTitle,accountEnabled"
            "&$top=999"
        )
        while url:
            payload = self.request("GET", url)
            values = payload.get("value", [])
            if not isinstance(values, list):
                raise ExternalServiceError("Microsoft returned an invalid directory response")
            users.extend(item for item in values if isinstance(item, dict) and item.get("accountEnabled") is not False)
            next_link = payload.get("@odata.nextLink")
            url = next_link if isinstance(next_link, str) else ""
        return users

    def create_direct_chat(self, target_microsoft_user_id: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/chats",
            json_body={
                "chatType": "oneOnOne",
                "members": [
                    {
                        "@odata.type": "#microsoft.graph.aadUserConversationMember",
                        "roles": ["owner"],
                        "user@odata.bind": "https://graph.microsoft.com/v1.0/users('{}')".format(
                            self.connection.microsoft_user_id
                        ),
                    },
                    {
                        "@odata.type": "#microsoft.graph.aadUserConversationMember",
                        "roles": ["owner"],
                        "user@odata.bind": "https://graph.microsoft.com/v1.0/users('{}')".format(
                            target_microsoft_user_id
                        ),
                    },
                ],
            },
        )

    def create_subscription(self, chat_id: str, webhook_url: str, client_state: str) -> dict[str, Any]:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=SUBSCRIPTION_LIFETIME_MINUTES)
        return self.request(
            "POST",
            "/subscriptions",
            json_body={
                "changeType": "created",
                "notificationUrl": webhook_url,
                "lifecycleNotificationUrl": webhook_url,
                "resource": "/chats/{}/messages".format(chat_id),
                "expirationDateTime": expires_at.isoformat().replace("+00:00", "Z"),
                "clientState": client_state,
            },
        )

    def renew_subscription(self, external_subscription_id: str) -> dict[str, Any]:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=SUBSCRIPTION_LIFETIME_MINUTES)
        return self.request(
            "PATCH",
            "/subscriptions/{}".format(external_subscription_id),
            json_body={"expirationDateTime": expires_at.isoformat().replace("+00:00", "Z")},
        )

    def send_chat_message(self, chat_id: str, content: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/chats/{}/messages".format(chat_id),
            json_body={
                "body": {
                    "contentType": "html",
                    "content": MicrosoftService.teams_html_message(content),
                }
            },
        )

    def send_mail(
        self, recipient_email: str, subject: str, content: str, *, content_type: str = "Text"
    ) -> None:
        """Send a Text or HTML email from the connected delegated Microsoft account."""

        if content_type not in {"Text", "HTML"}:
            raise ValueError("Mail content_type must be Text or HTML")

        response = httpx.post(
            GRAPH_BASE_URL + "/me/sendMail",
            headers={"Authorization": "Bearer " + self._access_token()},
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": content_type, "content": content},
                    "toRecipients": [{"emailAddress": {"address": recipient_email}}],
                },
                "saveToSentItems": True,
            },
            timeout=20.0,
        )
        if response.status_code not in (202, 204):
            self._json_or_error(response, "Microsoft mail send failed")

    def get_chat_message(self, chat_id: str, message_id: str) -> dict[str, Any]:
        return self.request("GET", "/chats/{}/messages/{}".format(chat_id, message_id))


class MicrosoftDirectoryService:
    @staticmethod
    def sync_active_users(db: Session) -> DirectorySyncResult:
        connection = MicrosoftService.get_connection(db)
        graph = MicrosoftGraphClient(db, connection)
        created = updated = skipped = 0
        for user in graph.list_active_users():
            microsoft_id = user.get("id")
            email = user.get("mail") or user.get("userPrincipalName")
            name = user.get("displayName") or email
            if not all(isinstance(value, str) and value.strip() for value in (microsoft_id, email, name)):
                skipped += 1
                continue
            normalized_email = email.strip().lower()
            employee = db.scalar(select(Employee).where(Employee.teams_user_id == microsoft_id))
            if employee is None:
                employee = db.scalar(select(Employee).where(Employee.email == normalized_email))
            if employee is None:
                db.add(
                    Employee(
                        name=name.strip(),
                        email=normalized_email,
                        role="Team member",
                        title=str(user.get("jobTitle") or "").strip() or None,
                        teams_user_id=microsoft_id,
                        is_active=True,
                        is_managed=False,
                    )
                )
                created += 1
                continue
            if employee.teams_user_id not in (None, microsoft_id):
                skipped += 1
                continue
            employee.name = name.strip()
            employee.email = normalized_email
            employee.title = str(user.get("jobTitle") or "").strip() or None
            employee.teams_user_id = microsoft_id
            employee.is_active = True
            updated += 1
        db.commit()
        return DirectorySyncResult(
            created=created,
            updated=updated,
            skipped=skipped,
            active_users_seen=created + updated + skipped,
        )


class MicrosoftService:
    @staticmethod
    def is_configured() -> bool:
        return MicrosoftService.is_auth_configured() and bool(
            get_settings().microsoft_webhook_base_url
        )

    @staticmethod
    def is_auth_configured() -> bool:
        settings = get_settings()
        return bool(
            settings.microsoft_tenant_id
            and settings.microsoft_client_id
            and settings.microsoft_client_secret
            and settings.microsoft_token_encryption_key
        )

    @staticmethod
    def get_connection(db: Session) -> MicrosoftConnection:
        connection = db.scalar(
            select(MicrosoftConnection).order_by(MicrosoftConnection.last_connected_at.desc()).limit(1)
        )
        if connection is None:
            raise RuleViolationError("Connect your Microsoft account from the dashboard before using Teams automation")
        return connection

    @staticmethod
    def active_run(db: Session) -> Optional[AutomationRun]:
        return db.scalar(
            select(AutomationRun)
            .where(AutomationRun.status == AutomationStatus.RUNNING)
            .order_by(AutomationRun.started_at.desc())
            .limit(1)
        )

    @staticmethod
    def status(db: Session) -> MicrosoftStatusRead:
        connection = db.scalar(
            select(MicrosoftConnection).order_by(MicrosoftConnection.last_connected_at.desc()).limit(1)
        )
        active_run = MicrosoftService.active_run(db)
        listener_expires_at: Optional[datetime] = None
        if active_run is not None:
            listener_expires_at = db.scalar(
                select(func.min(MicrosoftTeamsSubscription.expires_at)).where(
                    MicrosoftTeamsSubscription.automation_run_id == active_run.id,
                    MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                    MicrosoftTeamsSubscription.expires_at > datetime.now(timezone.utc),
                )
            )
        return MicrosoftStatusRead(
            is_auth_configured=MicrosoftService.is_auth_configured(),
            is_configured=MicrosoftService.is_configured(),
            is_connected=connection is not None,
            connection=connection,
            active_run=active_run,
            listener_expires_at=listener_expires_at,
        )

    @staticmethod
    def start_automation(db: Session, payload: AutomationStart) -> AutomationRun:
        if MicrosoftService.active_run(db) is not None:
            raise ConflictError("Teams automation is already running. Stop it before starting a new run")
        settings = MicrosoftGraphClient.require_auth_configuration()
        webhook_url = MicrosoftService._webhook_url(settings)
        connection = MicrosoftService.get_connection(db)
        target_query = select(Employee).where(
            Employee.is_active.is_(True),
            Employee.is_managed.is_(True),
            Employee.teams_user_id.is_not(None),
        )
        if payload.target_employee_ids:
            requested_ids = set(payload.target_employee_ids)
            target_query = target_query.where(Employee.id.in_(requested_ids))
        targets = list(db.scalars(target_query.order_by(Employee.name, Employee.id)))
        if payload.target_employee_ids and {employee.id for employee in targets} != requested_ids:
            raise RuleViolationError(
                "Every targeted employee must be active, managed, and imported from Microsoft"
            )
        if not targets:
            raise RuleViolationError(
                "Choose at least one active imported employee as managed before starting automation"
            )
        now = datetime.now(timezone.utc)
        base_prompt = payload.initial_prompt or MicrosoftService.default_initial_prompt()
        run = AutomationRun(
            connection_id=connection.id,
            status=AutomationStatus.RUNNING,
            initial_prompt=base_prompt,
            target_employee_ids=[str(employee.id) for employee in targets],
            target_count=len(targets),
            started_at=now,
        )
        db.add(run)
        db.flush()
        graph = MicrosoftGraphClient(db, connection)
        checkin_day = now.astimezone(ZoneInfo(settings.manager_timezone)).date().isoformat()
        for employee in targets:
            conversation: Optional[Conversation] = None
            content = MicrosoftService.initial_message_for(employee.name, base_prompt)
            checkin_key = "daily-checkin:{}:{}:{}".format(
                checkin_day, employee.id, connection.microsoft_user_id
            )
            try:
                conversation = MicrosoftService._get_or_create_direct_conversation(
                    db, graph, employee
                )
                MicrosoftService._ensure_subscription(db, graph, run, conversation, webhook_url)
                existing_checkin = db.scalar(
                    select(AutomationAction).where(AutomationAction.idempotency_key == checkin_key)
                )
                if existing_checkin is not None and existing_checkin.status in (
                    AutomationActionStatus.DELIVERED,
                    AutomationActionStatus.SKIPPED,
                ):
                    # A scheduler cycle may have already sent today's check-in.
                    # Reuse it instead of sending a duplicate when starting a run.
                    run.delivered_count += 1
                    continue
                sent = graph.send_chat_message(str(conversation.external_conversation_id), content)
                external_message_id = sent.get("id")
                if not isinstance(external_message_id, str):
                    raise ExternalServiceError("Microsoft did not return an ID for the sent Teams message")
                created_at = MicrosoftService._parse_graph_datetime(sent.get("createdDateTime"))
                message = Message(
                        conversation_id=conversation.id,
                        employee_id=employee.id,
                        direction=MessageDirection.OUTBOUND,
                        sender_type=SenderType.YASH,
                        delivery_status=MessageDeliveryStatus.DELIVERED,
                        external_message_id=external_message_id,
                        external_created_at=created_at,
                        content=content,
                    )
                db.add(message)
                db.flush()
                if existing_checkin is None:
                    existing_checkin = AutomationAction(
                        action_type=AutomationActionType.DAILY_CHECKIN,
                        status=AutomationActionStatus.DELIVERED,
                        idempotency_key=checkin_key,
                        employee_id=employee.id,
                        message_id=message.id,
                        detail="Initial automation check-in",
                        executed_at=created_at or now,
                    )
                    db.add(existing_checkin)
                else:
                    # A previous scheduler attempt may have failed before
                    # automation was started. Reuse that audit row safely.
                    existing_checkin.status = AutomationActionStatus.DELIVERED
                    existing_checkin.message_id = message.id
                    existing_checkin.detail = "Initial automation check-in"
                    existing_checkin.executed_at = created_at or now
                conversation.last_message_at = created_at or datetime.now(timezone.utc)
                run.delivered_count += 1
            except (ExternalServiceError, RuleViolationError) as exc:
                run.failed_count += 1
                run.last_error = exc.detail
                if conversation is not None:
                    db.add(
                        Message(
                            conversation_id=conversation.id,
                            employee_id=employee.id,
                            direction=MessageDirection.OUTBOUND,
                            sender_type=SenderType.YASH,
                            delivery_status=MessageDeliveryStatus.FAILED,
                            content=content,
                        )
                    )
        if run.delivered_count == 0:
            run.status = AutomationStatus.FAILED
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def stop_automation(db: Session) -> AutomationRun:
        run = MicrosoftService.active_run(db)
        if run is None:
            raise RuleViolationError("Teams automation is not running")
        connection = MicrosoftService.get_connection(db)
        graph = MicrosoftGraphClient(db, connection)
        subscriptions = list(
            db.scalars(
                select(MicrosoftTeamsSubscription).where(
                    MicrosoftTeamsSubscription.automation_run_id == run.id,
                    MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                )
            )
        )
        for subscription in subscriptions:
            try:
                graph.delete("/subscriptions/{}".format(subscription.external_subscription_id))
                subscription.status = MicrosoftSubscriptionStatus.STOPPED
                subscription.last_error = None
            except ExternalServiceError as exc:
                subscription.status = MicrosoftSubscriptionStatus.FAILED
                subscription.last_error = exc.detail
        run.status = AutomationStatus.STOPPED
        run.stopped_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def renew_listener(db: Session) -> SubscriptionRenewalResult:
        run = MicrosoftService.active_run(db)
        if run is None:
            raise RuleViolationError("Start Teams automation before renewing its reply listener")
        settings = MicrosoftGraphClient.require_auth_configuration()
        webhook_url = MicrosoftService._webhook_url(settings)
        connection = MicrosoftService.get_connection(db)
        graph = MicrosoftGraphClient(db, connection)
        now = datetime.now(timezone.utc)
        subscriptions = list(
            db.scalars(
                select(MicrosoftTeamsSubscription).where(
                    MicrosoftTeamsSubscription.automation_run_id == run.id,
                    MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                )
            )
        )
        renewed = failed = 0
        covered_conversation_ids: set[Any] = set()
        for subscription in subscriptions:
            try:
                response = graph.renew_subscription(subscription.external_subscription_id)
                subscription.expires_at = MicrosoftService._parse_graph_datetime(
                    response.get("expirationDateTime")
                ) or (now + timedelta(minutes=SUBSCRIPTION_LIFETIME_MINUTES))
                subscription.last_error = None
                covered_conversation_ids.add(subscription.conversation_id)
                renewed += 1
            except ExternalServiceError as exc:
                # Graph subscriptions can disappear or fail renewal even while
                # the automation run is healthy. Retire the stale record and
                # recreate the listener immediately instead of leaving this
                # employee permanently deaf until automation is restarted.
                subscription.status = MicrosoftSubscriptionStatus.FAILED
                subscription.last_error = exc.detail
                db.flush()
                # Legacy subscriptions created before lifecycle callbacks were
                # enabled cannot be extended beyond one hour. Remove that
                # remote subscription first so its long-lived replacement does
                # not conflict on the same chat resource.
                if "lifecyclenotificationurl" in exc.detail.casefold():
                    try:
                        graph.delete(
                            "/subscriptions/{}".format(subscription.external_subscription_id)
                        )
                    except ExternalServiceError:
                        pass
                try:
                    MicrosoftService._ensure_subscription(
                        db, graph, run, subscription.conversation, webhook_url
                    )
                    covered_conversation_ids.add(subscription.conversation_id)
                    renewed += 1
                except ExternalServiceError as recreate_exc:
                    subscription.last_error = (
                        "Renewal failed: {} Re-creation failed: {}".format(
                            exc.detail, recreate_exc.detail
                        )
                    )
                    failed += 1

        # Also repair listeners that failed during a previous cycle. Failed
        # subscriptions are intentionally excluded above, so derive the
        # required coverage from the run targets rather than only from the
        # currently-active subscription rows.
        target_ids = set(run.target_employee_ids or [])
        if target_ids:
            conversations = list(
                db.scalars(
                    select(Conversation).where(
                        Conversation.employee_id.in_(target_ids),
                        Conversation.channel == ConversationChannel.TEAMS,
                        Conversation.external_conversation_id.is_not(None),
                    )
                )
            )
            for conversation in conversations:
                if conversation.id in covered_conversation_ids:
                    continue
                active = db.scalar(
                    select(MicrosoftTeamsSubscription.id).where(
                        MicrosoftTeamsSubscription.automation_run_id == run.id,
                        MicrosoftTeamsSubscription.conversation_id == conversation.id,
                        MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                        MicrosoftTeamsSubscription.expires_at > now + timedelta(minutes=2),
                    )
                )
                if active is not None:
                    covered_conversation_ids.add(conversation.id)
                    continue
                try:
                    MicrosoftService._ensure_subscription(
                        db, graph, run, conversation, webhook_url
                    )
                    covered_conversation_ids.add(conversation.id)
                    renewed += 1
                except ExternalServiceError as exc:
                    run.last_error = "Reply-listener recovery failed: {}".format(exc.detail)
                    failed += 1
            # Report final uncovered targets, not transient renewal attempts
            # that were successfully recovered later in this same call.
            final_active_count = db.scalar(
                select(func.count(func.distinct(Conversation.employee_id)))
                .join(
                    MicrosoftTeamsSubscription,
                    MicrosoftTeamsSubscription.conversation_id == Conversation.id,
                )
                .where(
                    Conversation.employee_id.in_(target_ids),
                    MicrosoftTeamsSubscription.automation_run_id == run.id,
                    MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                    MicrosoftTeamsSubscription.expires_at > now + timedelta(minutes=2),
                )
            ) or 0
            failed = max(0, len(target_ids) - final_active_count)
            if failed == 0 and run.last_error and run.last_error.startswith(
                "Reply-listener recovery failed:"
            ):
                run.last_error = None
        db.commit()
        listener_expires_at = db.scalar(
            select(func.min(MicrosoftTeamsSubscription.expires_at)).where(
                MicrosoftTeamsSubscription.automation_run_id == run.id,
                MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                MicrosoftTeamsSubscription.expires_at > now,
            )
        )
        return SubscriptionRenewalResult(
            renewed=renewed, failed=failed, listener_expires_at=listener_expires_at
        )

    @staticmethod
    def process_webhook_notification(db: Session, notification: dict[str, Any]) -> Optional[str]:
        external_subscription_id = notification.get("subscriptionId")
        client_state = notification.get("clientState")
        if not isinstance(external_subscription_id, str) or not isinstance(client_state, str):
            return None
        subscription = db.scalar(
            select(MicrosoftTeamsSubscription).where(
                MicrosoftTeamsSubscription.external_subscription_id == external_subscription_id,
                MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
            )
        )
        if subscription is None:
            return None
        expected_client_state = TokenCipher().decrypt(subscription.encrypted_client_state)
        if not hmac.compare_digest(expected_client_state, client_state):
            return None
        if notification.get("changeType") != "created":
            return None
        message_id = MicrosoftService._notification_message_id(notification)
        if message_id is None:
            return None
        conversation = subscription.conversation
        if conversation.external_conversation_id is None or conversation.employee_id is None:
            return None
        connection = subscription.connection
        graph = MicrosoftGraphClient(db, connection)
        remote_message = graph.get_chat_message(conversation.external_conversation_id, message_id)
        sender_user_id = MicrosoftService._sender_user_id(remote_message)
        if sender_user_id is None or sender_user_id == connection.microsoft_user_id:
            return None
        employee = db.get(Employee, conversation.employee_id)
        # A conversation has a listener only after this application intentionally
        # contacted the employee. Dependency owners need not be direct reports.
        if employee is None or employee.teams_user_id != sender_user_id:
            return None
        existing = db.scalar(select(Message.id).where(Message.external_message_id == message_id))
        if existing is not None:
            return None
        content = MicrosoftService._message_content(remote_message)
        if not content:
            return None
        external_created_at = MicrosoftService._parse_graph_datetime(remote_message.get("createdDateTime"))
        message = Message(
                conversation_id=conversation.id,
                employee_id=employee.id,
                direction=MessageDirection.INBOUND,
                sender_type=SenderType.EMPLOYEE,
                delivery_status=MessageDeliveryStatus.DELIVERED,
                external_message_id=message_id,
                external_created_at=external_created_at,
                content=content,
                reply_to_external_id=MicrosoftService._reply_reference(remote_message)[0],
                quoted_content=MicrosoftService._reply_reference(remote_message)[1],
            )
        db.add(message)
        db.flush()
        MemoryService.record_message_evidence(db, message)
        conversation.last_message_at = external_created_at or datetime.now(timezone.utc)
        db.commit()
        return str(message.id)

    @staticmethod
    def send_management_message(db: Session, employee: Employee, content: str) -> Message:
        """Send an auditable Teams follow-up as the connected Yash account.

        This is deliberately the only path the management agent may use for
        outbound Teams messages. It also adds a reply listener for a dependency
        owner who is not one of Yash's selected direct reports.
        """

        run = MicrosoftService.active_run(db)
        if run is None:
            raise RuleViolationError("Teams automation must be running before the agent can send a follow-up")
        if str(employee.id) not in set(run.target_employee_ids or []):
            raise RuleViolationError("This employee is not included in the active automation run")
        settings = MicrosoftGraphClient.require_auth_configuration()
        connection = MicrosoftService.get_connection(db)
        graph = MicrosoftGraphClient(db, connection)
        conversation = MicrosoftService._get_or_create_direct_conversation(db, graph, employee)
        MicrosoftService._ensure_subscription(
            db, graph, run, conversation, MicrosoftService._webhook_url(settings)
        )
        sent = graph.send_chat_message(str(conversation.external_conversation_id), content)
        external_message_id = sent.get("id")
        if not isinstance(external_message_id, str):
            raise ExternalServiceError("Microsoft did not return an ID for the sent Teams message")
        created_at = MicrosoftService._parse_graph_datetime(sent.get("createdDateTime"))
        message = Message(
            conversation_id=conversation.id,
            employee_id=employee.id,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.YASH,
            delivery_status=MessageDeliveryStatus.DELIVERED,
            external_message_id=external_message_id,
            external_created_at=created_at,
            content=content,
        )
        db.add(message)
        MemoryService.record_message_evidence(db, message)
        conversation.last_message_at = created_at or datetime.now(timezone.utc)
        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def send_one_off_manager_report(db: Session, employee: Employee, content: str) -> Message:
        """Send one explicit, audited report without changing automation scope.

        This is for manager-authorized one-off reporting to somebody outside the
        active managed-team run. It deliberately does not add a reply listener,
        subscribe the recipient, or make them eligible for scheduled check-ins.
        """

        if not employee.is_active or employee.teams_user_id is None:
            raise RuleViolationError("The report recipient must be an active imported Microsoft user")
        connection = MicrosoftService.get_connection(db)
        graph = MicrosoftGraphClient(db, connection)
        conversation = MicrosoftService._get_or_create_direct_conversation(db, graph, employee)
        sent = graph.send_chat_message(str(conversation.external_conversation_id), content)
        external_message_id = sent.get("id")
        if not isinstance(external_message_id, str):
            raise ExternalServiceError("Microsoft did not return an ID for the sent Teams message")
        created_at = MicrosoftService._parse_graph_datetime(sent.get("createdDateTime"))
        message = Message(
            conversation_id=conversation.id,
            employee_id=employee.id,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.YASH,
            delivery_status=MessageDeliveryStatus.DELIVERED,
            external_message_id=external_message_id,
            external_created_at=created_at,
            content=content,
        )
        db.add(message)
        MemoryService.record_message_evidence(db, message)
        conversation.last_message_at = created_at or datetime.now(timezone.utc)
        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def default_initial_prompt() -> str:
        return (
            "What are you working on, what’s the expected outcome, and is anything blocking you?"
            " If yes, who can unblock it?"
        )

    @staticmethod
    def initial_message_for(name: str, prompt: str) -> str:
        message = "Hi {},\n\n{}".format(MicrosoftService.first_name(name), prompt.strip())
        if message.rstrip().endswith(SIGNATURE):
            return message.rstrip()
        return message.rstrip() + "\n\n" + SIGNATURE

    @staticmethod
    def follow_up_message_for(name: str, body: str) -> str:
        return MicrosoftService.initial_message_for(name, body)

    @staticmethod
    def first_name(name: str) -> str:
        """Use only the first name in agent-authored Teams messages."""

        parts = " ".join((name or "").split()).split(" ")
        return parts[0] if parts and parts[0] else "there"

    @staticmethod
    def teams_html_message(content: str) -> str:
        """Render a safe Teams HTML body while retaining plain text in the audit log."""

        paragraphs = [paragraph.strip() for paragraph in content.strip().split("\n\n") if paragraph.strip()]
        if paragraphs and paragraphs[-1] == SIGNATURE:
            paragraphs.pop()
        normal_html = "".join(
            "<p>{}</p>".format(html_escape(paragraph).replace("\n", "<br>"))
            for paragraph in paragraphs
        )
        # Teams consistently preserves <em>. Some Teams clients may ignore the
        # font/color preference, but the signature remains visibly separate.
        signature_html = (
            '<p><em><span style="font-family: Georgia, serif; color: #6264A7;">'
            "— " + SIGNATURE + "</span></em></p>"
        )
        return normal_html + signature_html

    @staticmethod
    def _webhook_url(settings: Settings) -> str:
        base_url = (settings.microsoft_webhook_base_url or "").strip().rstrip("/")
        if not base_url.startswith("https://"):
            raise RuleViolationError(
                "MICROSOFT_WEBHOOK_BASE_URL must be a public HTTPS URL before Teams automation starts"
            )
        return base_url + "/api/v1/microsoft/teams/webhook"

    @staticmethod
    def _get_or_create_direct_conversation(
        db: Session, graph: MicrosoftGraphClient, employee: Employee
    ) -> Conversation:
        if employee.teams_user_id is None:
            raise RuleViolationError("Managed employee has no Microsoft directory ID")
        remote_chat = graph.create_direct_chat(employee.teams_user_id)
        external_conversation_id = remote_chat.get("id")
        if not isinstance(external_conversation_id, str):
            raise ExternalServiceError("Microsoft did not return a direct Teams chat ID")
        conversation = db.scalar(
            select(Conversation).where(Conversation.external_conversation_id == external_conversation_id)
        )
        if conversation is None:
            conversation = Conversation(
                employee_id=employee.id,
                channel=ConversationChannel.TEAMS,
                external_conversation_id=external_conversation_id,
                conversation_type=ConversationType.DIRECT,
                started_at=MicrosoftService._parse_graph_datetime(remote_chat.get("createdDateTime"))
                or datetime.now(timezone.utc),
                last_message_at=datetime.now(timezone.utc),
            )
            db.add(conversation)
            db.flush()
        elif conversation.employee_id != employee.id:
            raise RuleViolationError("A Teams chat is already linked to a different employee")
        return conversation

    @staticmethod
    def _ensure_subscription(
        db: Session,
        graph: MicrosoftGraphClient,
        run: AutomationRun,
        conversation: Conversation,
        webhook_url: str,
    ) -> MicrosoftTeamsSubscription:
        now = datetime.now(timezone.utc)
        existing = db.scalar(
            select(MicrosoftTeamsSubscription)
            .where(
                MicrosoftTeamsSubscription.conversation_id == conversation.id,
                MicrosoftTeamsSubscription.status == MicrosoftSubscriptionStatus.ACTIVE,
                MicrosoftTeamsSubscription.expires_at > now + timedelta(minutes=2),
            )
            .order_by(MicrosoftTeamsSubscription.expires_at.desc())
            .limit(1)
        )
        if existing is not None:
            existing.automation_run_id = run.id
            return existing
        client_state = secrets.token_urlsafe(32)
        response = graph.create_subscription(
            str(conversation.external_conversation_id), webhook_url, client_state
        )
        external_subscription_id = response.get("id")
        if not isinstance(external_subscription_id, str):
            raise ExternalServiceError("Microsoft did not return a Teams reply-listener ID")
        subscription = MicrosoftTeamsSubscription(
            connection_id=graph.connection.id,
            automation_run_id=run.id,
            conversation_id=conversation.id,
            external_subscription_id=external_subscription_id,
            resource=str(response.get("resource") or "/chats/{}/messages".format(conversation.external_conversation_id)),
            encrypted_client_state=graph.cipher.encrypt(client_state),
            expires_at=MicrosoftService._parse_graph_datetime(response.get("expirationDateTime"))
            or (now + timedelta(minutes=SUBSCRIPTION_LIFETIME_MINUTES)),
            status=MicrosoftSubscriptionStatus.ACTIVE,
        )
        db.add(subscription)
        db.flush()
        return subscription

    @staticmethod
    def _notification_message_id(notification: dict[str, Any]) -> Optional[str]:
        resource_data = notification.get("resourceData")
        if isinstance(resource_data, dict) and isinstance(resource_data.get("id"), str):
            return resource_data["id"]
        resource = notification.get("resource")
        if not isinstance(resource, str):
            return None
        marker = "/messages/"
        if marker in resource:
            return resource.rsplit(marker, 1)[1].strip("()'")
        return None

    @staticmethod
    def _sender_user_id(remote_message: dict[str, Any]) -> Optional[str]:
        sender = remote_message.get("from")
        if not isinstance(sender, dict):
            return None
        user = sender.get("user")
        if not isinstance(user, dict):
            return None
        identifier = user.get("id")
        return identifier if isinstance(identifier, str) else None

    @staticmethod
    def _message_content(remote_message: dict[str, Any]) -> str:
        body = remote_message.get("body")
        if not isinstance(body, dict):
            return ""
        content = body.get("content")
        if not isinstance(content, str):
            return ""
        if body.get("contentType") == "html":
            parser = _HTMLTextExtractor()
            parser.feed(content)
            parser.close()
            return re.sub(r"\s+([,.;:!?])", r"\1", parser.text())
        return content.strip()

    @staticmethod
    def _reply_reference(remote_message: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        body = remote_message.get("body") or {}
        parser = _HTMLTextExtractor()
        if body.get("contentType") == "html":
            parser.feed(body.get("content") or "")
            parser.close()
        reference = remote_message.get("replyToId") or parser.reply_id
        for attachment in remote_message.get("attachments") or []:
            if attachment.get("contentType") == "messageReference":
                try:
                    value = json.loads(attachment.get("content") or "{}")
                    reference = value.get("messageId") or reference
                except (ValueError, TypeError):
                    pass
        quote = " ".join(" ".join(parser.quoted_parts).split())
        return (str(reference) if reference else None, quote or None)

    @staticmethod
    def _parse_graph_datetime(value: Any) -> Optional[datetime]:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
