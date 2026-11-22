import uuid

from pydantic import BaseModel, Field

from app.db.enums import UserRole
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    # Plain string on purpose: EmailStr rejects internal domains such as .local.
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str


class UserRead(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    name: str
    role: UserRole
