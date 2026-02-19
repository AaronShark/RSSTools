"""Tests for HTTPClient shared connection pool."""

import pytest

from rsstools.http_client import HTTPClient


class TestHTTPClient:
  """Tests for HTTPClient class."""

  async def test_context_manager_connects_and_disconnects(self):
    async with HTTPClient() as client:
      assert client._session is not None
      assert not client._session.closed
    assert client._session is None

  async def test_explicit_connect_disconnect(self):
    client = HTTPClient()
    await client.connect()
    assert client._session is not None
    assert not client._session.closed
    await client.disconnect()
    assert client._session is None

  async def test_session_property_raises_before_connect(self):
    client = HTTPClient()
    with pytest.raises(RuntimeError, match="not connected"):
      _ = client.session

  async def test_session_property_returns_session_after_connect(self):
    client = HTTPClient()
    await client.connect()
    session = client.session
    assert session is not None
    assert not session.closed
    await client.disconnect()

  async def test_connect_idempotent(self):
    client = HTTPClient()
    await client.connect()
    session1 = client._session
    await client.connect()
    assert client._session is session1
    await client.disconnect()

  async def test_disconnect_idempotent(self):
    client = HTTPClient()
    await client.connect()
    await client.disconnect()
    await client.disconnect()
    assert client._session is None

  async def test_disconnect_safe_when_not_connected(self):
    client = HTTPClient()
    await client.disconnect()
    assert client._session is None

  async def test_custom_connection_limits(self):
    client = HTTPClient(
      total_connections=50,
      per_host_connections=5,
      connect_timeout=5.0,
      total_timeout=30.0,
    )
    async with client:
      assert client._total_connections == 50
      assert client._per_host_connections == 5
      assert client._connect_timeout == 5.0
      assert client._total_timeout == 30.0

  async def test_context_manager_with_exception(self):
    try:
      async with HTTPClient() as client:
        assert client._session is not None
        raise ValueError("test error")
    except ValueError:
      pass
