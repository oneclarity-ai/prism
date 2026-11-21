import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.db.enums import AgentStatus
from app.db.models import Agent
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services.common import apply_updates, get_owned


async def list_agents(session: AsyncSession, org_id: uuid.UUID) -> list[Agent]:
    rows = await session.scalars(select(Agent).where(Agent.org_id == org_id).order_by(Agent.created_at))
    return list(rows)


async def get_agent(session: AsyncSession, org_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    return await get_owned(session, Agent, agent_id, org_id)


async def _check_manager(session: AsyncSession, org_id: uuid.UUID, reports_to_id: uuid.UUID | None) -> None:
    if reports_to_id is not None:
        await get_owned(session, Agent, reports_to_id, org_id)


async def create_agent(session: AsyncSession, org_id: uuid.UUID, data: AgentCreate) -> Agent:
    exists = await session.scalar(select(Agent.id).where(Agent.org_id == org_id, Agent.key == data.key))
    if exists:
        raise Conflict(f"Agent key '{data.key}' already exists")
    await _check_manager(session, org_id, data.reports_to_id)
    agent = Agent(org_id=org_id, **data.model_dump())
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def update_agent(session: AsyncSession, org_id: uuid.UUID, agent_id: uuid.UUID, data: AgentUpdate) -> Agent:
    agent = await get_agent(session, org_id, agent_id)
    changes = data.model_dump(exclude_unset=True)
    if "reports_to_id" in changes:
        if changes["reports_to_id"] == agent.id:
            raise Conflict("An agent cannot report to itself")
        await _check_manager(session, org_id, changes["reports_to_id"])
    apply_updates(agent, changes)
    await session.commit()
    await session.refresh(agent)
    return agent


async def set_status(session: AsyncSession, org_id: uuid.UUID, agent_id: uuid.UUID, status: AgentStatus) -> Agent:
    agent = await get_agent(session, org_id, agent_id)
    agent.status = status
    await session.commit()
    await session.refresh(agent)
    return agent
