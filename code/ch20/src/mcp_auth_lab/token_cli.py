from __future__ import annotations

import argparse
import os
import time

import jwt


def issue_fixture_token(
    *,
    subject: str,
    tenant: str,
    scope: str,
    consent: str,
    issuer: str,
    audience: str,
    client_id: str,
    secret: str,
    lifetime_seconds: int = 300,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "iat": now,
            "exp": now + lifetime_seconds,
            "client_id": client_id,
            "tenant_id": tenant,
            "scope": scope,
            "consent_id": f"consent-{subject}-{tenant}",
            "consent_status": consent,
        },
        secret,
        algorithm="HS256",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a short-lived chapter-20 fixture token.")
    parser.add_argument("--subject", default="alice")
    parser.add_argument("--tenant", default="tenant-a")
    parser.add_argument("--scope", default="documents:read")
    parser.add_argument("--consent", choices=("granted", "denied"), default="granted")
    parser.add_argument("--issuer", default=os.getenv("MCP_AUTH_ISSUER", "http://127.0.0.1:9019"))
    parser.add_argument("--audience", default=os.getenv("MCP_AUTH_RESOURCE", "http://127.0.0.1:8019/mcp"))
    parser.add_argument("--client-id", default="chapter-20-client")
    args = parser.parse_args()
    print(
        issue_fixture_token(
            subject=args.subject,
            tenant=args.tenant,
            scope=args.scope,
            consent=args.consent,
            issuer=args.issuer,
            audience=args.audience,
            client_id=args.client_id,
            secret=os.getenv(
                "MCP_JWT_FIXTURE_SECRET",
                "chapter-20-local-fixture-only-32-bytes-minimum",
            ),
        )
    )


if __name__ == "__main__":
    main()
