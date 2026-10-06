from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.development import DummyJourneyResult
from app.schemas.journey import JourneyRead
from app.schemas.management import RuleFinding
from app.services.development_service import DevelopmentService
from app.services.journey_service import JourneyService
from app.services.management_rule_service import ManagementRuleService

router = APIRouter(prefix="/api/v1/management", tags=["management rules"])


@router.get("/rule-findings", response_model=list[RuleFinding])
def list_rule_findings(db: Session = Depends(get_db)) -> list[RuleFinding]:
    return ManagementRuleService.findings(db)


@router.get("/journeys", response_model=list[JourneyRead])
def list_journeys(db: Session = Depends(get_db)) -> list[JourneyRead]:
    """Show the stored message-and-state chain for recent blockers."""

    return JourneyService.list(db, limit=30)


@router.post("/dummy-journey", response_model=DummyJourneyResult)
def create_dummy_journey(db: Session = Depends(get_db)) -> DummyJourneyResult:
    """Return an ephemeral development preview without writing operational state."""

    return DevelopmentService.create_dummy_journey(db)
