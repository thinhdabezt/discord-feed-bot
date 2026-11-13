from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import FeedSource
from app.schemas import FeedItemData
from app.services.feed_runner import FeedRunner


def make_runner(tmp_path, database=None, collectors=None):
    return FeedRunner(
        database=database or MagicMock(),
        collectors=collectors or {},
        interval_seconds=600,
        max_items_per_source=10,
        sources_file=tmp_path / "sources.yaml",
        discord_channel_id=123456,
    )


class AsyncContext:
    """Small async context manager for mocking database sessions."""

    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


def test_load_sources_only_returns_enabled_sources(tmp_path):
    runner = make_runner(tmp_path)

    runner.sources_file.write_text(
        """
sources:
  - key: source-a
    name: Source A
    platform: rss
    url: https://example.com/a.xml
    enabled: true

  - key: source-b
    name: Source B
    platform: rss
    url: https://example.com/b.xml
    enabled: false
""",
        encoding="utf-8",
    )

    sources = runner.load_sources()

    assert len(sources) == 1
    assert sources[0]["key"] == "source-a"


def test_load_sources_returns_empty_when_sources_is_not_a_list(tmp_path):
    runner = make_runner(tmp_path)

    runner.sources_file.write_text(
        "sources: invalid-value",
        encoding="utf-8",
    )

    assert runner.load_sources() == []


def test_load_sources_returns_empty_when_file_missing(tmp_path):
    runner = make_runner(tmp_path)

    assert runner.load_sources() == []


@pytest.mark.asyncio
async def test_store_item_returns_true_when_item_is_inserted(tmp_path):
    runner = make_runner(tmp_path)

    result = MagicMock()
    result.scalar_one_or_none.return_value = 100

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    source = FeedSource(id=1)
    item = FeedItemData(
        external_id="article-1",
        title="Test Article",
        url="https://example.com/article-1",
    )

    inserted = await runner._store_item(session, source, item)

    assert inserted is True
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_item_returns_false_when_duplicate_exists(tmp_path):
    runner = make_runner(tmp_path)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    source = FeedSource(id=1)
    item = FeedItemData(
        external_id="article-1",
        title="Test Article",
        url="https://example.com/article-1",
    )

    inserted = await runner._store_item(session, source, item)

    assert inserted is False


@pytest.mark.asyncio
async def test_record_delivery_success_updates_item(tmp_path):
    item = SimpleNamespace(
        notification_attempts=0,
        notified_at=None,
        last_notification_error="Previous error",
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=item)
    session.begin = lambda: AsyncContext(None)

    database = MagicMock()
    database.sessions = lambda: AsyncContext(session)

    runner = make_runner(tmp_path, database=database)

    await runner._record_delivery(item_id=1, success=True)

    assert item.notification_attempts == 1
    assert item.notified_at is not None
    assert item.last_notification_error is None


@pytest.mark.asyncio
async def test_record_delivery_failure_stores_error(tmp_path):
    item = SimpleNamespace(
        notification_attempts=0,
        notified_at=None,
        last_notification_error=None,
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=item)
    session.begin = lambda: AsyncContext(None)

    database = MagicMock()
    database.sessions = lambda: AsyncContext(session)

    runner = make_runner(tmp_path, database=database)

    await runner._record_delivery(
        item_id=1,
        success=False,
        error="Discord is unavailable",
    )

    assert item.notification_attempts == 1
    assert item.notified_at is None
    assert item.last_notification_error == "Discord is unavailable"


@pytest.mark.asyncio
async def test_deliver_pending_continues_after_notification_failure(tmp_path):
    pending_items = [
        (
            SimpleNamespace(
                id=1,
                title="Article that fails",
                url="https://example.com/1",
                summary=None,
            ),
            "Source A",
        ),
        (
            SimpleNamespace(
                id=2,
                title="Article that succeeds",
                url="https://example.com/2",
                summary=None,
            ),
            "Source A",
        ),
    ]

    result = MagicMock()
    result.all.return_value = pending_items

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    database = MagicMock()
    database.sessions = lambda: AsyncContext(session)

    runner = make_runner(tmp_path, database=database)

    async def fake_notify(bot, source_name, title, url, summary):
        if title == "Article that fails":
            raise RuntimeError("Discord unavailable")

    runner._notify = fake_notify
    runner._record_delivery = AsyncMock()

    await runner._deliver_pending(MagicMock())

    calls = runner._record_delivery.await_args_list

    assert len(calls) == 2

    # First item: notification failed
    assert calls[0].args[0] == 1
    assert calls[0].kwargs["success"] is False
    assert calls[0].kwargs["error"] == "Discord unavailable"

    # Second item: notification succeeded
    assert calls[1].args[0] == 2
    assert calls[1].kwargs["success"] is True


@pytest.mark.asyncio
async def test_close_closes_shared_collector_only_once(tmp_path):
    collector = MagicMock()
    collector.platform = "rss"
    collector.close = AsyncMock()

    runner = make_runner(
        tmp_path,
        collectors={
            "rss": collector,
            "rss_alias": collector,
        },
    )

    await runner.close()

    collector.close.assert_awaited_once()
