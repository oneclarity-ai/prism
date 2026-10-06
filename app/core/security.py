"""Minimal V1 protection for operator APIs exposed through a public tunnel."""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings

OPERATOR_TOKEN_HEADER = "X-Manager-Operator-Token"
PUBLIC_API_PATHS = {
    "/health",
    "/health/db",
    "/api/v1/microsoft/auth/start",
    "/api/v1/microsoft/auth/callback",
    "/api/v1/microsoft/teams/webhook",
}


def operator_auth_required() -> bool:
    """Require a token whenever configured or when a public Graph tunnel is enabled.

    Local-only development remains possible before a tunnel is configured. Once a
    public webhook base URL exists, missing operator-token configuration fails
    closed instead of leaving management controls anonymous.
    """

    settings = get_settings()
    return bool(
        settings.operator_api_token
        or settings.microsoft_webhook_base_url
        or settings.app_env.casefold() != "development"
    )


async def protect_operator_api(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path in PUBLIC_API_PATHS:
        return await call_next(request)
    if not operator_auth_required():
        return await call_next(request)

    expected_token = get_settings().operator_api_token
    if not expected_token:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "OPERATOR_API_TOKEN must be configured before exposing management APIs through a public URL",
                "code": "operator_auth_not_configured",
            },
        )
    supplied_token = request.headers.get(OPERATOR_TOKEN_HEADER, "")
    if not hmac.compare_digest(supplied_token, expected_token):
        return JSONResponse(
            status_code=401,
            content={
                "detail": "A valid manager operator token is required",
                "code": "operator_auth_required",
            },
        )
    return await call_next(request)
