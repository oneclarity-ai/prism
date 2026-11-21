"""Optional embedding boundary; memory remains useful with PostgreSQL full-text search alone."""

from __future__ import annotations

from typing import Optional

from app.core.config import Settings, get_settings


class EmbeddingProvider:
    @staticmethod
    def is_configured(settings: Optional[Settings] = None) -> bool:
        resolved = settings or get_settings()
        return bool(
            resolved.memory_embeddings_enabled
            and resolved.azure_openai_endpoint
            and resolved.azure_openai_api_key
            and resolved.azure_openai_embedding_deployment
        )

    @staticmethod
    def status(settings: Optional[Settings] = None) -> str:
        return "configured" if EmbeddingProvider.is_configured(settings) else "disabled"
