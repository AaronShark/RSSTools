"""Tests for Container dependency injection."""

import os
import tempfile

import pytest

from rsstools.container import Container
from rsstools.models import Config


@pytest.fixture
def temp_dir():
  with tempfile.TemporaryDirectory() as tmpdir:
    yield tmpdir


@pytest.fixture
def config(temp_dir):
  return Config(
    base_dir=temp_dir,
    opml_path=os.path.join(temp_dir, "feeds.opml"),
  )


class TestContainer:
  """Tests for Container class."""

  async def test_context_manager_connects_and_disconnects(self, config):
    async with Container(config) as container:
      assert container._db is not None
    assert container._db is None

  async def test_explicit_connect_disconnect(self, config):
    container = Container(config)
    await container.connect()
    assert container._db is not None
    await container.disconnect()
    assert container._db is None

  async def test_db_lazy_initialization(self, config):
    container = Container(config)
    assert container._db is None
    db = container.db
    assert db is not None
    assert container._db is db

  async def test_article_repo_lazy_initialization(self, config):
    async with Container(config) as container:
      assert container._article_repo is None
      repo = container.article_repo
      assert repo is not None
      assert container._article_repo is repo

  async def test_feed_repo_lazy_initialization(self, config):
    async with Container(config) as container:
      assert container._feed_repo is None
      repo = container.feed_repo
      assert repo is not None
      assert container._feed_repo is repo

  async def test_cache_repo_lazy_initialization(self, config):
    async with Container(config) as container:
      assert container._cache_repo is None
      repo = container.cache_repo
      assert repo is not None
      assert container._cache_repo is repo

  async def test_llm_cache_lazy_initialization(self, config):
    container = Container(config)
    assert container._llm_cache is None
    cache = container.llm_cache
    assert cache is not None
    assert container._llm_cache is cache

  async def test_llm_client_lazy_initialization(self, config):
    container = Container(config)
    assert container._llm_client is None
    client = container.llm_client
    assert client is not None
    assert container._llm_client is client

  async def test_llm_client_disabled_without_api_key(self, config):
    container = Container(config)
    client = container.llm_client
    assert not client.enabled

  async def test_repos_share_same_db(self, config):
    async with Container(config) as container:
      db = container.db
      assert container.article_repo._db is db
      assert container.feed_repo._db is db
      assert container.cache_repo._db is db

  async def test_llm_client_uses_llm_cache(self, config):
    container = Container(config)
    cache = container.llm_cache
    client = container.llm_client
    assert client.cache is cache

  async def test_disconnect_safe_when_not_connected(self, config):
    container = Container(config)
    await container.disconnect()
    assert container._db is None

  async def test_disconnect_idempotent(self, config):
    container = Container(config)
    await container.connect()
    await container.disconnect()
    await container.disconnect()
    assert container._db is None

  async def test_context_manager_with_exception(self, config):
    try:
      async with Container(config) as container:
        assert container._db is not None
        raise ValueError("test error")
    except ValueError:
      pass
    assert container._db is None

  async def test_multiple_containers_independent(self, temp_dir):
    config1 = Config(base_dir=temp_dir, opml_path=os.path.join(temp_dir, "1.opml"))
    config2 = Config(base_dir=temp_dir, opml_path=os.path.join(temp_dir, "2.opml"))

    async with Container(config1) as c1:
      async with Container(config2) as c2:
        assert c1.db is not c2.db
        assert c1.article_repo is not c2.article_repo

  async def test_http_client_lazy_initialization(self, config):
    container = Container(config)
    assert container._http_client is None
    client = container.http_client
    assert client is not None
    assert container._http_client is client

  async def test_http_session_raises_before_connect(self, config):
    container = Container(config)
    with pytest.raises(RuntimeError, match="not connected"):
      _ = container.http_session

  async def test_http_session_available_after_connect(self, config):
    container = Container(config)
    await container.connect()
    session = container.http_session
    assert session is not None
    assert not session.closed
    await container.disconnect()

  async def test_disconnect_closes_http_client(self, config):
    container = Container(config)
    await container.connect()
    assert container._http_client is not None
    await container.disconnect()
    assert container._http_client is None

