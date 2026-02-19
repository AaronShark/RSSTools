"""Tests for ShutdownManager graceful shutdown."""

import asyncio

import pytest

from rsstools.shutdown import ShutdownManager


class TestShutdownManager:
  """Tests for ShutdownManager class."""

  def test_initial_state(self):
    manager = ShutdownManager()
    assert not manager.is_shutting_down
    assert len(manager._cleanup_callbacks) == 0
    assert manager._in_flight == 0

  def test_register_callback(self):
    manager = ShutdownManager()
    called = []

    def cleanup():
      called.append(True)

    manager.register_callback(cleanup)
    assert len(manager._cleanup_callbacks) == 1

  def test_multiple_callbacks(self):
    manager = ShutdownManager()
    manager.register_callback(lambda: None)
    manager.register_callback(lambda: None)
    manager.register_callback(lambda: None)
    assert len(manager._cleanup_callbacks) == 3

  async def test_track_operation(self):
    manager = ShutdownManager()
    assert manager._in_flight == 0

    async with manager.track_operation():
      assert manager._in_flight == 1

    assert manager._in_flight == 0

  async def test_multiple_concurrent_operations(self):
    manager = ShutdownManager()

    async def op(delay):
      async with manager.track_operation():
        await asyncio.sleep(delay)

    tasks = [op(0.01) for _ in range(5)]
    await asyncio.gather(*tasks)
    assert manager._in_flight == 0

  async def test_shutdown_event(self):
    manager = ShutdownManager()
    assert not manager.is_shutting_down
    manager._shutdown_event.set()
    assert manager.is_shutting_down

  async def test_callbacks_executed_in_reverse_order(self):
    manager = ShutdownManager()
    order = []

    manager.register_callback(lambda: order.append(1))
    manager.register_callback(lambda: order.append(2))
    manager.register_callback(lambda: order.append(3))

    await manager._execute_shutdown()
    assert order == [3, 2, 1]

  async def test_callback_exception_handled(self):
    manager = ShutdownManager()
    called = []

    def bad_cleanup():
      raise RuntimeError("cleanup error")

    def good_cleanup():
      called.append(True)

    manager.register_callback(bad_cleanup)
    manager.register_callback(good_cleanup)

    await manager._execute_shutdown()
    assert called == [True]

  def test_signal_handler_setup(self):
    manager = ShutdownManager()
    loop = None
    try:
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      manager.setup_signal_handlers(loop)
    except NotImplementedError:
      pass
    finally:
      if loop:
        loop.close()

  async def test_wait_for_in_flight_operations(self):
    manager = ShutdownManager(shutdown_timeout=1.0)
    completed = []

    async def slow_op():
      async with manager.track_operation():
        await asyncio.sleep(0.1)
        completed.append(True)

    task = asyncio.create_task(slow_op())
    await asyncio.sleep(0.01)
    assert manager._in_flight == 1

    await manager._execute_shutdown()
    await task
    assert manager._in_flight == 0
    assert completed == [True]
