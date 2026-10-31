from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.provider_credential import ProviderCredential
from app.services.provider_credential_service import ProviderCredentialService


def test_openai_byok_is_encrypted_masked_activated_and_removed() -> None:
    encryption_key = Fernet.generate_key().decode("utf-8")
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
        APP_ENV="development",
        INTELLIGENCE_LLM_ENABLED=True,
        LLM_PROVIDER="codex_local",
        PROVIDER_CREDENTIAL_ENCRYPTION_KEY=encryption_key,
    )
    api_key = "test-openai-key-with-enough-length-1234"
    try:
        with SessionLocal() as db:
            db.execute(delete(ProviderCredential).where(ProviderCredential.provider == "openai"))
            db.commit()
            stored = ProviderCredentialService.save_openai(
                db, api_key=api_key, model="test-model", settings=settings
            )
            assert stored.key_last_four == "1234"
            assert api_key not in stored.encrypted_api_key

            effective = ProviderCredentialService.effective_settings(settings)
            assert effective.llm_provider == "openai"
            assert effective.llm_model == "test-model"
            assert effective.openai_api_key == api_key

            ProviderCredentialService._runtime_openai = None
            loaded = ProviderCredentialService.load(db, settings)
            assert loaded is not None
            assert ProviderCredentialService.effective_settings(settings).openai_api_key == api_key

            assert ProviderCredentialService.remove_openai(db) is True
            assert (
                db.scalar(select(ProviderCredential).where(ProviderCredential.provider == "openai"))
                is None
            )
            assert (
                ProviderCredentialService.effective_settings(settings).llm_provider == "codex_local"
            )
    finally:
        ProviderCredentialService._runtime_openai = None
