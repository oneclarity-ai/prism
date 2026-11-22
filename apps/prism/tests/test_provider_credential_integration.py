from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.llm.provider_credential import ProviderCredential
from app.services.llm.provider_credential_service import ProviderCredentialService


def _clear(db, *provider_ids: str) -> None:
    db.execute(delete(ProviderCredential).where(ProviderCredential.provider.in_(provider_ids)))
    db.commit()


def test_openai_byok_is_encrypted_masked_activated_and_removed() -> None:
    encryption_key = Fernet.generate_key().decode("utf-8")
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        APP_ENV="development",
        INTELLIGENCE_LLM_ENABLED=True,
        LLM_PROVIDER="openai",
        PROVIDER_CREDENTIAL_ENCRYPTION_KEY=encryption_key,
    )
    api_key = "test-openai-key-with-enough-length-1234"
    try:
        with SessionLocal() as db:
            _clear(db, "openai")
            stored = ProviderCredentialService.save_openai(
                db, api_key=api_key, model="test-model", settings=settings
            )
            assert stored.key_last_four == "1234"
            assert api_key not in stored.encrypted_api_key

            # Saving supplies the key for the already-active provider; it never switches
            # which provider LLM_PROVIDER names.
            effective = ProviderCredentialService.effective_settings(settings)
            assert effective.llm_provider == "openai"
            assert effective.llm_model == "test-model"
            assert effective.openai_api_key == api_key

            ProviderCredentialService._runtime = {}
            loaded = ProviderCredentialService.load(db, settings)
            assert loaded is not None
            assert ProviderCredentialService.effective_settings(settings).openai_api_key == api_key

            assert ProviderCredentialService.remove_openai(db) is True
            assert (
                db.scalar(select(ProviderCredential).where(ProviderCredential.provider == "openai"))
                is None
            )
            assert ProviderCredentialService.effective_settings(settings).openai_api_key is None
    finally:
        ProviderCredentialService._runtime = {}


def test_byok_only_activates_for_the_provider_llm_provider_selects() -> None:
    """Saving a key for a provider that is not currently active must not be used."""

    encryption_key = Fernet.generate_key().decode("utf-8")
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        APP_ENV="development",
        INTELLIGENCE_LLM_ENABLED=True,
        LLM_PROVIDER="codex_local",
        PROVIDER_CREDENTIAL_ENCRYPTION_KEY=encryption_key,
    )
    try:
        with SessionLocal() as db:
            _clear(db, "anthropic")
            ProviderCredentialService.save(
                db,
                provider_id="anthropic",
                api_key="sk-ant-stored-but-inactive-0000000000",
                model="claude-sonnet-5-5",
                settings=settings,
            )
            effective = ProviderCredentialService.effective_settings(settings)
            # LLM_PROVIDER is still codex_local: the stored Anthropic key is not applied.
            assert effective.llm_provider == "codex_local"
            assert effective.anthropic_api_key is None

            ProviderCredentialService.remove(db, provider_id="anthropic")
    finally:
        ProviderCredentialService._runtime = {}


def test_azure_openai_byok_stores_endpoint_and_api_version() -> None:
    encryption_key = Fernet.generate_key().decode("utf-8")
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        APP_ENV="development",
        INTELLIGENCE_LLM_ENABLED=True,
        LLM_PROVIDER="azure_openai",
        PROVIDER_CREDENTIAL_ENCRYPTION_KEY=encryption_key,
    )
    try:
        with SessionLocal() as db:
            _clear(db, "azure_openai")
            ProviderCredentialService.save(
                db,
                provider_id="azure_openai",
                api_key="azure-byok-key-with-enough-length-0000",
                model="gpt-5-nano",
                base_url="https://example.openai.azure.com",
                api_version="2024-10-21",
                settings=settings,
            )
            effective = ProviderCredentialService.effective_settings(settings)
            assert effective.azure_openai_api_key == "azure-byok-key-with-enough-length-0000"
            assert effective.azure_openai_endpoint == "https://example.openai.azure.com"
            assert effective.azure_openai_api_version == "2024-10-21"
            assert effective.llm_model == "gpt-5-nano"

            ProviderCredentialService.remove(db, provider_id="azure_openai")
    finally:
        ProviderCredentialService._runtime = {}
