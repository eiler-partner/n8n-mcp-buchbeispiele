from __future__ import annotations

from enum import StrEnum


class FailureKind(StrEnum):
    TRANSPORT = "transport"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    AUTHENTICATION = "authentication"
    INVALID_OUTPUT = "invalid_output"
    REFUSAL = "refusal"
    POLICY = "policy"


RETRYABLE_FAILURES = {
    FailureKind.TRANSPORT,
    FailureKind.RATE_LIMIT,
    FailureKind.SERVER,
}


class ProviderError(RuntimeError):
    def __init__(self, provider: str, kind: FailureKind, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.kind = kind

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_FAILURES
