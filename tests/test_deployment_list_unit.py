import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.enums import TaskStatus
from app.services.deployment_list_service import DeploymentListService
from app.services.errors import ExternalServiceError, RuleViolationError
from app.services.microsoft_service import MicrosoftService


def test_deployment_list_parser_groups_tasks_and_normalizes_statuses() -> None:
    parsed = DeploymentListService.parse(
        "Vaibhav\n\nFix feedback page. [ DONE ]\nShip inbox icon. [ IN PROGRESS ]\n\nShivam Bhalerao\n\nTest Super Admin. [ TO DO ]"
    )

    assert list(parsed) == ["Vaibhav", "Shivam Bhalerao"]
    assert [item.status for item in parsed["Vaibhav"]] == [TaskStatus.DONE, TaskStatus.IN_PROGRESS]
    assert parsed["Shivam Bhalerao"][0].title == "Test Super Admin"
    assert parsed["Shivam Bhalerao"][0].status == TaskStatus.TODO


class _FakeDb:
    def __init__(self, scalar_values):
        self.scalar_values = iter(scalar_values)
        self.rollbacks = 0

    def scalar(self, _statement):
        return next(self.scalar_values)

    def rollback(self):
        self.rollbacks += 1


def test_distribution_rejects_owner_outside_active_run_before_sending(monkeypatch) -> None:
    entry = SimpleNamespace(
        id=uuid.uuid4(), title="Deployment List (test)",
        content="Shivam Bhalerao\nValidate test deployment. [ IN PROGRESS ]",
    )
    owner = SimpleNamespace(id=uuid.uuid4(), name="Shivam Bhalerao")
    db = _FakeDb([entry])
    monkeypatch.setattr(DeploymentListService, "resolve_people", staticmethod(
        lambda *_args: {owner.name: owner}
    ))
    monkeypatch.setattr(MicrosoftService, "active_run", staticmethod(
        lambda _db: SimpleNamespace(target_employee_ids=[])
    ))
    monkeypatch.setattr(MicrosoftService, "send_management_message", staticmethod(
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not send"))
    ))

    with pytest.raises(RuleViolationError, match="outside the active automation run"):
        DeploymentListService.distribute(db, entry.id)


def test_distribution_failure_does_not_sync_task_state(monkeypatch) -> None:
    entry = SimpleNamespace(
        id=uuid.uuid4(), title="Deployment List (test)", updated_at=datetime.now(timezone.utc),
        content="Shivam Bhalerao\nValidate test deployment. [ IN PROGRESS ]",
    )
    owner = SimpleNamespace(id=uuid.uuid4(), name="Shivam Bhalerao")
    db = _FakeDb([entry, None])
    sync_calls = []
    monkeypatch.setattr(DeploymentListService, "resolve_people", staticmethod(
        lambda *_args: {owner.name: owner}
    ))
    monkeypatch.setattr(DeploymentListService, "sync_tasks", staticmethod(
        lambda *_args: sync_calls.append(True) or 1
    ))
    monkeypatch.setattr(MicrosoftService, "active_run", staticmethod(
        lambda _db: SimpleNamespace(target_employee_ids=[str(owner.id)])
    ))
    monkeypatch.setattr(MicrosoftService, "follow_up_message_for", staticmethod(
        lambda _name, content: content
    ))
    monkeypatch.setattr(MicrosoftService, "send_management_message", staticmethod(
        lambda *_args: (_ for _ in ()).throw(ExternalServiceError("simulated failure"))
    ))

    result = DeploymentListService.distribute(db, entry.id)

    assert result["task_changes"] == 0
    assert result["delivered"] == []
    assert result["failures"][0]["employee"] == owner.name
    assert sync_calls == []
    assert db.rollbacks == 1
