from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import anyio
import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier


@dataclass(frozen=True)
class AuthConfig:
    issuer: str
    resource: str
    algorithm: str = "HS256"
    fixture_secret: str | None = None
    jwks_url: str | None = None


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str
    client_id: str
    tenant_id: str
    scopes: frozenset[str]
    consent_id: str
    consent_status: str


class JsonlAuditSink:
    """Append-only JSONL audit trail without tokens or raw document content."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(
        self,
        event: str,
        *,
        principal: Principal | None = None,
        tool: str | None = None,
        decision: str,
        reason: str,
        correlation_id: str | None = None,
        argument_digest: str | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "event_id": uuid4().hex,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "decision": decision,
            "reason": reason,
            "correlation_id": correlation_id or uuid4().hex,
        }
        if tool is not None:
            row["tool"] = tool
        if argument_digest is not None:
            row["argument_digest"] = argument_digest
        if principal is not None:
            row.update(
                {
                    "issuer": principal.issuer,
                    "subject": principal.subject,
                    "client_id": principal.client_id,
                    "tenant_id": principal.tenant_id,
                    "scopes": sorted(principal.scopes),
                    "consent_id": principal.consent_id,
                    "consent_status": principal.consent_status,
                }
            )
        encoded = json.dumps(row, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded + "\n")


class JwtTokenVerifier(TokenVerifier):
    """Validate fixture JWTs or asymmetric JWTs obtained from an OIDC issuer."""

    def __init__(self, config: AuthConfig, audit: JsonlAuditSink) -> None:
        self.config = config
        self.audit = audit
        self._jwks = PyJWKClient(config.jwks_url) if config.jwks_url else None

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = await self._verification_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=[self.config.algorithm],
                audience=self.config.resource,
                issuer=self.config.issuer,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
            principal = principal_from_claims(claims)
        except Exception as exc:  # invalid credentials deliberately collapse to one boundary
            self.audit.record(
                "token_validation",
                decision="deny",
                reason=type(exc).__name__,
            )
            return None

        self.audit.record(
            "token_validation",
            principal=principal,
            decision="allow",
            reason="signature_issuer_audience_valid",
        )
        return AccessToken(
            token=token,
            client_id=principal.client_id,
            scopes=sorted(principal.scopes),
            expires_at=int(claims["exp"]),
            resource=self.config.resource,
            subject=principal.subject,
            claims=dict(claims),
        )

    async def _verification_key(self, token: str) -> Any:
        if self._jwks is not None:
            signing_key = await anyio.to_thread.run_sync(self._jwks.get_signing_key_from_jwt, token)
            return signing_key.key
        if not self.config.fixture_secret:
            raise ValueError("No verification key configured")
        return self.config.fixture_secret


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    scopes = claims.get("scope", "")
    if isinstance(scopes, str):
        scope_set = frozenset(part for part in scopes.split() if part)
    elif isinstance(scopes, list):
        scope_set = frozenset(str(part) for part in scopes)
    else:
        raise ValueError("scope must be a string or list")

    tenant_id = claims.get("tenant_id")
    consent_id = claims.get("consent_id")
    consent_status = claims.get("consent_status")
    client_id = claims.get("client_id") or claims.get("azp")
    for name, value in {
        "tenant_id": tenant_id,
        "consent_id": consent_id,
        "consent_status": consent_status,
        "client_id": client_id,
    }.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f"missing claim: {name}")

    return Principal(
        issuer=str(claims["iss"]),
        subject=str(claims["sub"]),
        client_id=client_id,
        tenant_id=tenant_id,
        scopes=scope_set,
        consent_id=consent_id,
        consent_status=consent_status,
    )
