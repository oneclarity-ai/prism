from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.llm.provider_credential import ProviderCredential
from app.services.errors import RuleViolationError


@dataclass(frozen=True)
class _RuntimeCredential:
    api_key: str
    model: str
    base_url: str | None = None
    api_version: str | None = None


class ProviderCredentialService:
    """Encrypt, store and run BYOK credentials for any registered LLM provider.

    Credentials are decrypted into an in-process cache (never persisted in plaintext) keyed
    by provider id. `effective_settings` only overrides the provider `LLM_PROVIDER` already
    selects on the server: saving a key does not switch which provider Prism runs, it supplies
    the key for whichever one is already active.
    """

    _runtime: ClassVar[dict[str, _RuntimeCredential]] = {}

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
    def load_all(
        cls, db: Session, settings: Settings | None = None
    ) -> dict[str, ProviderCredential]:
        """Decrypt every active credential row and warm the runtime cache.

        Returns the active rows keyed by provider id, for callers that need the metadata
        (masked key, timestamps) without touching the decrypted cache directly.
        """
        resolved = settings or get_settings()
        rows = db.scalars(
            select(ProviderCredential).where(ProviderCredential.is_active.is_(True))
        ).all()
        cache: dict[str, _RuntimeCredential] = {}
        by_provider: dict[str, ProviderCredential] = {}
        if rows:
            fernet = cls._fernet(resolved)
            for row in rows:
                try:
                    api_key = fernet.decrypt(row.encrypted_api_key.encode("utf-8")).decode("utf-8")
                except InvalidToken:
                    continue
                cache[row.provider] = _RuntimeCredential(
                    api_key=api_key,
                    model=row.model,
                    base_url=row.base_url,
                    api_version=row.api_version,
                )
                by_provider[row.provider] = row
        cls._runtime = cache
        return by_provider

    @classmethod
    def effective_settings(cls, settings: Settings) -> Settings:
        provider_id = settings.llm_provider.strip().casefold()
        credential = cls._runtime.get(provider_id)
        if credential is None:
            return settings
        update: dict[str, object] = {"llm_model": credential.model}
        if provider_id == "openai":
            update["openai_api_key"] = credential.api_key
            if credential.base_url:
                update["openai_base_url"] = credential.base_url
        elif provider_id == "azure_openai":
            update["azure_openai_api_key"] = credential.api_key
            if credential.base_url:
                update["azure_openai_endpoint"] = credential.base_url
            if credential.api_version:
                update["azure_openai_api_version"] = credential.api_version
        elif provider_id == "anthropic":
            update["anthropic_api_key"] = credential.api_key
            if credential.base_url:
                update["anthropic_base_url"] = credential.base_url
            if credential.api_version:
                update["anthropic_api_version"] = credential.api_version
        elif provider_id == "deepseek":
            update["deepseek_api_key"] = credential.api_key
            if credential.base_url:
                update["deepseek_base_url"] = credential.base_url
        elif provider_id == "custom":
            update["custom_llm_api_key"] = credential.api_key
            if credential.base_url:
                update["custom_llm_base_url"] = credential.base_url
        else:
            return settings
        return settings.model_copy(update=update)

    @classmethod
    def save(
        cls,
        db: Session,
        *,
        provider_id: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        api_version: str | None = None,
        settings: Settings | None = None,
    ) -> ProviderCredential:
        resolved = settings or get_settings()
        clean_key = api_key.strip()
        clean_model = model.strip()
        clean_base_url = (base_url or "").strip() or None
        clean_api_version = (api_version or "").strip() or None
        if len(clean_key) < 8:
            raise RuleViolationError("API key is too short")
        if not clean_model or len(clean_model) > 255:
            raise RuleViolationError("A valid model name is required")
        encrypted = cls._fernet(resolved).encrypt(clean_key.encode("utf-8")).decode("utf-8")
        credential = db.scalar(
            select(ProviderCredential).where(ProviderCredential.provider == provider_id)
        )
        if credential is None:
            credential = ProviderCredential(
                provider=provider_id,
                model=clean_model,
                encrypted_api_key=encrypted,
                key_last_four=clean_key[-4:],
                base_url=clean_base_url,
                api_version=clean_api_version,
                is_active=True,
            )
            db.add(credential)
        else:
            credential.model = clean_model
            credential.encrypted_api_key = encrypted
            credential.key_last_four = clean_key[-4:]
            credential.base_url = clean_base_url
            credential.api_version = clean_api_version
            credential.is_active = True
        db.commit()
        db.refresh(credential)
        cls._runtime[provider_id] = _RuntimeCredential(
            api_key=clean_key,
            model=clean_model,
            base_url=clean_base_url,
            api_version=clean_api_version,
        )
        return credential

    @classmethod
    def remove(cls, db: Session, *, provider_id: str) -> bool:
        credential = db.scalar(
            select(ProviderCredential).where(ProviderCredential.provider == provider_id)
        )
        cls._runtime.pop(provider_id, None)
        if credential is None:
            return False
        db.delete(credential)
        db.commit()
        return True

    # --- Backward-compatible OpenAI-only helpers; prefer save()/remove()/load_all(). ---

    @classmethod
    def save_openai(
        cls, db: Session, *, api_key: str, model: str, settings: Settings | None = None
    ) -> ProviderCredential:
        return cls.save(db, provider_id="openai", api_key=api_key, model=model, settings=settings)

    @classmethod
    def remove_openai(cls, db: Session) -> bool:
        return cls.remove(db, provider_id="openai")

    @classmethod
    def load(cls, db: Session, settings: Settings | None = None) -> ProviderCredential | None:
        return cls.load_all(db, settings).get("openai")
