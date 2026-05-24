from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class _JobEntry:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    done: bool = False


class IngestJobRegistry:
    """Thread-safe job registry that buffers per-file ingest status events for SSE streaming.

    The upload endpoint creates a job and starts a background thread. The thread emits
    status events via ``emit()`` using ``call_soon_threadsafe``. The SSE endpoint reads
    from the job's asyncio.Queue via ``subscribe()`` until the sentinel ``done=True``
    event is received.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, _JobEntry] = {}

    def create(self, *, loop: asyncio.AbstractEventLoop) -> str:
        """Create a new job and return its ID. Must be called from async context."""
        job_id = str(uuid4())
        self._jobs[job_id] = _JobEntry(queue=asyncio.Queue(), loop=loop)
        return job_id

    def emit(self, job_id: str, event: dict[str, object]) -> None:
        """Emit an event from any thread. Thread-safe."""
        entry = self._jobs.get(job_id)
        if entry is None or entry.done:
            return
        if event.get("done"):
            entry.done = True
        try:
            entry.loop.call_soon_threadsafe(entry.queue.put_nowait, event)
        except RuntimeError:
            pass

    async def subscribe(self, job_id: str):
        """Async generator that yields events until the job signals done."""
        entry = self._jobs.get(job_id)
        if entry is None:
            return
        queue = entry.queue
        try:
            while True:
                event = await queue.get()
                yield event
                if event.get("done"):
                    break
        finally:
            self._jobs.pop(job_id, None)
