"""Bounded parallel execution for synchronous business agents.

The public task/result types stay small. Internally the pool provides
per-task deadlines, retry budgets, per-agent circuit breakers and explicit
fallback behavior. A timed-out Python thread cannot be killed, so the pool
stops waiting for it and ignores its late result.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class AgentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    CIRCUIT_OPEN = "circuit_open"


class RetryPolicy(StrEnum):
    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"


class FallbackPolicy(StrEnum):
    NONE = "none"
    EMPTY = "empty"
    MOCK = "mock"
    CACHED = "cached"
    SKIP = "skip"


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class AgentTask:
    name: str
    fn: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    timeout: float = 120.0
    retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    fallback: FallbackPolicy = FallbackPolicy.EMPTY
    fallback_value: Any = None
    required: bool = True
    retry_if: Optional[Callable[[Exception], bool]] = None
    breaker_key: Optional[str] = None


@dataclass
class AgentResult:
    name: str
    status: AgentStatus
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    retries: int = 0
    fallback_used: bool = False


@dataclass
class PoolResult:
    results: dict[str, AgentResult] = field(default_factory=dict)
    total_ms: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    circuit_open_count: int = 0

    @property
    def all_success(self) -> bool:
        return (
            self.failure_count == 0
            and self.timeout_count == 0
            and self.circuit_open_count == 0
        )

    @property
    def partial_success(self) -> bool:
        return self.success_count > 0

    def get(self, name: str) -> Optional[AgentResult]:
        return self.results.get(name)


class CircuitBreaker:
    """Thread-safe sliding-window circuit breaker with bounded probes."""

    _MAX_SAMPLES = 10_000

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        *,
        window_duration: float = 60.0,
        error_rate_threshold: float = 0.5,
        half_open_max_probes: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if not 0 < error_rate_threshold <= 1:
            raise ValueError("error_rate_threshold must be in (0, 1]")
        if half_open_max_probes < 1:
            raise ValueError("half_open_max_probes must be at least 1")
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = max(0.0, recovery_timeout)
        self.window_duration = max(0.001, window_duration)
        self.error_rate_threshold = error_rate_threshold
        self.half_open_max_probes = half_open_max_probes
        self._clock = clock
        self._samples: deque[tuple[float, bool]] = deque()
        self._failure_count = 0
        self._opened_at = 0.0
        self._half_open_probes = 0
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._refresh_open_state(self._clock())
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def retry_after(self) -> float:
        with self._lock:
            if self._state != CircuitState.OPEN:
                return 0.0
            return max(
                0.0,
                self.recovery_timeout - (self._clock() - self._opened_at),
            )

    def try_acquire(self) -> bool:
        """Return whether work may run, claiming one half-open probe."""
        with self._lock:
            self._refresh_open_state(self._clock())
            if self._state == CircuitState.OPEN:
                return False
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_probes >= self.half_open_max_probes:
                    return False
                self._half_open_probes += 1
            return True

    def record_success(self):
        with self._lock:
            now = self._clock()
            if self._state == CircuitState.HALF_OPEN:
                self._close()
                return
            if self._state == CircuitState.OPEN:
                # Ignore work that completed after its caller timed out.
                return
            self._record_sample(False, now)

    def record_failure(self):
        with self._lock:
            now = self._clock()
            if self._state == CircuitState.HALF_OPEN:
                self._open(now, "probe_failure")
                return
            if self._state == CircuitState.OPEN:
                return
            self._record_sample(True, now)
            count = len(self._samples)
            if (
                count >= self.failure_threshold
                and self._failure_count / count >= self.error_rate_threshold
            ):
                self._open(now, "failure_rate")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            self._refresh_open_state(now)
            self._evict(now)
            count = len(self._samples)
            return {
                "name": self.name,
                "state": self._state.value,
                "sample_count": count,
                "failure_count": self._failure_count,
                "failure_rate": self._failure_count / count if count else 0.0,
                "retry_after": (
                    max(
                        0.0,
                        self.recovery_timeout - (now - self._opened_at),
                    )
                    if self._state == CircuitState.OPEN
                    else 0.0
                ),
                "half_open_probes": self._half_open_probes,
            }

    def _record_sample(self, failed: bool, now: float) -> None:
        self._evict(now)
        if len(self._samples) >= self._MAX_SAMPLES:
            _, evicted_failed = self._samples.popleft()
            if evicted_failed:
                self._failure_count -= 1
        self._samples.append((now, failed))
        if failed:
            self._failure_count += 1

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_duration
        while self._samples and self._samples[0][0] < cutoff:
            _, failed = self._samples.popleft()
            if failed:
                self._failure_count -= 1

    def _refresh_open_state(self, now: float) -> None:
        if (
            self._state == CircuitState.OPEN
            and now - self._opened_at >= self.recovery_timeout
        ):
            previous = self._state
            self._state = CircuitState.HALF_OPEN
            self._half_open_probes = 0
            logger.info(
                "CircuitBreaker[%s]: %s -> %s",
                self.name,
                previous.value,
                self._state.value,
            )

    def _open(self, now: float, reason: str) -> None:
        previous = self._state
        self._state = CircuitState.OPEN
        self._opened_at = now
        self._half_open_probes = 0
        logger.warning(
            "CircuitBreaker[%s]: %s -> %s (%s)",
            self.name,
            previous.value,
            self._state.value,
            reason,
        )

    def _close(self) -> None:
        previous = self._state
        self._state = CircuitState.CLOSED
        self._samples.clear()
        self._failure_count = 0
        self._half_open_probes = 0
        logger.info(
            "CircuitBreaker[%s]: %s -> %s",
            self.name,
            previous.value,
            self._state.value,
        )


@dataclass(frozen=True)
class _FutureMeta:
    name: str
    task: AgentTask
    deadline: float
    breaker: Optional[CircuitBreaker]


class AgentPool:
    """Execute synchronous agents concurrently with bounded failure behavior."""

    def __init__(
        self,
        max_workers: int = 4,
        default_timeout: float = 120.0,
        default_retry: RetryPolicy = RetryPolicy.EXPONENTIAL,
        default_max_retries: int = 3,
        enable_circuit_breaker: bool = True,
        circuit_threshold: int = 5,
        circuit_recovery: float = 60.0,
        circuit_window: float = 60.0,
        circuit_error_rate: float = 0.5,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.default_retry = default_retry
        self.default_max_retries = default_max_retries
        self._enable_circuit_breaker = enable_circuit_breaker
        self._circuit_threshold = circuit_threshold
        self._circuit_recovery = circuit_recovery
        self._circuit_window = circuit_window
        self._circuit_error_rate = circuit_error_rate
        self._breakers: dict[str, CircuitBreaker] = {}
        self._breakers_lock = threading.Lock()

    def execute_all(self, tasks: dict[str, Callable | AgentTask]) -> PoolResult:
        started = time.monotonic()
        result = PoolResult()
        normalized = self._normalize_tasks(tasks)
        if not normalized:
            return result

        executor = ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(normalized)),
            thread_name_prefix="bsc-agent",
        )
        pending: set[Future] = set()
        metadata: dict[Future, _FutureMeta] = {}
        try:
            for name, task in normalized.items():
                submitted_at = time.monotonic()
                deadline = submitted_at + task.timeout
                breaker = self._breaker_for(task)
                future = executor.submit(
                    self._execute_with_retry,
                    task,
                    breaker,
                    deadline,
                )
                pending.add(future)
                metadata[future] = _FutureMeta(name, task, deadline, breaker)

            while pending:
                now = time.monotonic()
                completed = {future for future in pending if future.done()}
                if not completed:
                    next_deadline = min(
                        metadata[future].deadline for future in pending
                    )
                    completed, _ = wait(
                        pending,
                        timeout=max(0.0, next_deadline - now),
                        return_when=FIRST_COMPLETED,
                    )
                for future in completed:
                    pending.discard(future)
                    meta = metadata[future]
                    result.results[meta.name] = self._resolve_future(future, meta)

                now = time.monotonic()
                expired = [
                    future
                    for future in pending
                    if metadata[future].deadline <= now
                ]
                for future in expired:
                    pending.discard(future)
                    meta = metadata[future]
                    future.cancel()
                    if meta.breaker is not None:
                        meta.breaker.record_failure()
                    result.results[meta.name] = AgentResult(
                        name=meta.name,
                        status=AgentStatus.TIMEOUT,
                        error=f"Task timeout after {meta.task.timeout:g}s",
                        duration_ms=(
                            now - (meta.deadline - meta.task.timeout)
                        ) * 1000,
                    )
        finally:
            # Running threads are not force-cancellable. Return at the caller's
            # deadline and prevent queued work from starting.
            executor.shutdown(wait=False, cancel_futures=True)

        self._summarize(result)
        result.total_ms = (time.monotonic() - started) * 1000
        return result

    def breaker_snapshots(self) -> dict[str, dict[str, Any]]:
        with self._breakers_lock:
            items = list(self._breakers.items())
        return {key: breaker.snapshot() for key, breaker in items}

    def _normalize_tasks(
        self,
        tasks: dict[str, Callable | AgentTask],
    ) -> dict[str, AgentTask]:
        normalized: dict[str, AgentTask] = {}
        for name, task in tasks.items():
            if isinstance(task, AgentTask):
                normalized[name] = task
            else:
                normalized[name] = AgentTask(
                    name=name,
                    fn=task,
                    timeout=self.default_timeout,
                    retry_policy=self.default_retry,
                    max_retries=self.default_max_retries,
                )
            if normalized[name].timeout <= 0:
                raise ValueError(f"task {name!r} timeout must be positive")
            if normalized[name].max_retries < 0:
                raise ValueError(
                    f"task {name!r} max_retries cannot be negative"
                )
        return normalized

    def _breaker_for(self, task: AgentTask) -> Optional[CircuitBreaker]:
        if not self._enable_circuit_breaker:
            return None
        key = task.breaker_key or task.name
        with self._breakers_lock:
            breaker = self._breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker(
                    key,
                    failure_threshold=self._circuit_threshold,
                    recovery_timeout=self._circuit_recovery,
                    window_duration=self._circuit_window,
                    error_rate_threshold=self._circuit_error_rate,
                )
                self._breakers[key] = breaker
            return breaker

    def _execute_with_retry(
        self,
        task: AgentTask,
        breaker: Optional[CircuitBreaker],
        deadline: float,
    ) -> AgentResult:
        started = time.monotonic()
        delay = max(0.0, task.retry_delay)
        max_attempts = (
            1
            if task.retry_policy == RetryPolicy.NONE
            else task.max_retries + 1
        )
        last_error = ""
        attempts_made = 0

        for attempt in range(max_attempts):
            if time.monotonic() >= deadline:
                return AgentResult(
                    name=task.name,
                    status=AgentStatus.TIMEOUT,
                    error=f"Task timeout after {task.timeout:g}s",
                    duration_ms=(time.monotonic() - started) * 1000,
                    retries=max(0, attempts_made - 1),
                )
            if breaker is not None and not breaker.try_acquire():
                return AgentResult(
                    name=task.name,
                    status=AgentStatus.CIRCUIT_OPEN,
                    error=(
                        "Circuit breaker is open"
                        f"; retry after {breaker.retry_after:.3f}s"
                    ),
                    duration_ms=(time.monotonic() - started) * 1000,
                    retries=max(0, attempts_made - 1),
                )

            attempts_made += 1
            try:
                data = task.fn(*task.args, **task.kwargs)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if breaker is not None:
                    breaker.record_failure()
                retryable = task.retry_if(exc) if task.retry_if else True
                if attempt >= max_attempts - 1 or not retryable:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sleep_for = min(delay, remaining)
                logger.warning(
                    "AgentPool[%s]: attempt %d/%d failed: %s; retrying in %.3fs",
                    task.name,
                    attempt + 1,
                    max_attempts,
                    last_error,
                    sleep_for,
                )
                time.sleep(sleep_for)
                if task.retry_policy == RetryPolicy.EXPONENTIAL:
                    delay *= max(1.0, task.retry_backoff)
                continue

            if breaker is not None:
                breaker.record_success()
            return AgentResult(
                name=task.name,
                status=AgentStatus.SUCCESS,
                data=data,
                duration_ms=(time.monotonic() - started) * 1000,
                retries=attempt,
            )

        fallback = self._apply_fallback(task, last_error)
        fallback.duration_ms = (time.monotonic() - started) * 1000
        fallback.retries = max(0, attempts_made - 1)
        return fallback

    def _apply_fallback(self, task: AgentTask, error: str = "") -> AgentResult:
        def fallback_value():
            value = task.fallback_value
            return value() if callable(value) else value

        if task.fallback == FallbackPolicy.NONE:
            return AgentResult(
                name=task.name,
                status=AgentStatus.FAILED,
                error=error or "All retries exhausted",
            )
        if task.fallback == FallbackPolicy.EMPTY:
            value = fallback_value()
            return AgentResult(
                name=task.name,
                status=AgentStatus.FAILED,
                data={} if value is None else value,
                error=error or "Fallback: empty result",
                fallback_used=True,
            )
        if task.fallback == FallbackPolicy.MOCK:
            value = fallback_value()
            return AgentResult(
                name=task.name,
                status=AgentStatus.FAILED,
                data={"_mock": True} if value is None else value,
                error=error or "Fallback: mock result",
                fallback_used=True,
            )
        if task.fallback == FallbackPolicy.CACHED:
            try:
                value = fallback_value()
            except Exception as exc:
                return AgentResult(
                    name=task.name,
                    status=AgentStatus.FAILED,
                    error=(
                        f"Cached fallback failed: {type(exc).__name__}: {exc}"
                    ),
                    fallback_used=True,
                )
            if value is None:
                return AgentResult(
                    name=task.name,
                    status=AgentStatus.FAILED,
                    error=error or "Cached fallback returned no value",
                    fallback_used=True,
                )
            return AgentResult(
                name=task.name,
                status=AgentStatus.SUCCESS,
                data=value,
                error=error,
                fallback_used=True,
            )
        if task.fallback == FallbackPolicy.SKIP:
            return AgentResult(
                name=task.name,
                status=AgentStatus.SKIPPED,
                error=error or "Skipped by fallback policy",
                fallback_used=True,
            )
        return AgentResult(
            name=task.name,
            status=AgentStatus.FAILED,
            error=f"Unknown fallback policy: {task.fallback}",
        )

    @staticmethod
    def _resolve_future(future: Future, meta: _FutureMeta) -> AgentResult:
        try:
            return future.result()
        except Exception as exc:
            if meta.breaker is not None:
                meta.breaker.record_failure()
            return AgentResult(
                name=meta.name,
                status=AgentStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _summarize(result: PoolResult) -> None:
        result.success_count = sum(
            item.status == AgentStatus.SUCCESS for item in result.results.values()
        )
        result.failure_count = sum(
            item.status == AgentStatus.FAILED for item in result.results.values()
        )
        result.timeout_count = sum(
            item.status == AgentStatus.TIMEOUT for item in result.results.values()
        )
        result.circuit_open_count = sum(
            item.status == AgentStatus.CIRCUIT_OPEN
            for item in result.results.values()
        )
