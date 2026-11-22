from __future__ import annotations

import uuid

from app.schemas.common import Schema
from app.schemas.management.journey import JourneyRead


class DummyJourneyResult(Schema):
    created: bool
    blocker_id: uuid.UUID
    message: str
    journey: JourneyRead
