async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers


async def test_health_db(client):
    response = await client.get("/api/v1/health/db")
    assert response.json() == {"status": "ok"}


async def test_login_wrong_password(client, org):
    response = await client.post("/api/v1/auth/login", json={"email": "admin@test.local", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_requires_login(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_and_logout(auth_client):
    me = await auth_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@test.local"
    assert "password_hash" not in me.json()

    await auth_client.post("/api/v1/auth/logout")
    auth_client.cookies.clear()
    assert (await auth_client.get("/api/v1/auth/me")).status_code == 401


async def test_bearer_token_also_works(client, org):
    login = await client.post("/api/v1/auth/login", json={"email": "admin@test.local", "password": "test-password"})
    token = login.cookies["oc_session"]
    client.cookies.clear()
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


async def test_validation_error_shape(client):
    response = await client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unexpected_error_is_logged_and_hidden(client):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async def boom():
        raise RuntimeError("database exploded with password=hunter2")

    app.add_api_route("/api/v1/_boom", boom)
    try:
        async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t") as c:
            response = await c.get("/api/v1/_boom")
        assert response.status_code == 500
        body = response.json()["error"]
        assert body["code"] == "internal_error"
        assert "hunter2" not in response.text
        assert "request id" in body["message"]
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/api/v1/_boom"]
