import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

INDEX = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
needs_build = pytest.mark.skipif(
    not INDEX.is_file(), reason="Dashboard not built (make frontend-build)"
)


@needs_build
def test_dashboard_is_served() -> None:
    response = TestClient(app).get("/dashboard/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Prism</title>" in response.text
    assert '<div id="root"></div>' in response.text
    assert "fonts.googleapis.com" not in response.text


@needs_build
def test_dashboard_bundles_and_static_assets_are_served() -> None:
    client = TestClient(app)
    html = client.get("/dashboard/").text

    bundles = re.findall(r'(?:src|href)="(/dashboard/assets/[^"]+\.(?:js|css))"', html)
    assert any(path.endswith(".js") for path in bundles)
    assert any(path.endswith(".css") for path in bundles)
    for path in bundles:
        assert client.get(path).status_code == 200, path

    assert client.get("/dashboard/fonts/inter-latin-wght.woff2").status_code == 200
    assert client.get("/dashboard/assets/workspace-icons.svg").status_code == 200


def test_dashboard_without_a_build_explains_how_to_build(monkeypatch, tmp_path) -> None:
    import app.main as main

    monkeypatch.setattr(main.Path, "is_file", lambda self: False)
    response = TestClient(app).get("/chats")

    assert response.status_code == 503
    assert "make frontend-build" in response.json()["detail"]
