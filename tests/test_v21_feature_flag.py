from app.core.config import Settings

DATABASE_URL = "postgresql+psycopg://prism:test@localhost:5432/prism_test"


def test_v21_feature_flag_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None, DATABASE_URL=DATABASE_URL)

    assert settings.prism_v21_enabled is False


def test_v21_feature_flag_can_be_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_V21_ENABLED", "true")

    settings = Settings(DATABASE_URL=DATABASE_URL)

    assert settings.prism_v21_enabled is True
