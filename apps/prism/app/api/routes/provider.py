from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.provider import OpenAICredentialUpsert, ProviderStatusRead
from app.services.llm_provider import provider_status
from app.services.provider_credential_service import ProviderCredentialService

router = APIRouter(prefix="/api/v1/provider", tags=["provider"])


@router.get("/status", response_model=ProviderStatusRead)
def provider_readiness(db: Session = Depends(get_db)) -> ProviderStatusRead:
    """Return safe model readiness metadata without testing or exposing credentials."""

    settings = get_settings()
    credential = ProviderCredentialService.load(db, settings)
    effective = ProviderCredentialService.effective_settings(settings)
    safe_status = provider_status(effective)
    if credential is not None:
        source = "database"
        masked_key = "••••" + credential.key_last_four
    elif effective.llm_provider == "codex_local":
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
