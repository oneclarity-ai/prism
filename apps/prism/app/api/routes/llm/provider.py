from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.llm.provider_credential import ProviderCredential
from app.schemas.llm.provider import (
    OpenAICredentialUpsert,
    ProviderCredentialSummary,
    ProviderCredentialTestResult,
    ProviderCredentialUpsert,
    ProviderStatusRead,
)
from app.services.errors import NotFoundError, RuleViolationError
from app.services.llm.llm_provider import provider_status, validate_credential
from app.services.llm.provider_credential_service import ProviderCredentialService
from app.services.llm.provider_registry import (
    PROVIDER_BY_ID,
    PROVIDER_REGISTRY,
    ProviderDefinition,
)

router = APIRouter(prefix="/api/v1/provider", tags=["provider"])


def _definition(provider_id: str) -> ProviderDefinition:
    definition = PROVIDER_BY_ID.get(provider_id.strip().casefold())
    if definition is None:
        raise NotFoundError(f"Unknown provider: {provider_id}")
    return definition


def _summary(
    definition: ProviderDefinition,
    row: ProviderCredential | None,
    *,
    active_id: str,
    can_manage: bool,
) -> ProviderCredentialSummary:
    return ProviderCredentialSummary(
        provider=definition.id,
        label=definition.label,
        configured=row is not None,
        is_active_provider=definition.id == active_id,
        model=row.model if row else None,
        masked_key=("••••" + row.key_last_four) if row else None,
        base_url=row.base_url if row else None,
        api_version=row.api_version if row else None,
        needs_base_url=definition.needs_base_url,
        base_url_required=definition.base_url_required,
        needs_api_version=definition.needs_api_version,
        default_model_hint=definition.default_model_hint,
        docs_url=definition.docs_url,
        can_manage=can_manage,
    )


@router.get("/status", response_model=ProviderStatusRead)
def provider_readiness(db: Session = Depends(get_db)) -> ProviderStatusRead:
    """Return safe model readiness metadata without testing or exposing credentials."""

    settings = get_settings()
    rows = ProviderCredentialService.load_all(db, settings)
    effective = ProviderCredentialService.effective_settings(settings)
    safe_status = provider_status(effective)
    active_id = str(safe_status["provider"])
    credential = rows.get(active_id)
    if credential is not None:
        source = "database"
        masked_key = "••••" + credential.key_last_four
    elif effective.llm_provider.strip().casefold() == "codex_local":
        source = "local_login"
        masked_key = None
    else:
        source = "environment"
        masked_key = None
    return ProviderStatusRead.model_validate(
        {
            **safe_status,
            "credential_source": source,
            "masked_key": masked_key,
            "can_manage": bool(settings.credential_encryption_key),
        }
    )


@router.get("/credentials", response_model=list[ProviderCredentialSummary])
def list_provider_credentials(db: Session = Depends(get_db)) -> list[ProviderCredentialSummary]:
    """List every registered provider's BYOK state. Never returns a decrypted key."""

    settings = get_settings()
    active_id = settings.llm_provider.strip().casefold()
    rows = ProviderCredentialService.load_all(db, settings)
    can_manage = bool(settings.credential_encryption_key)
    return [
        _summary(definition, rows.get(definition.id), active_id=active_id, can_manage=can_manage)
        for definition in PROVIDER_REGISTRY
    ]


@router.put("/credentials/{provider_id}", response_model=ProviderCredentialSummary)
def save_provider_credential(
    provider_id: str, payload: ProviderCredentialUpsert, db: Session = Depends(get_db)
) -> ProviderCredentialSummary:
    definition = _definition(provider_id)
    if definition.base_url_required and not (payload.base_url or "").strip():
        raise RuleViolationError(f"{definition.label} requires a base URL / endpoint")
    settings = get_settings()
    ProviderCredentialService.save(
        db,
        provider_id=definition.id,
        api_key=payload.api_key,
        model=payload.model,
        base_url=payload.base_url,
        api_version=payload.api_version,
        settings=settings,
    )
    rows = ProviderCredentialService.load_all(db, settings)
    active_id = settings.llm_provider.strip().casefold()
    return _summary(
        definition,
        rows.get(definition.id),
        active_id=active_id,
        can_manage=bool(settings.credential_encryption_key),
    )


@router.delete("/credentials/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_provider_credential(provider_id: str, db: Session = Depends(get_db)) -> Response:
    definition = _definition(provider_id)
    ProviderCredentialService.remove(db, provider_id=definition.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/credentials/{provider_id}/test", response_model=ProviderCredentialTestResult)
def test_provider_credential(
    provider_id: str, payload: ProviderCredentialUpsert
) -> ProviderCredentialTestResult:
    """Make a free, live "list models" call to confirm the pasted key actually works.

    Tests the credential as typed; it is not saved by this call.
    """

    definition = _definition(provider_id)
    ok, detail = validate_credential(
        provider_id=definition.id,
        api_key=payload.api_key,
        model=payload.model,
        base_url=payload.base_url,
        api_version=payload.api_version,
    )
    return ProviderCredentialTestResult(ok=ok, detail=detail)


# --- Legacy OpenAI-only routes, kept for compatibility. Prefer /credentials/{provider_id}. ---


@router.put("/openai", response_model=ProviderStatusRead)
def save_openai_credential(
    payload: OpenAICredentialUpsert, db: Session = Depends(get_db)
) -> ProviderStatusRead:
    ProviderCredentialService.save_openai(
        db, api_key=payload.api_key, model=payload.model, settings=get_settings()
    )
    return provider_readiness(db)


@router.delete("/openai", status_code=status.HTTP_204_NO_CONTENT)
def remove_openai_credential(db: Session = Depends(get_db)) -> Response:
    ProviderCredentialService.remove_openai(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
