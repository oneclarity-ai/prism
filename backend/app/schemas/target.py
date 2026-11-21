import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.db.enums import Environment
from app.schemas.common import ORMModel


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1)
    scope: str = "general"


class SecretRead(ORMModel):
    id: uuid.UUID
    name: str
    scope: str
    created_at: datetime


class TestLogin(BaseModel):
    __test__ = False

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _origins(values: list[str] | None) -> list[str] | None:
    """Normalise to scheme://host[:port]. '*' means: do not restrict the browser."""
    if values is None:
        return None
    out = []
    for v in values:
        v = v.strip()
        if not v:
            continue
        if v == "*":
            out.append("*")
            continue
        u = urlparse(v if "://" in v else f"https://{v}")
        if not u.netloc:
            raise ValueError(f"'{v}' is not a valid origin, e.g. https://cdn.example.com")
        out.append(f"{u.scheme}://{u.netloc}")
    return list(dict.fromkeys(out))


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: AnyHttpUrl
    environment: Environment = Environment.staging
    test_login: TestLogin | None = None
    repo_url: AnyHttpUrl | None = None
    notes: str = ""
    extra_origins: list[str] = Field(default_factory=list)

    @field_validator("extra_origins")
    @classmethod
    def _check_origins(cls, v):
        return _origins(v)


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: AnyHttpUrl | None = None
    environment: Environment | None = None
    test_login: TestLogin | None = None
    clear_test_login: bool = False
    repo_url: AnyHttpUrl | None = None
    notes: str | None = None
    extra_origins: list[str] | None = None

    @field_validator("extra_origins")
    @classmethod
    def _check_origins(cls, v):
        return _origins(v)


class TargetRead(ORMModel):
    id: uuid.UUID
    name: str
    base_url: str
    environment: Environment
    has_test_login: bool
    repo_url: str | None
    notes: str
    extra_origins: list[str]
    created_at: datetime
    updated_at: datetime
