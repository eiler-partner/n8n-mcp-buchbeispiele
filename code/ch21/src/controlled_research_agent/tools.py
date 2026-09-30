from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .domain import ToolContract


class SearchCatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=2, max_length=200)
    max_hits: int = Field(default=3, ge=1, le=5)


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    title: str
    score: int = Field(ge=1)


class SearchCatalogOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hits: list[SearchHit] = Field(max_length=5)


class ReadDocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")


class ReadDocumentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    title: str
    text: str = Field(max_length=20_000)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    title: str
    text: str


class CatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    documents: list[Document]


class ToolRejected(ValueError):
    """A model-proposed call did not pass the deterministic boundary."""


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    contract: ToolContract
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]


class ToolRegistry:
    """Closed registry: model output can select, but cannot add, a tool."""

    def __init__(self, catalog: CatalogFile) -> None:
        self._documents = {item.document_id: item for item in catalog.documents}
        self._tools = {
            "search_catalog": RegisteredTool(
                contract=ToolContract(
                    name="search_catalog",
                    description=(
                        "Durchsucht den lokalen, freigegebenen Katalog. "
                        "Liefert nur Dokument-IDs, Titel und einen einfachen Trefferwert."
                    ),
                    input_schema=SearchCatalogInput.model_json_schema(),
                ),
                input_model=SearchCatalogInput,
                output_model=SearchCatalogOutput,
                handler=self._search,
            ),
            "read_document": RegisteredTool(
                contract=ToolContract(
                    name="read_document",
                    description=(
                        "Liest genau ein Dokument aus dem freigegebenen lokalen Katalog. "
                        "Akzeptiert nur eine zuvor bekannte Dokument-ID."
                    ),
                    input_schema=ReadDocumentInput.model_json_schema(),
                ),
                input_model=ReadDocumentInput,
                output_model=ReadDocumentOutput,
                handler=self._read,
            ),
        }

    @classmethod
    def from_path(cls, path: str | Path) -> ToolRegistry:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(CatalogFile.model_validate(value))

    @property
    def contracts(self) -> tuple[ToolContract, ...]:
        return tuple(item.contract for item in self._tools.values())

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolRejected(f"tool_not_allowed:{name}")
        try:
            parsed_input = tool.input_model.model_validate(arguments)
            raw_output = tool.handler(parsed_input)
            checked_output = tool.output_model.model_validate(raw_output)
        except ValidationError as exc:
            raise ToolRejected("arguments_or_result_failed_schema") from exc
        except KeyError as exc:
            raise ToolRejected("document_not_found") from exc
        return checked_output.model_dump(mode="json")

    def _search(self, raw: BaseModel) -> SearchCatalogOutput:
        args = SearchCatalogInput.model_validate(raw)
        terms = set(re.findall(r"[a-z0-9äöüß]+", args.query.casefold()))
        hits: list[SearchHit] = []
        for document in self._documents.values():
            haystack = f"{document.title} {document.text}".casefold()
            score = sum(haystack.count(term) for term in terms)
            if score:
                hits.append(
                    SearchHit(document_id=document.document_id, title=document.title, score=score)
                )
        hits.sort(key=lambda item: (-item.score, item.document_id))
        return SearchCatalogOutput(hits=hits[: args.max_hits])

    def _read(self, raw: BaseModel) -> ReadDocumentOutput:
        args = ReadDocumentInput.model_validate(raw)
        document = self._documents[args.document_id]
        return ReadDocumentOutput(**document.model_dump())
