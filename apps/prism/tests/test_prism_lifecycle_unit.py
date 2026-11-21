from app.models.enums import PrismLifecycleState
from app.services.prism_lifecycle_service import LIFECYCLE_TRANSITIONS, PrismLifecycleService


def test_prism_name_normalization_is_unicode_and_whitespace_stable() -> None:
    assert (
        PrismLifecycleService.normalize_name("  Executive   Assistant  ") == "executive assistant"
    )
    assert PrismLifecycleService.normalize_name("Ｅxecutive Assistant") == "executive assistant"


def test_archived_prism_has_no_valid_lifecycle_transition() -> None:
    assert LIFECYCLE_TRANSITIONS[PrismLifecycleState.ARCHIVED] == set()
    assert (
        PrismLifecycleState.ACTIVE
        in LIFECYCLE_TRANSITIONS[PrismLifecycleState.AWAITING_CONFIRMATION]
    )
