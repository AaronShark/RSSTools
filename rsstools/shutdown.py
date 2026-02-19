"""Graceful shutdown management for RSSTools."""

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

from .logging_config import get_logger

logger = get_logger(__name__)

CleanupCallback = Callable[[], None]


class ShutdownManager:
  """Manages graceful shutdown with cleanup callbacks and operation tracking."""

  def __init__(self, shutdown_timeout: float = 30.0):
    self._shutdown_timeout = shutdown_timeout
    self._cleanup_callbacks: list[CleanupCallback] = []
    self._in_flight = 0
    self._in_flight_lock = asyncio.Lock()
    self._shutdown_event = asyncio.Event()
    self._in_flight_zero = asyncio.Event()
    self._in_flight_zero.set()
    self._loop: Optional[asyncio.AbstractEventLoop] = None

  @property
  def is_shutting_down(self) -> bool:
    return self._shutdown_event.is_set()

  def register_callback(self, callback: CleanupCallback) -> None:
    self._cleanup_callbacks.append(callback)
    logger.debug("shutdown_callback_registered", total=len(self._cleanup_callbacks))

  @asynccontextmanager
  async def track_operation(self) -> AsyncIterator[None]:
    async with self._in_flight_lock:
      self._in_flight += 1
      self._in_flight_zero.clear()
    try:
      yield
    finally:
      async with self._in_flight_lock:
        self._in_flight -= 1
        if self._in_flight <= 0:
          self._in_flight = 0
          self._in_flight_zero.set()

  def setup_signal_handlers(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    self._loop = loop or asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
      try:
        self._loop.add_signal_handler(sig, lambda s=sig: self._signal_handler(s))
        logger.debug("signal_handler_registered", signal=sig.name)
      except NotImplementedError:
        logger.debug("signal_handler_not_supported", signal=sig.name)

  def _signal_handler(self, sig: signal.Signals) -> None:
    logger.info("shutdown_signal_received", signal=sig.name)
    self._shutdown_event.set()
    if self._loop:
      self._loop.create_task(self._execute_shutdown())

  async def _execute_shutdown(self) -> None:
    logger.info(
      "shutdown_started",
      in_flight=self._in_flight,
      callbacks=len(self._cleanup_callbacks),
    )

    try:
      await asyncio.wait_for(
        self._in_flight_zero.wait(),
        timeout=self._shutdown_timeout,
      )
      logger.info("shutdown_all_operations_completed")
    except TimeoutError:
      logger.warning(
        "shutdown_timeout",
        timeout=self._shutdown_timeout,
        remaining_in_flight=self._in_flight,
      )

    for callback in reversed(self._cleanup_callbacks):
      try:
        callback()
        logger.debug("shutdown_callback_executed")
      except Exception as e:
        logger.error("shutdown_callback_error", error=str(e))

    logger.info("shutdown_complete")

  async def wait_for_shutdown(self) -> None:
    await self._shutdown_event.wait()
