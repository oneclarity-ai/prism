from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/", summary="Application status")
def root() -> dict[str, str]:
    settings = get_settings()
    return {"name": settings.app_name, "status": "ok"}


@router.get("/health", summary="API health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/health/db", summary="Database health")
def database_health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
    return {"status": "healthy", "database": "connected"}
