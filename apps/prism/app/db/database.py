from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import get_settings


def build_engine() -> Engine:
    """Create the synchronous SQLAlchemy engine used by the API and Alembic."""

    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )


engine = build_engine()
