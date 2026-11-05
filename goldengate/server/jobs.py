"""Background jobs (suite runs, demo reset) with progress polling for the dashboard."""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

JobStatus = Literal["queued", "running", "done", "error"]


class Job(BaseModel):
    id: str
    kind: str
    label: str
    status: JobStatus = "queued"
    done: int = 0
    total: int = 0
    message: str = ""
    run_id: str | None = None
    error: str | None = None
    started_at: str
    finished_at: str | None = None


class JobBusy(RuntimeError):
    """Raised when a job is already running (one at a time keeps SQLite writes simple)."""


Work = Callable[[Callable[[int, int, str], None]], str | None]


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def active(self) -> Job | None:
        return next((j for j in self._jobs.values() if j.status in ("queued", "running")), None)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def start(self, kind: str, label: str, work: Work) -> Job:
        """Run ``work(progress)`` in a thread; ``work`` returns an optional run ID."""
        with self._lock:
            if self.active():
                raise JobBusy("Another run is in progress; wait for it to finish")
            job = Job(id=uuid.uuid4().hex[:10], kind=kind, label=label,
                      started_at=datetime.now(timezone.utc).isoformat())
            self._jobs[job.id] = job

        def progress(done: int, total: int, message: str) -> None:
            job.done, job.total, job.message = done, total, message

        def target() -> None:
            job.status = "running"
            try:
                job.run_id = work(progress)
                job.status = "done"
                job.message = "Finished"
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI instead of crashing the server
                job.status = "error"
                job.error = f"{exc.__class__.__name__}: {exc}"
                traceback.print_exc()
            job.finished_at = datetime.now(timezone.utc).isoformat()

        threading.Thread(target=target, daemon=True, name=f"goldengate-job-{job.id}").start()
        return job
