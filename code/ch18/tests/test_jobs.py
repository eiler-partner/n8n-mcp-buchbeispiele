import asyncio

import pytest

from advanced_policy_mcp.jobs import ReviewJobManager, ReviewResult, ReviewState


class GateEngine:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def review(self, document_id, checks, report):
        self.started.set()
        await report(1, 2, "Analyse")
        await self.release.wait()
        await report(2, 2, "Fertig")
        return ReviewResult(document_id=document_id, findings=[], passed_checks=len(checks))


@pytest.mark.anyio
async def test_job_lifecycle_is_transport_independent():
    engine = GateEngine()
    manager = ReviewJobManager(engine)
    try:
        submitted = await manager.submit("DOC-7", ["Freigabe", "Verschlüsselung"])
        assert submitted.state is ReviewState.QUEUED

        await engine.started.wait()
        running = await manager.get(submitted.job_id)
        assert running.state is ReviewState.RUNNING
        assert running.progress == 50

        engine.release.set()
        for _ in range(20):
            finished = await manager.get(submitted.job_id)
            if finished.state is ReviewState.SUCCEEDED:
                break
            await asyncio.sleep(0)

        assert finished.state is ReviewState.SUCCEEDED
        assert finished.progress == 100
        assert finished.result is not None
    finally:
        await manager.close()


@pytest.mark.anyio
async def test_running_job_can_be_cancelled():
    engine = GateEngine()
    manager = ReviewJobManager(engine)
    try:
        submitted = await manager.submit("DOC-8", ["Freigabe"])
        await engine.started.wait()
        cancelled = await manager.cancel(submitted.job_id)
        assert cancelled.state is ReviewState.CANCELLED
    finally:
        await manager.close()
