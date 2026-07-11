"""Async scheduler for periodic jobs.

A lightweight cron-like scheduler that runs inside MK's async event loop.
Supports named intervals (every 5 minutes, hourly, daily, weekly) and
tracks execution history for reliability monitoring.

Design decisions:
- Async-native: Uses asyncio.sleep, no threads
- Jitter: Random offset to prevent thundering herd
- Missed runs: Detects and reports missed executions
- Graceful: Handles exceptions per-job without crashing the scheduler
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScheduleInterval(str, Enum):
    """Named schedule intervals.

    Predefined intervals that cover common monitoring patterns.
    Custom intervals can also be specified in seconds.
    """

    EVERY_MINUTE = "every_minute"  # 60s
    EVERY_5_MINUTES = "every_5_minutes"  # 300s
    EVERY_15_MINUTES = "every_15_minutes"  # 900s
    EVERY_30_MINUTES = "every_30_minutes"  # 1800s
    HOURLY = "hourly"  # 3600s
    EVERY_6_HOURS = "every_6_hours"  # 21600s
    DAILY = "daily"  # 86400s
    WEEKLY = "weekly"  # 604800s

    @property
    def seconds(self) -> int:
        """Get the interval duration in seconds."""
        return {
            "every_minute": 60,
            "every_5_minutes": 300,
            "every_15_minutes": 900,
            "every_30_minutes": 1800,
            "hourly": 3600,
            "every_6_hours": 21600,
            "daily": 86400,
            "weekly": 604800,
        }[self.value]


@dataclass
class JobExecution:
    """Record of a single job execution."""

    timestamp: float
    success: bool
    duration_seconds: float
    error: Optional[str] = None
    result: Optional[str] = None


@dataclass
class ScheduledJob:
    """A registered scheduled job.

    Tracks the job's configuration, execution history, and
    current state. Each job runs independently.
    """

    name: str
    handler: Callable[..., Coroutine]
    interval_seconds: int
    description: str = ""
    enabled: bool = True
    jitter_seconds: int = 0  # Random offset to prevent thundering herd
    max_history: int = 50

    # Runtime state
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    consecutive_failures: int = 0
    total_runs: int = 0
    total_failures: int = 0
    history: List[JobExecution] = field(default_factory=list)
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    @property
    def is_overdue(self) -> bool:
        """Whether this job should have run but hasn't."""
        if self.next_run is None:
            return True
        return time.time() > self.next_run + self.interval_seconds

    @property
    def success_rate(self) -> float:
        """Success rate as a fraction (0.0 to 1.0)."""
        if self.total_runs == 0:
            return 1.0
        return (self.total_runs - self.total_failures) / self.total_runs

    def record_execution(
        self,
        success: bool,
        duration: float,
        error: Optional[str] = None,
        result: Optional[str] = None,
    ) -> None:
        """Record a job execution."""
        self.history.append(
            JobExecution(
                timestamp=time.time(),
                success=success,
                duration_seconds=duration,
                error=error,
                result=result,
            )
        )
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

        self.total_runs += 1
        self.last_run = time.time()

        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            self.total_failures += 1


