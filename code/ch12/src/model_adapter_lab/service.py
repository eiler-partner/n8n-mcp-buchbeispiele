from __future__ import annotations

from dataclasses import dataclass

from .adapters import InvoiceExtractor
from .domain import ExtractionEnvelope, ExtractionRequest
from .errors import ProviderError


@dataclass(slots=True)
class ExtractionService:
    primary: InvoiceExtractor
    fallback: InvoiceExtractor | None = None

    def extract(self, request: ExtractionRequest) -> ExtractionEnvelope:
        try:
            return self.primary.extract(request)
        except ProviderError as exc:
            if self.fallback is None or not exc.retryable:
                raise
            return self.fallback.extract(request)
