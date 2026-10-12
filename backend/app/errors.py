"""Canonical API errors (frontend types/contracts.ts ApiError)."""

from typing import Literal

ErrorCode = Literal[
    "MALFORMED_INPUT",
    "SESSION_EXPIRED",
    "FORBIDDEN",
    "NOT_FOUND",
    "REVISION_CONFLICT",
    "GUARD_FAILED",
    "CAPABILITY_UNAVAILABLE",
    "DEPENDENCY_UNAVAILABLE",
    "LIMIT_REACHED",
]

STATUS: dict[str, int] = {
    "MALFORMED_INPUT": 422,
    "SESSION_EXPIRED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "REVISION_CONFLICT": 409,
    "GUARD_FAILED": 409,
    "CAPABILITY_UNAVAILABLE": 501,
    "DEPENDENCY_UNAVAILABLE": 503,
    "LIMIT_REACHED": 429,
}


class ApiError(Exception):
    def __init__(self, code: ErrorCode, message: str, retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        # Extra machine-readable fields merged into the error body (e.g. "limit" for LIMIT_REACHED).
        self.details = details or {}

    @property
    def status(self) -> int:
        return STATUS[self.code]
