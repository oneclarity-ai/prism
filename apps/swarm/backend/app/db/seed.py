"""Create the first organization, admin user, available agents, demo target/task and a starter org chart.

Run: `uv run python -m app.db.seed`.

Safe to run more than once: existing rows are left as they are.
"""

import asyncio

from sqlalchemy import select

from app.agents import registry as agent_roles
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.enums import UserRole
from app.db.models import Agent, Organization, OrgPosition, TargetApp, Task, User
from app.db.session import SessionLocal, engine
from app.schemas.target import TargetCreate, TestLogin
from app.services.targets import create_target

DEMO_TARGET = "Demo Shop (eval app)"
DEMO_TASK = "Full regression of Demo Shop"
# Starter org chart: (title, level, department, holder_type, holder_name, agent_key, children)
ORG_CHART = (
    "Chief Executive Officer",
    "ceo",
    "Leadership",
    "human",
    "CEO",
    None,
    [
        (
            "Chief Technology Officer",
            "executive",
            "Technology",
            "vacant",
            "",
            None,
            [
                (
                    "Engineering Manager",
                    "senior_manager",
                    "Technology",
                    "vacant",
                    "",
                    None,
                    [
                        (
                            "QA Manager",
                            "manager",
                            "Technology",
                            "vacant",
                            "",
                            None,
                            [
                                ("QA Agent", "member", "Technology", "agent", "", "qa-agent", []),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        (
            "VP Sales",
            "executive",
            "Sales",
            "vacant",
            "",
            None,
            [
                (
                    "Sales Manager",
                    "manager",
                    "Sales",
                    "vacant",
                    "",
                    None,
                    [
                        ("Sales SDR Agent", "member", "Sales", "vacant", "", "sales-sdr-agent", []),
                    ],
                ),
            ],
        ),
        (
            "Chief Marketing Officer",
            "executive",
            "Marketing",
            "vacant",
            "",
            None,
            [
                (
                    "Marketing Manager",
                    "manager",
                    "Marketing",
                    "vacant",
                    "",
                    None,
                    [
                        ("Marketing Content Agent", "member", "Marketing", "vacant", "", "marketing-content-agent", []),
                    ],
                ),
            ],
        ),
        (
            "Head of Customer Success",
            "executive",
            "Customer Success",
            "vacant",
            "",
            None,
            [
                (
                    "Support Manager",
                    "manager",
                    "Customer Success",
                    "vacant",
                    "",
                    None,
                    [
                        ("Customer Support Agent", "member", "Customer Success", "vacant", "", "support-agent", []),
                    ],
                ),
            ],
        ),
    ],
)


async def _seed_org_chart(session, org_id) -> None:
    if await session.scalar(select(OrgPosition.id).where(OrgPosition.org_id == org_id).limit(1)):
        return
    agents = {a.key: a.id for a in await session.scalars(select(Agent).where(Agent.org_id == org_id))}

    async def add(node, parent_id, order):
        title, level, dept, holder, name, agent_key, children = node
        agent_id = agents.get(agent_key) if holder == "agent" else None
        pos = OrgPosition(
            org_id=org_id,
            parent_id=parent_id,
            title=title,
            level=level,
            department=dept,
            holder_type=holder if (holder != "agent" or agent_id) else "vacant",
            holder_name=name,
            agent_id=agent_id,
            planned_agent_key=agent_key,
            sort_order=order,
        )
        session.add(pos)
        await session.flush()
        for i, child in enumerate(children):
            await add(child, pos.id, i)

    await add(ORG_CHART, None, 0)
    print("created starter org chart")


async def seed() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        org = await session.scalar(select(Organization).order_by(Organization.created_at).limit(1))
        if org is None:
            org = Organization(name="OneClarity")
            session.add(org)
            await session.flush()
            print(f"created organization {org.id}")

        admin = await session.scalar(select(User).where(User.email == settings.seed_admin_email))
        if admin is None:
            session.add(
                User(
                    org_id=org.id,
                    email=settings.seed_admin_email,
                    name="Admin",
                    password_hash=hash_password(settings.seed_admin_password),
                    role=UserRole.admin,
                )
            )
            print(f"created admin {settings.seed_admin_email}")

        for definition in agent_roles.available():
            exists = await session.scalar(select(Agent.id).where(Agent.org_id == org.id, Agent.key == definition.key))
            if exists:
                continue
            session.add(
                Agent(
                    org_id=org.id,
                    key=definition.key,
                    name=definition.name,
                    role=definition.role,
                    description=definition.description,
                    instructions=definition.instructions,
                    runtime=definition.runtime,
                    model=settings.azure_openai_deployment,
                    tool_grants=dict(definition.tool_grants),
                    max_turns=definition.max_turns,
                    run_budget_usd=definition.run_budget_usd,
                    monthly_budget_usd=definition.monthly_budget_usd,
                )
            )
            print(f"created agent {definition.key}")
        await session.commit()

        # Demo target (eval-app/, served on :4000 by scripts/dev.sh) and a ready-to-run task.
        demo = await session.scalar(select(TargetApp).where(TargetApp.org_id == org.id, TargetApp.name == DEMO_TARGET))
        if demo is None:
            demo = await create_target(
                session,
                org.id,
                TargetCreate(
                    name=DEMO_TARGET,
                    base_url="http://localhost:4000",
                    environment="local",
                    test_login=TestLogin(username="demo@shop.test", password="demo123"),
                    notes="Practice app with known bugs. Safe to submit any form; no real orders or emails.",
                ),
            )
            print("created target Demo Shop")
        qa = await session.scalar(select(Agent).where(Agent.org_id == org.id, Agent.key == "qa-agent"))
        if not await session.scalar(select(Task.id).where(Task.org_id == org.id, Task.title == DEMO_TASK)):
            session.add(
                Task(
                    org_id=org.id,
                    title=DEMO_TASK,
                    goal="Find functional bugs on every page of Demo Shop before release.",
                    agent_id=qa.id,
                    target_app_id=demo.id,
                    scope={
                        "urls": ["/index.html", "/login.html", "/signup.html", "/shop.html", "/contact.html"],
                        "features": ["Search", "Log in", "Sign up", "Cart total", "Contact form", "Log out"],
                        "acceptance_criteria": [
                            "Given a wrong password, when I log in, then I see an error and stay logged out",
                            "Given quantity 12, when I view the total, then it is 12 x $12.50",
                        ],
                        "allow_bug_filing": True,
                    },
                )
            )
            print("created task for Demo Shop")
        await session.commit()

        await _seed_org_chart(session, org.id)
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
