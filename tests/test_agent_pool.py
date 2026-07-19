import threading
import time

from app.core.agent_pool import (
    AgentPool,
    AgentStatus,
    AgentTask,
    CircuitBreaker,
    FallbackPolicy,
    RetryPolicy,
)


def test_task_timeout_returns_without_waiting_for_worker_completion():
    release = threading.Event()

    def blocked():
        release.wait(timeout=0.3)
        return "late"

    pool = AgentPool(max_workers=1, enable_circuit_breaker=False)
    started = time.perf_counter()
    try:
        result = pool.execute_all({
            "slow": AgentTask(
                name="slow",
                fn=blocked,
                timeout=0.03,
                retry_policy=RetryPolicy.NONE,
                fallback=FallbackPolicy.NONE,
            )
        })
    finally:
        release.set()

    elapsed = time.perf_counter() - started
    assert elapsed < 0.15
    assert result.get("slow").status == AgentStatus.TIMEOUT
    assert result.timeout_count == 1


def test_half_open_allows_only_one_probe():
    breaker = CircuitBreaker(
        "provider",
        failure_threshold=1,
        recovery_timeout=0.01,
    )
    breaker.record_failure()
    time.sleep(0.02)

    assert breaker.try_acquire() is True
    assert breaker.try_acquire() is False

    breaker.record_success()
    assert breaker.try_acquire() is True


def test_cached_fallback_can_call_a_stale_value_provider():
    pool = AgentPool(max_workers=1, enable_circuit_breaker=False)

    def fail():
        raise RuntimeError("provider unavailable")

    result = pool.execute_all({
        "cached": AgentTask(
            name="cached",
            fn=fail,
            retry_policy=RetryPolicy.NONE,
            fallback=FallbackPolicy.CACHED,
            fallback_value=lambda: {"source": "stale-cache"},
        )
    })

    task_result = result.get("cached")
    assert task_result.status == AgentStatus.SUCCESS
    assert task_result.data == {"source": "stale-cache"}
    assert task_result.fallback_used is True

