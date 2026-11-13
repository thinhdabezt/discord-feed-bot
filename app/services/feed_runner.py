import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import discord
import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import FeedItem, FeedSource
from app.schemas import FeedItemData

logger = logging.getLogger(__name__)


class FeedRunner:
    def __init__(
        self,
        database,
        collectors: dict,
        interval_seconds: int,
        max_items_per_source: int,
        sources_file: Path,
        discord_channel_id: int,
    ):
        self.database = database
        self.collectors = collectors
        self.interval_seconds = interval_seconds
        self.max_items_per_source = max_items_per_source
        self.sources_file = sources_file
        self.discord_channel_id = discord_channel_id
        self._poll_lock = asyncio.Lock()

    async def close(self) -> None:
        closed_collectors: set[int] = set()

        for collector in self.collectors.values():
            collector_id = id(collector)

            if collector_id in closed_collectors:
                continue

            closed_collectors.add(collector_id)

            try:
                await collector.close()
                logger.info(
                    "Collector closed: platform=%s",
                    getattr(collector, "platform", "unknown"),
                )
            except Exception:
                logger.exception(
                    "Failed to close collector: platform=%s",
                    getattr(collector, "platform", "unknown"),
                )

    async def _record_delivery(
        self,
        item_id: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        async with self.database.sessions() as session, session.begin():
            item = await session.get(FeedItem, item_id)

            if item is None or item.notified_at is not None:
                return

            item.notification_attempts += 1

            if success:
                item.notified_at = datetime.now(UTC)
                item.last_notification_error = None
            else:
                item.last_notification_error = (error or "Unknown error")[:2000]

    async def _notify(
        self,
        bot: discord.Client,
        source_name: str,
        title: str,
        url: str,
        summary: str | None,
    ) -> None:
        channel = bot.get_channel(self.discord_channel_id)

        if channel is None:
            channel = await bot.fetch_channel(self.discord_channel_id)

        safe_title = discord.utils.escape_markdown(title)
        safe_source = discord.utils.escape_markdown(source_name)

        message = f"**{safe_source}**\n{safe_title}\n{url}"

        if summary:
            summary = " ".join(summary.split())

            if len(summary) > 500:
                summary = summary[:497] + "..."

            message += f"\n{summary}"

        await channel.send(message[:1900])

    async def _deliver_pending(self, bot: discord.Client) -> None:
        async with self.database.sessions() as session:
            result = await session.execute(
                select(FeedItem, FeedSource.name)
                .join(FeedSource, FeedItem.source_id == FeedSource.id)
                .where(FeedItem.notified_at.is_(None))
                .order_by(FeedItem.discovered_at.asc())
                .limit(50)
            )

            pending = [
                (
                    item.id,
                    source_name,
                    item.title,
                    item.url,
                    item.summary,
                )
                for item, source_name in result.all()
            ]

        for item_id, source_name, title, url, summary in pending:
            try:
                await self._notify(
                    bot,
                    source_name,
                    title,
                    url,
                    summary,
                )

                await self._record_delivery(item_id, success=True)

                logger.info("Notification delivered: item_id=%s", item_id)

            except Exception as exc:
                logger.exception(
                    "Notification failed: item_id=%s",
                    item_id,
                )

                try:
                    await self._record_delivery(
                        item_id,
                        success=False,
                        error=str(exc),
                    )
                except Exception:
                    logger.exception(
                        "Failed to record notification error: item_id=%s",
                        item_id,
                    )

    def load_sources(self) -> list[dict]:
        path = self.sources_file

        if not path.is_file():
            logger.error("Sources configuration file not found: %s", path)
            return []

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        if not isinstance(payload, dict):
            logger.error("Invalid sources configuration format: %s", path)
            return []

        sources = payload.get("sources", [])

        if not isinstance(sources, list):
            logger.error("The 'sources' field must be a list: %s", path)
            return []

        return [
            source
            for source in sources
            if isinstance(source, dict) and source.get("enabled", False)
        ]

    async def _get_or_create_source(self, session, config: dict) -> FeedSource:
        result = await session.execute(select(FeedSource).where(FeedSource.key == config["key"]))
        source = result.scalar_one_or_none()
        if source is None:
            source = FeedSource(
                key=config["key"],
                name=config["name"],
                platform=config["platform"],
                url=config["url"],
                enabled=config.get("enabled", True),
            )
            session.add(source)
            await session.flush()
        else:
            source.name = config["name"]
            source.platform = config["platform"]
            source.url = config["url"]
            source.enabled = config.get("enabled", True)
        return source

    async def _store_item(self, session, source: FeedSource, item: FeedItemData) -> bool:
        statement = (
            pg_insert(FeedItem)
            .values(
                source_id=source.id,
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                summary=item.summary,
                published_at=item.published_at,
            )
            .on_conflict_do_nothing(index_elements=["source_id", "external_id"])
            .returning(FeedItem.id)
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def poll_once(self, bot: discord.Client) -> int:
        if self._poll_lock.locked():
            logger.info("Poll skipped: another poll is still running.")
            return 0

        async with self._poll_lock:
            total_new = 0
            for config in self.load_sources():
                platform = config["platform"]
                collector = self.collectors.get(platform)
                if collector is None:
                    logger.warning("No collector registered for platform=%s", platform)
                    continue

                try:
                    items = await collector.collect(config, self.max_items_per_source)
                    async with self.database.sessions() as session, session.begin():
                        source = await self._get_or_create_source(session, config)
                        new_items = []
                        for item in items:
                            if await self._store_item(session, source, item):
                                new_items.append(item)

                    total_new += len(new_items)
                    logger.info(
                        "source=%s fetched=%d new=%d",
                        config["key"], len(items), len(new_items)
                    )
                except Exception:
                    logger.exception("Collector failed for source=%s", config.get("key"))
            await self._deliver_pending(bot)
            return total_new

    async def run_forever(self, bot: discord.Client) -> None:
        await bot.wait_until_ready()

        logger.info(
            "Feed poller started. Interval: %s seconds",
            self.interval_seconds,
        )

        while not bot.is_closed():
            try:
                await self.poll_once(bot)

            except asyncio.CancelledError:
                logger.info("Feed poller cancellation requested.")
                raise

            except Exception:
                logger.exception(
                    "Unexpected error during polling cycle. "
                    "The poller will continue."
                )

            await asyncio.sleep(self.interval_seconds)
