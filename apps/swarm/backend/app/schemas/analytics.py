from typing import Any

from pydantic import BaseModel


class AnalyticsRead(BaseModel):
    period_days: int
    totals: dict[str, Any]
    by_day: list[dict[str, Any]]
    by_agent: list[dict[str, Any]]
    by_model: list[dict[str, Any]]
    by_status: list[dict[str, Any]]
    tests_by_status: list[dict[str, Any]]
    bugs_by_severity: list[dict[str, Any]]
    bugs_by_status: list[dict[str, Any]]


class BugListItem(BaseModel):
    id: str
    title: str
    severity: str
    status: str
    steps: str
    expected: str
    actual: str
    external_url: str | None
    created_at: str
    run_id: str
    task_id: str
    task_title: str
    target_name: str | None
    model: str | None
