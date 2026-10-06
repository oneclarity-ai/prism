"""PostgreSQL-backed dependency graph projection and traversal."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blocker import Blocker
from app.models.employee import Employee
from app.models.enums import BlockerStatus
from app.models.intelligence import DependencyEdge
from app.models.message import Message
from app.models.project import Project
from app.models.response_state import BlockerDependency
from app.models.task import Task
from app.schemas.intelligence import DependencyEdgeCreate, DependencyEdgeRead, DependencyGraphRead
from app.services.errors import NotFoundError, RuleViolationError


class DependencyGraphService:
    ENTITY_MODELS = {"employee": Employee, "task": Task, "project": Project}

    @staticmethod
    def create(db: Session, data: DependencyEdgeCreate) -> DependencyEdge:
        DependencyGraphService._validate_entity(db, data.source_entity_type, data.source_entity_id)
        DependencyGraphService._validate_entity(db, data.target_entity_type, data.target_entity_id)
        if data.blocker_id and db.get(Blocker, data.blocker_id) is None:
            raise NotFoundError("Blocker was not found")
        if data.source_message_id and db.get(Message, data.source_message_id) is None:
            raise NotFoundError("Source message was not found")
        existing = db.scalar(
            select(DependencyEdge).where(
                DependencyEdge.source_entity_type == data.source_entity_type,
                DependencyEdge.source_entity_id == data.source_entity_id,
                DependencyEdge.target_entity_type == data.target_entity_type,
                DependencyEdge.target_entity_id == data.target_entity_id,
                DependencyEdge.status == "active",
            )
        )
        if existing:
            return existing
        edge = DependencyEdge(
            **data.model_dump(),
            relation_type="depends_on",
            status="active",
            valid_from=datetime.now(timezone.utc),
        )
        db.add(edge)
        db.commit()
        db.refresh(edge)
        return edge

    @staticmethod
    def resolve(db: Session, edge_id: uuid.UUID) -> DependencyEdge:
        edge = db.get(DependencyEdge, edge_id)
        if edge is None:
            raise NotFoundError("Dependency edge was not found")
        if edge.status != "active":
            raise RuleViolationError("Only an active dependency can be resolved")
        edge.status = "resolved"
        edge.valid_until = datetime.now(timezone.utc)
        db.commit()
        db.refresh(edge)
        return edge

    @staticmethod
    def reopen(db: Session, edge_id: uuid.UUID) -> DependencyEdge:
        edge = db.get(DependencyEdge, edge_id)
        if edge is None:
            raise NotFoundError("Dependency edge was not found")
        if edge.status != "resolved":
            raise RuleViolationError("Only a resolved dependency can be reopened")
        reopened = DependencyEdge(
            source_entity_type=edge.source_entity_type,
            source_entity_id=edge.source_entity_id,
            target_entity_type=edge.target_entity_type,
            target_entity_id=edge.target_entity_id,
            relation_type=edge.relation_type,
            status="active",
            blocker_id=edge.blocker_id,
            task_id=edge.task_id,
            project_id=edge.project_id,
            source_message_id=edge.source_message_id,
            reopened_from_id=edge.id,
            valid_from=datetime.now(timezone.utc),
            confidence=edge.confidence,
        )
        db.add(reopened)
        db.commit()
        db.refresh(reopened)
        return reopened

    @staticmethod
    def graph(db: Session, *, include_resolved: bool = False) -> DependencyGraphRead:
        edges = DependencyGraphService.edges(db, include_resolved=include_resolved)
        return DependencyGraphRead(edges=edges, cycles=DependencyGraphService._cycles(edges))

    @staticmethod
    def edges(db: Session, *, include_resolved: bool = False) -> list[DependencyEdgeRead]:
        result: list[DependencyEdgeRead] = []
        persisted = select(DependencyEdge)
        blockers = select(Blocker)
        if not include_resolved:
            persisted = persisted.where(DependencyEdge.status == "active")
            blockers = blockers.where(Blocker.status == BlockerStatus.OPEN)
        for edge in db.scalars(persisted.order_by(DependencyEdge.valid_from)):
            result.append(
                DependencyEdgeRead(
                    id=edge.id,
                    source_entity_type=edge.source_entity_type,
                    source_entity_id=edge.source_entity_id,
                    target_entity_type=edge.target_entity_type,
                    target_entity_id=edge.target_entity_id,
                    relation_type=edge.relation_type,
                    status=edge.status,
                    blocker_id=edge.blocker_id,
                    task_id=edge.task_id,
                    project_id=edge.project_id,
                    valid_from=edge.valid_from,
                    valid_until=edge.valid_until,
                    confidence=edge.confidence,
                    reopened_from_id=edge.reopened_from_id,
                    evidence=(
                        [f"message:{edge.source_message_id}"] if edge.source_message_id else []
                    ),
                )
            )
        existing = {
            (
                edge.source_entity_type,
                edge.source_entity_id,
                edge.target_entity_type,
                edge.target_entity_id,
                edge.blocker_id,
            )
            for edge in result
        }
        for blocker in db.scalars(blockers.order_by(Blocker.created_at)):
            owner_ids = list(
                db.scalars(
                    select(BlockerDependency.employee_id).where(
                        BlockerDependency.blocker_id == blocker.id,
                        BlockerDependency.is_active.is_(True),
                    )
                )
            ) or ([blocker.dependency_owner_id] if blocker.dependency_owner_id else [])
            for owner_id in owner_ids:
                key = ("employee", blocker.blocked_employee_id, "employee", owner_id, blocker.id)
                if owner_id is None or key in existing:
                    continue
                result.append(
                    DependencyEdgeRead(
                        id=blocker.id,
                        source_entity_type="employee",
                        source_entity_id=blocker.blocked_employee_id,
                        target_entity_type="employee",
                        target_entity_id=owner_id,
                        status="active" if blocker.status == BlockerStatus.OPEN else "resolved",
                        blocker_id=blocker.id,
                        task_id=blocker.task_id,
                        valid_from=blocker.created_at or datetime.now(timezone.utc),
                        valid_until=blocker.resolved_at,
                        confidence=1.0,
                        evidence=[f"blocker:{blocker.id}"],
                    )
                )
        return result

    @staticmethod
    def _validate_entity(db: Session, entity_type: str, entity_id: uuid.UUID) -> None:
        model = DependencyGraphService.ENTITY_MODELS.get(entity_type)
        if model is None or db.get(model, entity_id) is None:
            raise NotFoundError(f"{entity_type.title()} was not found")

    @staticmethod
    def affected_by(
        db: Session, entity_type: str, entity_id: uuid.UUID, *, max_depth: int = 8
    ) -> list[dict]:
        edges = DependencyGraphService.edges(db)
        reverse: dict[tuple[str, uuid.UUID], list[DependencyEdgeRead]] = {}
        for edge in edges:
            reverse.setdefault((edge.target_entity_type, edge.target_entity_id), []).append(edge)
        queue = [((entity_type, entity_id), 0)]
        seen = {(entity_type, entity_id)}
        affected = []
        while queue:
            node, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for edge in reverse.get(node, []):
                source = (edge.source_entity_type, edge.source_entity_id)
                if source in seen:
                    continue
                seen.add(source)
                affected.append(
                    {
                        "entity_type": source[0],
                        "id": str(source[1]),
                        "depth": depth + 1,
                        "via_blocker_id": str(edge.blocker_id) if edge.blocker_id else None,
                    }
                )
                queue.append((source, depth + 1))
        return affected

    @staticmethod
    def _cycles(edges: list[DependencyEdgeRead]) -> list[list[str]]:
        graph: dict[str, list[str]] = {}
        for edge in edges:
            source = f"{edge.source_entity_type}:{edge.source_entity_id}"
            target = f"{edge.target_entity_type}:{edge.target_entity_id}"
            graph.setdefault(source, []).append(target)
        cycles: set[tuple[str, ...]] = set()

        def visit(node: str, path: list[str], active: set[str]) -> None:
            if node in active:
                start = path.index(node)
                cycle = path[start:] + [node]
                rotations = [
                    tuple(cycle[i:-1] + cycle[:i] + [cycle[i]]) for i in range(len(cycle) - 1)
                ]
                cycles.add(min(rotations))
                return
            if len(path) >= 10:
                return
            active.add(node)
            for target in graph.get(node, []):
                visit(target, path + [target], active)
            active.remove(node)

        for node in graph:
            visit(node, [node], set())
        return [list(value) for value in sorted(cycles)]
