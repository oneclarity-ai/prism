from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ARM = "https://management.azure.com"
CACHE_SECONDS = 600  # Cost Management is rate limited and only refreshes every few hours
_lock = threading.Lock()
_token: tuple[str, float] | None = None
_cache: dict[tuple, tuple[float, dict]] = {}


class BillingError(Exception):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(
        s.azure_billing_tenant_id
        and s.azure_billing_client_id
        and s.azure_billing_client_secret
        and s.azure_billing_scopes
    )


def _bearer() -> str:
    global _token
    s = get_settings()
    if _token and _token[1] > time.time() + 60:
        return _token[0]
    response = httpx.post(
        f"https://login.microsoftonline.com/{s.azure_billing_tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": s.azure_billing_client_id,
            "client_secret": s.azure_billing_client_secret.get_secret_value(),
            "scope": f"{ARM}/.default",
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise BillingError("Azure rejected the billing sign-in. Check the service principal.")
    body = response.json()
    _token = (body["access_token"], time.time() + int(body.get("expires_in", 3000)))
    return _token[0]


def _query(scope: str, start: date, end: date) -> dict[str, Any]:
    response = httpx.post(
        f"{ARM}{scope}/providers/Microsoft.CostManagement/query",
        params={"api-version": "2023-11-01"},
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
            "dataset": {
                "granularity": "None",
                "aggregation": {"cost": {"name": "Cost", "function": "Sum"}},
                "grouping": [{"type": "Dimension", "name": "Meter"}],
            },
        },
        timeout=30,
    )
    if response.status_code == 429:
        raise BillingError("Azure is rate limiting billing queries. Try again in a few minutes.")
    if response.status_code != 200:
        raise BillingError(
            f"Azure billing returned {response.status_code} for {scope.split('/')[-1]}."
        )
    return response.json().get("properties", {})


def _parse(properties: dict[str, Any]) -> dict[str, Any]:
    names = [column["name"] for column in properties.get("columns", [])]
    rows = [dict(zip(names, row)) for row in properties.get("rows", [])]
    meters = [
        {"meter": row.get("Meter") or "Other", "cost": float(row.get("Cost") or 0)} for row in rows
    ]
    currency = next((row.get("Currency") for row in rows if row.get("Currency")), None)
    return {
        "cost": round(sum(item["cost"] for item in meters), 6),
        "currency": currency,
        "meters": sorted(meters, key=lambda item: -item["cost"]),
    }


def billed(start: date, end: date) -> dict[str, Any]:
    """What Azure billed per source (prism / swarm) between two dates, inclusive.

    Never raises: a source that can't be read carries an `error`, so the page still renders.
    Azure posts charges with a delay of hours, so today's figure is normally behind the estimate.
    """
    if not configured():
        return {"configured": False, "sources": {}}
    key = (start, end)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
    sources: dict[str, Any] = {}
    for name, scope in get_settings().azure_billing_scopes.items():
        try:
            sources[name] = _parse(_query(scope, start, end))
        except (BillingError, httpx.HTTPError) as exc:
            logger.warning("azure_billing_failed", extra={"source": name, "error": str(exc)})
            sources[name] = {
                "error": str(exc)
                if isinstance(exc, BillingError)
                else "Azure could not be reached."
            }
    result = {
        "configured": True,
        "sources": sources,
        "note": "Azure posts charges hours late, so recent days can read lower than the estimate.",
        "from": start,
        "to": end,
    }
    with _lock:
        _cache[key] = (time.time() + CACHE_SECONDS, result)
    return result
