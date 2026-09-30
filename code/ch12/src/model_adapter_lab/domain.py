from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractionStatus(StrEnum):
    COMPLETE = "complete"
    INSUFFICIENT = "insufficient"


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=50_000)


class ExtractedInvoice(BaseModel):
    """Providerunabhaengiger Fachvertrag, nicht das Rohformat einer API."""

    model_config = ConfigDict(extra="forbid")

    status: ExtractionStatus
    supplier: str | None
    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    gross_amount: Decimal | None = Field(default=None, ge=0)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    warnings: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def complete_result_needs_core_fields(self) -> ExtractedInvoice:
        if self.status is ExtractionStatus.COMPLETE:
            required = (
                self.supplier,
                self.invoice_number,
                self.currency,
                self.gross_amount,
            )
            if any(value is None for value in required):
                raise ValueError("complete requires supplier, invoice_number, currency and gross_amount")
        return self


class ExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
    data: ExtractedInvoice


SYSTEM_INSTRUCTIONS = """Du extrahierst Rechnungsdaten ohne zu raten.
Verwende nur Informationen aus dem Dokument. Fehlen Kernfelder, setze status auf
insufficient, die betreffenden Felder auf null und erklaere dies in warnings.
evidence enthaelt kurze woertliche Belege aus dem Dokument, keine Schlussfolgerungen.
Gib ausschliesslich das angeforderte strukturierte Ergebnis zurueck."""
