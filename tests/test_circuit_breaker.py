"""Tests for circuit breaker pattern."""

import asyncio
from datetime import datetime, timedelta

import pytest

from rsstools.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_closed_allows_execution(self):
        cb = CircuitBreaker()

        async def run():
            assert await cb.can_execute() is True

        asyncio.run(run())

    def test_records_failures(self):
        cb = CircuitBreaker(failure_threshold=3)

        async def run():
            await cb.record_failure()
            assert cb._failure_count == 1
            assert cb.state == CircuitState.CLOSED

            await cb.record_failure()
            assert cb._failure_count == 2
            assert cb.state == CircuitState.CLOSED

            await cb.record_failure()
            assert cb._failure_count == 3
            assert cb.state == CircuitState.OPEN

        asyncio.run(run())

    def test_open_blocks_execution(self):
        cb = CircuitBreaker(failure_threshold=1)

        async def run():
            await cb.record_failure()
            assert cb.state == CircuitState.OPEN
            assert await cb.can_execute() is False

        asyncio.run(run())

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        async def run():
            await cb.record_failure()
            assert cb.state == CircuitState.OPEN

            await asyncio.sleep(0.15)
            assert await cb.can_execute() is True
            assert cb.state == CircuitState.HALF_OPEN

        asyncio.run(run())

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, recovery_timeout=0.1)

        async def run():
            await cb.record_failure()
            await asyncio.sleep(0.15)
            await cb.can_execute()

            await cb.record_success()
            assert cb.state == CircuitState.HALF_OPEN
            assert cb._success_count == 1

            await cb.record_success()
            assert cb.state == CircuitState.CLOSED
            assert cb._failure_count == 0

        asyncio.run(run())

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        async def run():
            await cb.record_failure()
            await asyncio.sleep(0.15)
            await cb.can_execute()

            await cb.record_failure()
            assert cb.state == CircuitState.OPEN

        asyncio.run(run())

    def test_call_succeeds(self):
        cb = CircuitBreaker()

        async def run():
            async def success_func():
                return "result"

            result = await cb.call(success_func)
            assert result == "result"

        asyncio.run(run())

    def test_call_tracks_failures(self):
        cb = CircuitBreaker(failure_threshold=2)

        async def run():
            async def fail_func():
                raise ValueError("error")

            with pytest.raises(ValueError):
                await cb.call(fail_func)
            assert cb._failure_count == 1

            with pytest.raises(ValueError):
                await cb.call(fail_func)
            assert cb._failure_count == 2
            assert cb.state == CircuitState.OPEN

        asyncio.run(run())

    def test_call_blocked_when_open(self):
        cb = CircuitBreaker(failure_threshold=1)

        async def run():
            async def fail_func():
                raise ValueError("error")

            async def success_func():
                return "result"

            with pytest.raises(ValueError):
                await cb.call(fail_func)

            with pytest.raises(Exception, match="Circuit breaker is open"):
                await cb.call(success_func)

        asyncio.run(run())

    def test_resets_on_success_in_closed_state(self):
        cb = CircuitBreaker(failure_threshold=5)

        async def run():
            await cb.record_failure()
            await cb.record_failure()
            assert cb._failure_count == 2

            await cb.record_success()
            assert cb._failure_count == 0

        asyncio.run(run())

    def test_success_threshold_configurable(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=3, recovery_timeout=0.1)

        async def run():
            await cb.record_failure()
            await asyncio.sleep(0.15)
            await cb.can_execute()

            for _ in range(2):
                await cb.record_success()
            assert cb.state == CircuitState.HALF_OPEN

            await cb.record_success()
            assert cb.state == CircuitState.CLOSED

        asyncio.run(run())
