from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

ProgressReporter = Callable[[int, int, str], Awaitable[None]]


class ReviewState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewResult(BaseModel):
    document_id: str
    findings: list[str] = Field(default_factory=list)
    passed_checks: int = Field(ge=0)


class ReviewJob(BaseModel):
    job_id: str
    document_id: str
    checks: list[str]
    state: ReviewState = ReviewState.QUEUED
    progress: int = Field(default=0, ge=0, le=100)
    message: str = "Eingereiht"
    result: ReviewResult | None = None
    error: str | None = None


class ReviewEngine(Protocol):
    async def review(
        self,
        document_id: str,
        checks: list[str],
        report: ProgressReporter,
    ) -> ReviewResult: ...


class DemoReviewEngine:
    """Deterministische Demo; in Produktion steht hier ein externer Worker."""

    async def review(
        self,
        document_id: str,
        checks: list[str],
        report: ProgressReporter,
    ) -> ReviewResult:
        findings: list[str] = []
        total = max(len(checks), 1)
        for number, check in enumerate(checks, start=1):
            await asyncio.sleep(0.05)
            if "verschlüssel" in check.casefold():
                findings.append(f"{check}: Nachweis fehlt")
            await report(number, total, f"Prüfung {number}/{total}: {check}")
        return ReviewResult(
            document_id=document_id,
            findings=findings,
            passed_checks=len(checks) - len(findings),
        )


class ReviewJobManager:
    """Anwendungsdienst; kennt weder MCP noch einen Transport."""

    def __init__(self, engine: ReviewEngine) -> None:
        self._engine = engine
        self._jobs: dict[str, ReviewJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def submit(self, document_id: str, checks: list[str]) -> ReviewJob:
        job = ReviewJob(
            job_id=uuid4().hex,
            document_id=document_id,
            checks=list(checks),
        )
        async with self._lock:
            self._jobs[job.job_id] = job
            self._tasks[job.job_id] = asyncio.create_task(
                self._run(job.job_id),
                name=f"review:{job.job_id}",
            )
        return job.model_copy(deep=True)

    async def get(self, job_id: str) -> ReviewJob:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job.model_copy(deep=True)

    async def cancel(self, job_id: str) -> ReviewJob:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            task = self._tasks.get(job_id)
            if task is None or task.done():
                return job.model_copy(deep=True)
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        return await self.get(job_id)

    async def close(self) -> None:
        async with self._lock:
            tasks = [task for task in self._tasks.values() if not task.done()]
            for task in tasks:
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, job_id: str) -> None:
        await self._update(job_id, state=ReviewState.RUNNING, message="Prüfung läuft")

        async def report(done: int, total: int, message: str) -> None:
            progress = int(done / total * 100) if total else 0
            await self._update(job_id, progress=progress, message=message)

        try:
            job = await self.get(job_id)
            result = await self._engine.review(job.document_id, job.checks, report)
            await self._update(
                job_id,
                state=ReviewState.SUCCEEDED,
                progress=100,
                message="Prüfung abgeschlossen",
                result=result,
            )
        except asyncio.CancelledError:
            await self._update(
                job_id,
                state=ReviewState.CANCELLED,
                message="Prüfung abgebrochen",
            )
            raise
        except Exception as exc:  # Details bleiben serverseitig; Tool liefert stabile Form.
            await self._update(
                job_id,
                state=ReviewState.FAILED,
                message="Prüfung fehlgeschlagen",
                error=type(exc).__name__,
            )

    async def _update(self, job_id: str, **changes: object) -> None:
        async with self._lock:
            self._jobs[job_id] = self._jobs[job_id].model_copy(update=changes)
