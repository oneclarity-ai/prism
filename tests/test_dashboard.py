from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_is_served() -> None:
    response = TestClient(app).get("/dashboard/")

    assert response.status_code == 200
    assert "Prism" in response.text
    assert "Today's AI cost" in response.text
    assert "/dashboard/styles.css" in response.text
    assert "fonts.googleapis.com" not in response.text
    assert "Teams automation" in response.text
    assert "Start automation" in response.text
    assert "Connect Microsoft account" in response.text
    assert "Managed people" in response.text
    assert "Add people from the organization" in response.text
    assert "Teams activity" in response.text
    assert "Run daily cycle" in response.text
    assert "Send digest" in response.text
    assert "toggle-automation-button" in response.text
    assert "stop-automation-button" not in response.text
    assert "Daily manager review" in response.text
    assert "Journey" in response.text
    assert "Preview dummy flow" in response.text
    assert "Agent delivery health" in response.text
    assert "Retry failed replies" in response.text
    assert "Organisational memory" in response.text
    assert "Update memory" in response.text
    assert "My knowledge" in response.text
    assert "Needs your attention" in response.text
    assert "Daily management brief" in response.text
    assert "Ask about the team" in response.text
    assert 'data-tab-target="intelligence"' in response.text
    assert 'data-tab-target="management"' in response.text
    assert 'data-tab-target="journey"' in response.text
    assert 'data-tab-target="memory"' in response.text
    assert 'data-tab-target="knowledge"' in response.text
    assert 'data-tab="management"' in response.text
    assert 'data-tab="knowledge"' in response.text
    assert 'data-tab="memory"' in response.text
    assert 'data-tab="intelligence"' in response.text
    assert "/dashboard/app.js" in response.text


def test_dashboard_static_assets_are_served() -> None:
    client = TestClient(app)

    assert client.get("/dashboard/styles.css").status_code == 200
    script = client.get("/dashboard/app.js")
    assert script.status_code == 200
    assert "distribute-deployment-list" in script.text
    assert "Distribute list" in script.text
