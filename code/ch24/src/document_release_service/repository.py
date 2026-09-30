from __future__ import annotations

from threading import Lock
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from .models import (
    DocumentHit,
    NormalizedDocument,
    PublicationRequest,
    PublishResult,
    RequestStatus,
)


class ConflictError(ValueError):
    pass


class Repository(Protocol):
    def initialize(self) -> None: ...
    def put_document(self, document: NormalizedDocument) -> bool: ...
    def get_document(self, tenant_id: str, document_id: str) -> NormalizedDocument | None: ...
    def search_documents(self, tenant_id: str, query: str, limit: int) -> list[DocumentHit]: ...
    def put_request(self, request: PublicationRequest) -> None: ...
    def get_request(self, request_id: str) -> PublicationRequest | None: ...
    def save_request(self, request: PublicationRequest) -> None: ...
    def put_outbox(self, result: PublishResult) -> bool: ...
    def get_outbox(self, request_id: str) -> PublishResult | None: ...


class MemoryRepository:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str], NormalizedDocument] = {}
        self.requests: dict[str, PublicationRequest] = {}
        self.outbox: dict[str, PublishResult] = {}
        self._lock = Lock()

    def initialize(self) -> None:
        return None

    def put_document(self, document: NormalizedDocument) -> bool:
        key = (document.tenant_id, document.document_id)
        with self._lock:
            existing = self.documents.get(key)
            if existing:
                if existing.content_hash != document.content_hash:
                    raise ConflictError("document_id bereits mit anderem Inhalt vorhanden")
                return False
            self.documents[key] = document
        return True

    def get_document(self, tenant_id: str, document_id: str) -> NormalizedDocument | None:
        return self.documents.get((tenant_id, document_id))

    def search_documents(self, tenant_id: str, query: str, limit: int) -> list[DocumentHit]:
        needle = query.casefold()
        values = [
            value
            for (tenant, _), value in self.documents.items()
            if tenant == tenant_id
            and needle in f"{value.document_id} {value.title} {value.text}".casefold()
        ]
        return [DocumentHit(**value.model_dump(exclude={"tenant_id", "text", "correlation_id"})) for value in values[:limit]]

    def put_request(self, request: PublicationRequest) -> None:
        with self._lock:
            if request.request_id in self.requests:
                raise ConflictError("request_id bereits vorhanden")
            self.requests[request.request_id] = request

    def get_request(self, request_id: str) -> PublicationRequest | None:
        value = self.requests.get(request_id)
        return value.model_copy(deep=True) if value else None

    def save_request(self, request: PublicationRequest) -> None:
        self.requests[request.request_id] = request.model_copy(deep=True)

    def put_outbox(self, result: PublishResult) -> bool:
        with self._lock:
            if result.request_id in self.outbox:
                return False
            self.outbox[result.request_id] = result.model_copy(deep=True)
        return True

    def get_outbox(self, request_id: str) -> PublishResult | None:
        value = self.outbox.get(request_id)
        return value.model_copy(deep=True) if value else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS ch24_documents (
  tenant_id text NOT NULL,
  document_id text NOT NULL,
  title text NOT NULL,
  source text NOT NULL,
  body text NOT NULL,
  trusted boolean NOT NULL,
  content_hash text NOT NULL,
  correlation_id text NOT NULL,
  PRIMARY KEY (tenant_id, document_id)
);
CREATE TABLE IF NOT EXISTS ch24_publication_requests (
  request_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  document_id text NOT NULL,
  content_hash text NOT NULL,
  summary text NOT NULL,
  destination text NOT NULL,
  proposal_digest text NOT NULL,
  correlation_id text NOT NULL,
  status text NOT NULL,
  approver text,
  expires_at bigint,
  signature text
);
CREATE TABLE IF NOT EXISTS ch24_outbox (
  request_id text PRIMARY KEY,
  document_id text NOT NULL,
  destination text NOT NULL,
  correlation_id text NOT NULL,
  published_at timestamptz NOT NULL
);
"""


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def initialize(self) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('ch24-schema'))")
            cursor.execute(SCHEMA)

    def put_document(self, document: NormalizedDocument) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT content_hash FROM ch24_documents WHERE tenant_id=%s AND document_id=%s",
                (document.tenant_id, document.document_id),
            )
            existing = cursor.fetchone()
            if existing:
                if existing["content_hash"] != document.content_hash:
                    raise ConflictError("document_id bereits mit anderem Inhalt vorhanden")
                return False
            cursor.execute(
                "INSERT INTO ch24_documents VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    document.tenant_id,
                    document.document_id,
                    document.title,
                    document.source,
                    document.text,
                    document.trusted,
                    document.content_hash,
                    document.correlation_id,
                ),
            )
        return True

    def get_document(self, tenant_id: str, document_id: str) -> NormalizedDocument | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id,document_id,title,source,body AS text,trusted,content_hash,correlation_id FROM ch24_documents WHERE tenant_id=%s AND document_id=%s",
                (tenant_id, document_id),
            )
            row = cursor.fetchone()
        return NormalizedDocument(**row) if row else None

    def search_documents(self, tenant_id: str, query: str, limit: int) -> list[DocumentHit]:
        pattern = f"%{query}%"
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT document_id,title,source,trusted,content_hash FROM ch24_documents WHERE tenant_id=%s AND (document_id ILIKE %s OR title ILIKE %s OR body ILIKE %s) ORDER BY document_id LIMIT %s",
                (tenant_id, pattern, pattern, pattern, limit),
            )
            rows = cursor.fetchall()
        return [DocumentHit(**row) for row in rows]

    def put_request(self, request: PublicationRequest) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO ch24_publication_requests VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        request.request_id,
                        request.tenant_id,
                        request.document_id,
                        request.content_hash,
                        request.summary,
                        request.destination,
                        request.proposal_digest,
                        request.correlation_id,
                        request.status.value,
                        request.approver,
                        request.expires_at,
                        request.signature,
                    ),
                )
            except psycopg.errors.UniqueViolation as exc:
                raise ConflictError("request_id bereits vorhanden") from exc

    def get_request(self, request_id: str) -> PublicationRequest | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ch24_publication_requests WHERE request_id=%s", (request_id,))
            row = cursor.fetchone()
        return PublicationRequest(**row) if row else None

    def save_request(self, request: PublicationRequest) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE ch24_publication_requests SET status=%s,approver=%s,expires_at=%s,signature=%s WHERE request_id=%s",
                (request.status.value, request.approver, request.expires_at, request.signature, request.request_id),
            )

    def put_outbox(self, result: PublishResult) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM ch24_outbox WHERE request_id=%s", (result.request_id,))
            if cursor.fetchone():
                return False
            cursor.execute(
                "INSERT INTO ch24_outbox VALUES (%s,%s,%s,%s,%s)",
                (result.request_id, result.document_id, result.destination, result.correlation_id, result.published_at),
            )
        return True

    def get_outbox(self, request_id: str) -> PublishResult | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ch24_outbox WHERE request_id=%s", (request_id,))
            row = cursor.fetchone()
        return PublishResult(**row) if row else None
