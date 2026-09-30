from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel, Field


class HashResult(BaseModel):
    algorithm: str = "sha256"
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=0)


class SearchHit(BaseModel):
    policy_id: str
    title: str
    excerpt: str
    score: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class Policy:
    policy_id: str
    title: str
    text: str


class PolicyRepository:
    def __init__(self, policies: list[Policy]) -> None:
        self._policies = policies

    def get(self, policy_id: str) -> Policy | None:
        return next((p for p in self._policies if p.policy_id == policy_id), None)

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        terms = {term.casefold() for term in query.split() if term.strip()}
        ranked: list[tuple[float, Policy]] = []
        for policy in self._policies:
            haystack = f"{policy.title} {policy.text}".casefold()
            matches = sum(term in haystack for term in terms)
            if matches:
                ranked.append((matches / max(len(terms), 1), policy))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchHit(
                policy_id=policy.policy_id,
                title=policy.title,
                excerpt=policy.text[:220],
                score=min(score, 1.0),
            )
            for score, policy in ranked[:limit]
        ]


def sha256_text(text: str) -> HashResult:
    raw = text.encode("utf-8")
    return HashResult(digest=hashlib.sha256(raw).hexdigest(), byte_length=len(raw))
