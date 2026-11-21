import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.db.enums import AgentStatus
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate, JobDescription, JobDescriptionRequest
from app.services import agents as service
from app.services.ai_writer import job_description

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
async def list_agents(session: SessionDep, user: CurrentUser):
    return await service.list_agents(session, user.org_id)


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, session: SessionDep, user: CurrentUser):
    return await service.create_agent(session, user.org_id, body)


@router.post("/generate-description", response_model=JobDescription)
async def generate_description(body: JobDescriptionRequest, user: CurrentUser):
    """Draft a detailed job description (mission, responsibilities, KPIs, boundaries…) with Azure OpenAI.
    Nothing is saved: the text fills the form, and the user edits it before creating the agent."""
    text, cost = await job_description(body.name, body.role, body.department, body.notes)
    return JobDescription(description=text, cost_usd=round(cost, 5))


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.get_agent(session, user.org_id, agent_id)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(agent_id: uuid.UUID, body: AgentUpdate, session: SessionDep, user: CurrentUser):
    return await service.update_agent(session, user.org_id, agent_id, body)


@router.post("/{agent_id}/pause", response_model=AgentRead)
async def pause_agent(agent_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.set_status(session, user.org_id, agent_id, AgentStatus.paused)


@router.post("/{agent_id}/resume", response_model=AgentRead)
async def resume_agent(agent_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await service.set_status(session, user.org_id, agent_id, AgentStatus.active)
