from __future__ import annotations

from typing import ClassVar

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.llm.provider_credential import ProviderCredential
from app.services.errors import RuleViolationError


class ProviderCredentialService:
    """Encrypt and activate the single-manager OpenAI BYOK credential."""

    _runtime_openai: ClassVar[tuple[str, str] | None] = None

    @staticmethod
    def _fernet(settings: Settings) -> Fernet:
        key = settings.credential_encryption_key
        if not key:
            raise RuleViolationError(
                "PROVIDER_CREDENTIAL_ENCRYPTION_KEY or MICROSOFT_TOKEN_ENCRYPTION_KEY is required"
            )
        try:
            return Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise RuleViolationError("Provider credential encryption key is invalid") from exc

    @classmethod
    def load(cls, db: Session, settings: Settings | None = None) -> ProviderCredential | None:
        resolved = settings or get_settings()
        credential = db.scalar(
            select(ProviderCredential).where(
                ProviderCredential.provider == "openai",
                ProviderCredential.is_active.is_(True),
            )
        )
        if credential is None:
            cls._runtime_openai = None
            return None
        try:
            api_key = (
                cls._fernet(resolved)
                .decrypt(credential.encrypted_api_key.encode("utf-8"))
                .decode("utf-8")
            )
        except InvalidToken as exc:
            cls._runtime_openai = None
            raise RuleViolationError("Stored OpenAI credential cannot be decrypted") from exc
        cls._runtime_openai = (api_key, credential.model)
        return credential

    @classmethod
    def effective_settings(cls, settings: Settings) -> Settings:
        if cls._runtime_openai is None:
            return settings
        api_key, model = cls._runtime_openai
        return settings.model_copy(
            update={"llm_provider": "openai", "llm_model": model, "openai_api_key": api_key}
        )

    @classmethod
    def save_openai(
        cls, db: Session, *, api_key: str, model: str, settings: Settings | None = None
    ) -> ProviderCredential:
        resolved = settings or get_settings()
        clean_key = api_key.strip()
        clean_model = model.strip()
        if len(clean_key) < 20:
            raise RuleViolationError("OpenAI API key is too short")
        if not clean_model or len(clean_model) > 255:
            raise RuleViolationError("A valid OpenAI model name is required")
        encrypted = cls._fernet(resolved).encrypt(clean_key.encode("utf-8")).decode("utf-8")
        credential = db.scalar(
            select(ProviderCredential).where(ProviderCredential.provider == "openai")
        )
        if credential is None:
            credential = ProviderCredential(
                provider="openai",
                model=clean_model,
                encrypted_api_key=encrypted,
                key_last_four=clean_key[-4:],
                is_active=True,
            )
            db.add(credential)
        else:
            credential.model = clean_model
            credential.encrypted_api_key = encrypted
            credential.key_last_four = clean_key[-4:]
            credential.is_active = True
        db.commit()
        db.refresh(credential)
        cls._runtime_openai = (clean_key, clean_model)
        return credential

    @classmethod
    def remove_openai(cls, db: Session) -> bool:
        credential = db.scalar(
            select(ProviderCredential).where(ProviderCredential.provider == "openai")
        )
        if credential is None:
            cls._runtime_openai = None
            return False
        db.delete(credential)
        db.commit()
        cls._runtime_openai = None
        return True
