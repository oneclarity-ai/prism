from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.llm_usage import LLMUsage
from app.services.errors import RuleViolationError

router = APIRouter(prefix="/api/v1/usage/llm", tags=["AI usage"])


def bounds(start: Optional[date], end: Optional[date]):
    zone = ZoneInfo(get_settings().manager_timezone)
    start = start or datetime.now(zone).date()
    end = end or start
    if end < start or (end - start).days > 366:
        raise RuleViolationError("Choose an inclusive date range of at most 366 days")
    return datetime.combine(start, time.min, zone), datetime.combine(end + timedelta(days=1), time.min, zone)


def summary(db, start, end, group=None):
    lower, upper = bounds(start, end)
    columns = [func.count(LLMUsage.id), func.sum(LLMUsage.estimated_total_cost_usd),
               func.count(LLMUsage.estimated_total_cost_usd), func.sum(LLMUsage.input_tokens),
               func.sum(LLMUsage.cached_input_tokens), func.sum(LLMUsage.output_tokens)]
    query = select(*(columns + ([group] if group is not None else []))).where(
        LLMUsage.timestamp >= lower, LLMUsage.timestamp < upper)
    if group is not None:
        query = query.group_by(group).order_by(group)
    result = []
    for row in db.execute(query):
        item = {"calls": row[0], "estimated_cost_usd": str(row[1] or Decimal(0)),
                "unpriced_calls": row[0] - row[2], "input_tokens": row[3] or 0,
                "cached_input_tokens": row[4] or 0, "output_tokens": row[5] or 0,
                "complete": row[0] == row[2], "timezone": get_settings().manager_timezone,
                "from": lower.date(), "to": (upper - timedelta(days=1)).date()}
        if group is not None:
            item["group"] = row[6]
        result.append(item)
    return result if group is not None else result[0]


@router.get("/today")
def today(db: Session = Depends(get_db)):
    return summary(db, None, None)


@router.get("/by-model")
def by_model(start: Optional[date] = Query(None, alias="from"), end: Optional[date] = Query(None, alias="to"), db: Session = Depends(get_db)):
    return summary(db, start, end, LLMUsage.model)


@router.get("/by-feature")
def by_feature(start: Optional[date] = Query(None, alias="from"), end: Optional[date] = Query(None, alias="to"), db: Session = Depends(get_db)):
    return summary(db, start, end, LLMUsage.feature)


@router.get("")
def calls(start: Optional[date] = Query(None, alias="from"), end: Optional[date] = Query(None, alias="to"),
          limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    lower, upper = bounds(start, end)
    rows = db.scalars(select(LLMUsage).where(LLMUsage.timestamp >= lower, LLMUsage.timestamp < upper)
                      .order_by(LLMUsage.timestamp.desc(), LLMUsage.id).limit(limit).offset(offset))
    return {"summary": summary(db, start, end), "limit": limit, "offset": offset,
            "items": [{column.name: getattr(row, column.name) for column in LLMUsage.__table__.columns} for row in rows]}
