"""Job storage for submitted Ingestions.

A folder Ingestion runs for minutes -- longer than an HTTP caller or a webhook
provider will wait -- so callers get a Job Id back and collect the summary
later.

``InMemoryJobStore`` is the adapter for a single process: Jobs do not survive a
restart and are invisible to other processes. The seam is here so a durable
store can replace it without the Ingestor noticing.
"""

import asyncio
import uuid
from typing import Protocol, runtime_checkable

from app.models.schemas import IngestionResult, Job, JobState


@runtime_checkable
class JobStore(Protocol):
    async def create(self, source: str) -> Job: ...

    async def get(self, job_id: str) -> Job | None: ...

    async def succeed(self, job_id: str, result: IngestionResult) -> None: ...

    async def fail(self, job_id: str, error: str) -> None: ...

    async def wait(self, job_id: str) -> Job | None:
        """Block until the Job leaves the running state."""
        ...


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        # One event per Job so waiters wake without polling.
        self._done: dict[str, asyncio.Event] = {}

    async def create(self, source: str) -> Job:
        job = Job(id=uuid.uuid4().hex, source=source, state=JobState.RUNNING)
        self._jobs[job.id] = job
        self._done[job.id] = asyncio.Event()
        return job

    async def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def succeed(self, job_id: str, result: IngestionResult) -> None:
        self._finish(job_id, state=JobState.SUCCEEDED, result=result)

    async def fail(self, job_id: str, error: str) -> None:
        self._finish(job_id, state=JobState.FAILED, error=error)

    async def wait(self, job_id: str) -> Job | None:
        event = self._done.get(job_id)
        if event is None:
            return None
        await event.wait()
        return self._jobs.get(job_id)

    def _finish(
        self,
        job_id: str,
        state: JobState,
        result: IngestionResult | None = None,
        error: str | None = None,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.state = state
        job.result = result
        job.error = error
        self._done[job_id].set()
