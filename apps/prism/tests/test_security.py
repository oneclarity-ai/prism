from types import SimpleNamespace

from app.core import security


def test_operator_auth_is_optional_only_for_unexposed_development(monkeypatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="development",
            microsoft_webhook_base_url=None,
            operator_api_token=None,
        ),
    )

    assert security.operator_auth_required() is False


def test_operator_auth_fails_closed_outside_development(monkeypatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="production",
            microsoft_webhook_base_url=None,
            operator_api_token=None,
        ),
    )

    assert security.operator_auth_required() is True


def test_public_webhook_url_requires_operator_auth(monkeypatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="development",
            microsoft_webhook_base_url="https://example.invalid",
            operator_api_token=None,
        ),
    )

    assert security.operator_auth_required() is True
