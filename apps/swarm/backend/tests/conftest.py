import os

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://localhost:5432/oneclarity_test")
from cryptography.fernet import Fernet  # noqa: E402

os.environ["SECRET_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret"

import asyncio  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.db.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.enums import UserRole  # noqa: E402
from app.db.models import Organization, User  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import app  # noqa: E402

DB_URL = os.environ["DATABASE_URL"]
ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "test-password"


@pytest.fixture(scope="session", autouse=True)
def schema():
    async def create():
        engine = create_async_engine(DB_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
    yield


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine(DB_URL, poolclass=NullPool)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield maker
    app.dependency_overrides.clear()
    await engine.dispose()
    # The worker code uses the app's global engine; drop its pooled connections between tests
    # because each test runs in its own event loop.
    from app.db.session import engine as app_engine

    await app_engine.dispose()


@pytest.fixture
async def org(sessionmaker):
    async with sessionmaker() as session:
        org = Organization(name="Test Org")
        session.add(org)
        await session.flush()
        session.add(
            User(
                org_id=org.id,
                email=ADMIN_EMAIL,
                name="Admin",
                password_hash=hash_password(ADMIN_PASSWORD),
                role=UserRole.admin,
            )
        )
        await session.commit()
        return org


@pytest.fixture
async def client(sessionmaker):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth_client(client, org):
    response = await client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    assert get_settings().session_cookie_name in response.cookies
    return client


@pytest.fixture
async def qa_agent(auth_client):
    response = await auth_client.post(
        "/api/v1/agents",
        json={"key": "qa-agent", "name": "QA Agent", "role": "qa", "tool_grants": {"file_bug": "ask_first"}},
    )
    assert response.status_code == 201, response.text
    return response.json()
