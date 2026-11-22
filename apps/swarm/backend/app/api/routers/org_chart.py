import uuid

from fastapi import APIRouter, status

from app.agents.registry import CATALOG
from app.api.deps import CurrentUser, SessionDep
from app.schemas.common import Message
from app.schemas.org_chart import AgentRoleRead, PositionCreate, PositionRead, PositionUpdate
from app.services import org_chart as service

router = APIRouter(tags=["organization"])


@router.get("/org/positions", response_model=list[PositionRead])
async def list_positions(session: SessionDep, user: CurrentUser):
    return await service.list_positions(session, user.org_id)


@router.post("/org/positions", response_model=PositionRead, status_code=status.HTTP_201_CREATED)
async def create_position(body: PositionCreate, session: SessionDep, user: CurrentUser):
    return await service.create_position(session, user.org_id, body)


@router.patch("/org/positions/{position_id}", response_model=PositionRead)
async def update_position(position_id: uuid.UUID, body: PositionUpdate, session: SessionDep, user: CurrentUser):
    return await service.update_position(session, user.org_id, position_id, body)


@router.delete("/org/positions/{position_id}", response_model=Message)
async def delete_position(position_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    await service.delete_position(session, user.org_id, position_id)
    return Message()


@router.get("/agent-roles", response_model=list[AgentRoleRead])
async def agent_roles(user: CurrentUser):
    """Agent roles defined in code under app/agents/<role>/ (available and planned)."""
    return [
        AgentRoleRead(
            key=d.key,
            name=d.name,
            role=d.role,
            department=d.department,
            description=d.description,
            status=d.status,
            runtime=d.runtime,
        )
        for d in CATALOG
    ]
