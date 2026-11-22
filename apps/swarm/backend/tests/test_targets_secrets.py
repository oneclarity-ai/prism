import json

from sqlalchemy import select

from app.core.security import decrypt_secret
from app.db.models import Secret, TargetApp


async def test_secret_values_never_returned(auth_client):
    created = await auth_client.post("/api/v1/secrets", json={"name": "github-token", "value": "ghp_supersecret"})
    assert created.status_code == 201
    assert "value" not in created.json()
    assert "ghp_supersecret" not in created.text

    listed = await auth_client.get("/api/v1/secrets")
    assert [s["name"] for s in listed.json()] == ["github-token"]
    assert "ghp_supersecret" not in listed.text

    dup = await auth_client.post("/api/v1/secrets", json={"name": "github-token", "value": "x"})
    assert dup.status_code == 409

    deleted = await auth_client.delete(f"/api/v1/secrets/{created.json()['id']}")
    assert deleted.status_code == 200
    assert (await auth_client.get("/api/v1/secrets")).json() == []


async def test_secret_is_encrypted_at_rest(auth_client, sessionmaker):
    await auth_client.post("/api/v1/secrets", json={"name": "k", "value": "plain-value"})
    async with sessionmaker() as session:
        secret = await session.scalar(select(Secret))
        assert secret.encrypted_value != "plain-value"
        assert decrypt_secret(secret.encrypted_value) == "plain-value"


async def test_target_with_test_login(auth_client, sessionmaker):
    created = await auth_client.post(
        "/api/v1/targets",
        json={
            "name": "Eval app",
            "base_url": "http://localhost:3000",
            "environment": "local",
            "test_login": {"username": "qa@example.com", "password": "pw-123"},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["has_test_login"] is True
    assert "pw-123" not in created.text

    async with sessionmaker() as session:
        target = await session.get(TargetApp, body["id"])
        secret = await session.get(Secret, target.auth_secret_id)
        assert json.loads(decrypt_secret(secret.encrypted_value)) == {
            "username": "qa@example.com",
            "password": "pw-123",
        }

    cleared = await auth_client.patch(f"/api/v1/targets/{body['id']}", json={"clear_test_login": True})
    assert cleared.json()["has_test_login"] is False
    async with sessionmaker() as session:
        assert (await session.scalars(select(Secret))).all() == []


async def test_target_crud_and_validation(auth_client):
    bad = await auth_client.post("/api/v1/targets", json={"name": "x", "base_url": "not a url"})
    assert bad.status_code == 422

    created = await auth_client.post(
        "/api/v1/targets", json={"name": "Shop", "base_url": "https://staging.example.com"}
    )
    target_id = created.json()["id"]
    assert created.json()["environment"] == "staging"

    updated = await auth_client.patch(f"/api/v1/targets/{target_id}", json={"notes": "Use test card 4242"})
    assert updated.json()["notes"] == "Use test card 4242"

    assert len((await auth_client.get("/api/v1/targets")).json()) == 1
    assert (await auth_client.delete(f"/api/v1/targets/{target_id}")).status_code == 200
    assert (await auth_client.get(f"/api/v1/targets/{target_id}")).status_code == 404
