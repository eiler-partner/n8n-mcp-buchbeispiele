from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from model_adapter_lab.domain import ExtractedInvoice


VALID_DATA = {
    "status": "complete",
    "supplier": "Alpenlicht GmbH",
    "invoice_number": "RE-2026-1042",
    "invoice_date": "2026-09-12",
    "due_date": "2026-10-12",
    "currency": "EUR",
    "gross_amount": "1488.00",
    "evidence": ["Rechnung RE-2026-1042", "Gesamtbetrag EUR 1.488,00"],
    "warnings": [],
}


class Recorder:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}


class FakeOpenAI:
    def __init__(self, recorder: Recorder, data: dict[str, Any] | None = None) -> None:
        self.responses = self
        self.recorder = recorder
        self.data = data or VALID_DATA

    def parse(self, **kwargs: Any) -> Any:
        self.recorder.kwargs = kwargs
        return SimpleNamespace(output_parsed=ExtractedInvoice.model_validate(self.data))


class FakeAnthropic:
    def __init__(self, recorder: Recorder, data: dict[str, Any] | None = None) -> None:
        self.messages = self
        self.recorder = recorder
        self.data = data or VALID_DATA

    def parse(self, **kwargs: Any) -> Any:
        self.recorder.kwargs = kwargs
        return SimpleNamespace(parsed_output=ExtractedInvoice.model_validate(self.data))


class FakeOllama:
    def __init__(self, recorder: Recorder, content: str | None = None) -> None:
        self.recorder = recorder
        self.content = content or ExtractedInvoice.model_validate(VALID_DATA).model_dump_json()

    def chat(self, **kwargs: Any) -> Any:
        self.recorder.kwargs = kwargs
        return SimpleNamespace(message=SimpleNamespace(content=self.content))
