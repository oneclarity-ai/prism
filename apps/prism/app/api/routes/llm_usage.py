from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.llm_usage import LLMUsage
from app.services import azure_billing_service
from app.services.errors import RuleViolationError

router = APIRouter(prefix="/api/v1/usage/llm", tags=["AI usage"])


def bounds(start: Optional[date], end: Optional[date]):
    zone = ZoneInfo(get_settings().manager_timezone)
    start = start or datetime.now(zone).date()
    end = end or start
    if end < start or (end - start).days > 366:
        raise RuleViolationError("Choose an inclusive date range of at most 366 days")
    return datetime.combine(start, time.min, zone), datetime.combine(
        end + timedelta(days=1), time.min, zone
    )


SWARM_PROVIDER = (
    "qa_workspace"  # runs the hidden agent swarm did; every other row is Prism's own calls
)
SOURCES = ("prism", "swarm")


def summary(db, start, end, group=None, source=None):
    lower, upper = bounds(start, end)
    columns = [
        func.count(LLMUsage.id),
        func.sum(LLMUsage.estimated_total_cost_usd),
        func.count(LLMUsage.estimated_total_cost_usd),
        func.sum(LLMUsage.input_tokens),
        func.sum(LLMUsage.cached_input_tokens),
        func.sum(LLMUsage.output_tokens),
    ]
    query = select(*(columns + ([group] if group is not None else []))).where(
        LLMUsage.timestamp >= lower, LLMUsage.timestamp < upper
    )
    if source == "swarm":
        query = query.where(LLMUsage.provider == SWARM_PROVIDER)
    elif source == "prism":
        query = query.where(LLMUsage.provider != SWARM_PROVIDER)
    if group is not None:
        query = query.group_by(group).order_by(group)
    result = []
    for row in db.execute(query):
        item = {
            "calls": row[0],
            "estimated_cost_usd": str(row[1] or Decimal(0)),
            "unpriced_calls": row[0] - row[2],
            "input_tokens": row[3] or 0,
            "cached_input_tokens": row[4] or 0,
            "output_tokens": row[5] or 0,
            "complete": row[0] == row[2],
            "timezone": get_settings().manager_timezone,
            "from": lower.date(),
            "to": (upper - timedelta(days=1)).date(),
        }
        if group is not None:
            item["group"] = row[6]
        result.append(item)
    return result if group is not None else result[0]


@router.get("/sources")
def sources(
    period: Literal["today", "week", "month"] = "month",
    db: Session = Depends(get_db),
):
    """Prism's own AI calls and the agent swarm's runs side by side: totals for today, the
    last 7 days, this month and all time, plus breakdowns by feature and by model for `period`."""
    zone = ZoneInfo(get_settings().manager_timezone)
    today_ = datetime.now(zone).date()
    month_start = today_.replace(day=1)
    periods = {
        "today": (today_, today_),
        "week": (today_ - timedelta(days=6), today_),
        "month": (month_start, today_),
        "total": (today_ - timedelta(days=365), today_),
    }
    start, end = periods[period]
    return {
        "timezone": get_settings().manager_timezone,
        "today": today_,
        "range": {"from": start, "to": end},
        "periods": {
            name: {src: summary(db, a, b, source=src) for src in SOURCES}
            for name, (a, b) in periods.items()
        },
        "by_feature": {src: summary(db, start, end, LLMUsage.feature, src) for src in SOURCES},
        "by_model": {src: summary(db, start, end, LLMUsage.model, src) for src in SOURCES},
        "by_provider": summary(db, start, end, LLMUsage.provider),
    }


@router.get("/azure-billed")
def azure_billed(
    start: Optional[date] = Query(None, alias="from"),
    end: Optional[date] = Query(None, alias="to"),
):
    """What Azure itself billed per source, for comparing with the token-based estimate."""
    lower, upper = bounds(start, end)
    return azure_billing_service.billed(lower.date(), (upper - timedelta(days=1)).date())


@router.get("/today")
def today(db: Session = Depends(get_db)):
    return summary(db, None, None)


@router.get("/by-model")
def by_model(
    start: Optional[date] = Query(None, alias="from"),
    end: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    return summary(db, start, end, LLMUsage.model)


@router.get("/by-feature")
def by_feature(
    start: Optional[date] = Query(None, alias="from"),
    end: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    return summary(db, start, end, LLMUsage.feature)


@router.get("")
def calls(
    start: Optional[date] = Query(None, alias="from"),
    end: Optional[date] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    lower, upper = bounds(start, end)
    rows = db.scalars(
        select(LLMUsage)
        .where(LLMUsage.timestamp >= lower, LLMUsage.timestamp < upper)
        .order_by(LLMUsage.timestamp.desc(), LLMUsage.id)
        .limit(limit)
        .offset(offset)
    )
    return {
        "summary": summary(db, start, end),
        "limit": limit,
        "offset": offset,
        "items": [
            {column.name: getattr(row, column.name) for column in LLMUsage.__table__.columns}
            for row in rows
        ],
    }
