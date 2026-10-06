class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class RuleViolationError(DomainError):
    status_code = 422
    code = "rule_violation"


class ExternalServiceError(DomainError):
    status_code = 502
    code = "external_service_error"
