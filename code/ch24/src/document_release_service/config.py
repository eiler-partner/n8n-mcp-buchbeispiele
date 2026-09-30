from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    mcp_token: str
    approval_key: str
    executor_key: str
    signing_key: bytes
    tenant_id: str = "tenant-alpen"
    publish_destination: str = "local://published-reviews"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "CH24_DATABASE_URL",
                "postgresql://n8n:chapter-24-local-db-password@postgres:5432/n8n",
            ),
            mcp_token=os.getenv(
                "CH24_MCP_TOKEN", "chapter-24-local-mcp-token-change-me"
            ),
            approval_key=os.getenv(
                "CH24_APPROVAL_KEY", "chapter-24-local-approval-key-change-me"
            ),
            executor_key=os.getenv(
                "CH24_EXECUTOR_KEY", "chapter-24-local-executor-key-change-me"
            ),
            signing_key=os.getenv(
                "CH24_SIGNING_KEY", "chapter-24-local-signing-key-change-me"
            ).encode(),
            tenant_id=os.getenv("CH24_TENANT_ID", "tenant-alpen"),
        )