class Scheduler:
    """Async cron-like scheduler for periodic operations.

    Manages a set of named jobs, each running at its own interval.
    Jobs run concurrently via asyncio tasks but don't overlap
    (a job that's still running won't be triggered again).

    Features:
    - Named intervals or custom seconds
    - Jitter to spread load
    - Execution history per job
    - Graceful error handling (one bad job doesn't crash others)
    - Start/stop/pause per job or globally
    """

    def __init__(self, max_concurrent_jobs: int = 10) -> None:
        """Initialize the scheduler.

        Args:
            max_concurrent_jobs: Maximum jobs running simultaneously.
        """
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running: bool = False
        self._main_task: Optional[asyncio.Task] = None
        self._max_concurrent = max_concurrent_jobs
        self._semaphore: Optional[asyncio.Semaphore] = None

    @property
    def job_count(self) -> int:
        """Number of registered jobs."""
        return len(self._jobs)

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is actively running."""
        return self._running

    @property
    def jobs(self) -> Dict[str, ScheduledJob]:
        """All registered jobs."""
        return dict(self._jobs)

    def register(
        self,
        name: str,
        handler: Callable[..., Coroutine],
        interval: ScheduleInterval | int,
        description: str = "",
        jitter_seconds: int = 0,
        enabled: bool = True,
    ) -> ScheduledJob:
        """Register a new scheduled job.

        Args:
            name: Unique job name.
            handler: Async function to call on each tick.
            interval: How often to run (ScheduleInterval or seconds).
            description: Human-readable description.
            jitter_seconds: Random offset range (0 to jitter) added to interval.
            enabled: Whether the job starts enabled.

        Returns:
            The registered ScheduledJob.

        Raises:
            ValueError: If a job with the same name already exists.
        """
        if name in self._jobs:
            raise ValueError(f"Job '{name}' already registered")

        interval_secs = interval.seconds if isinstance(interval, ScheduleInterval) else interval

        job = ScheduledJob(
            name=name,
            handler=handler,
            interval_seconds=interval_secs,
            description=description,
            enabled=enabled,
            jitter_seconds=jitter_seconds,
        )
        self._jobs[name] = job
        logger.info(f"Registered job '{name}' (every {interval_secs}s)")
        return job

    def unregister(self, name: str) -> bool:
        """Remove a registered job.

        Args:
            name: Job name to remove.

        Returns:
            True if found and removed.
        """
        job = self._jobs.pop(name, None)
        if job and job._task:
            job._task.cancel()
        return job is not None

    def enable_job(self, name: str) -> bool:
        """Enable a disabled job."""
        if name in self._jobs:
            self._jobs[name].enabled = True
            return True
        return False

    def disable_job(self, name: str) -> bool:
        """Disable a job (stops it from running)."""
        if name in self._jobs:
            self._jobs[name].enabled = False
            return True
        return False

    async def start(self) -> None:
        """Start the scheduler (runs all jobs in background).

        This method starts the main scheduler loop and returns
        immediately. Jobs begin executing on their schedules.
        """
        if self._running:
            return

        self._running = True
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

        # Start individual job loops
        for job in self._jobs.values():
            if job.enabled:
                job._task = asyncio.create_task(
                    self._job_loop(job),
                    name=f"scheduler:{job.name}",
                )

        logger.info(f"Scheduler started with {self.job_count} jobs")

    async def stop(self) -> None:
        """Stop the scheduler gracefully.

        Cancels all running job tasks and waits for them to finish.
        """
        self._running = False

        tasks = [j._task for j in self._jobs.values() if j._task]
        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Scheduler stopped")

    async def run_once(self, name: str) -> Optional[JobExecution]:
        """Manually trigger a job to run immediately.

        Args:
            name: Job name to run.

        Returns:
            JobExecution record, or None if job not found.
        """
        job = self._jobs.get(name)
        if not job:
            return None

        # Ensure semaphore exists for manual runs
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)

        return await self._execute_job(job)

    async def _job_loop(self, job: ScheduledJob) -> None:
        """Main loop for a single job. Runs until cancelled.

        Args:
            job: The job to loop.
        """
        # Initial delay: spread jobs out with jitter
        initial_delay = random.uniform(0, min(job.interval_seconds, 30))
        await asyncio.sleep(initial_delay)

        while self._running and job.enabled:
            try:
                # Calculate next run with optional jitter
                jitter = random.uniform(0, job.jitter_seconds) if job.jitter_seconds else 0
                job.next_run = time.time() + job.interval_seconds + jitter

                # Execute the job
                await self._execute_job(job)

                # Sleep until next run
                sleep_time = job.interval_seconds + jitter
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Job loop error for '{job.name}': {e}", exc_info=True)
                # Back off on repeated failures
                backoff = min(300, job.consecutive_failures * 30)
                await asyncio.sleep(backoff)

    async def _execute_job(self, job: ScheduledJob) -> JobExecution:
        """Execute a single job with error handling and timing.

        Args:
            job: The job to execute.

        Returns:
            JobExecution record.
        """
        start = time.time()
        success = False
        error: Optional[str] = None
        result: Optional[str] = None

        try:
            if self._semaphore is None:
                self._semaphore = asyncio.Semaphore(self._max_concurrent)
            async with self._semaphore:
                raw_result = await job.handler()
                success = True
                if raw_result is not None:
                    result = str(raw_result)[:500]  # Cap result size
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            logger.warning(f"Job '{job.name}' failed: {error}")

        duration = time.time() - start
        job.record_execution(success, duration, error, result)

        execution = JobExecution(
            timestamp=time.time(),
            success=success,
            duration_seconds=duration,
            error=error,
            result=result,
        )

        return execution

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status and all job states.

        Returns:
            Dict with scheduler state and per-job details.
        """
        return {
            "running": self._running,
            "total_jobs": self.job_count,
            "enabled_jobs": sum(1 for j in self._jobs.values() if j.enabled),
            "jobs": {
                name: {
                    "enabled": job.enabled,
                    "interval_seconds": job.interval_seconds,
                    "last_run": job.last_run,
                    "next_run": job.next_run,
                    "total_runs": job.total_runs,
                    "total_failures": job.total_failures,
                    "consecutive_failures": job.consecutive_failures,
                    "success_rate": job.success_rate,
                    "description": job.description,
                }
                for name, job in self._jobs.items()
            },
        }
