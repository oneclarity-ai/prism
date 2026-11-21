import pytest
from fastapi.testclient import TestClient

from app.core.dashboard_routes import is_dashboard_path
from app.main import app


@pytest.mark.parametrize(
    "path",
    [
        "spending",
        "run-analytics",
        "prisms/pA7xQ2",
        "prisms/pA7xQ2/settings/skills",
        "prisms/PR-12",
        "prisms/PR-12/settings/skills",
        "settings/preferences",
        "runs/12345678-1234-1234-1234-123456789abc",
    ],
)
def test_deep_links_serve_the_dashboard_document(path):
    response = TestClient(app).get(f"/{path}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/dashboard/js/navigation.js" in response.text
    assert "/dashboard/css/styles.css" in response.text


@pytest.mark.parametrize(
    "path",
    [
        "api/unknown-route",
        "settings/unknown",
        "prisms/not-a-code",
        "prisms/pShort7",
        "prisms/pAb12",
        "prisms/PA7xQ2",
        "dashboard/missing.js",
        ".env",
        "anything-else",
    ],
)
def test_unknown_files_and_api_paths_do_not_become_html(path):
    assert not is_dashboard_path(path)
    response = TestClient(app).get(f"/{path}")
    assert response.status_code == 404
    assert not response.headers.get("content-type", "").startswith("text/html")
