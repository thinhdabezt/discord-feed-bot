import asyncio
import logging
from pathlib import Path

import discord
import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import FeedItem, FeedSource
from app.schemas import FeedItemData

logger = logging.getLogger(__name__)


class FeedRunner:
    def __init__(self, database, collectors: dict, interval_seconds: int, max_items_per_source: int):
        self.database = database
        self.collectors = collectors
        self.interval_seconds = interval_seconds
        self.max_items_per_source = max_items_per_source
        self._poll_lock = asyncio.Lock()

    def load_sources(self) -> list[dict]:
        path = Path("sources.yaml")
        if not path.exists():
            path = Path("sources.example.yaml")
        if not path.exists():
            logger.warning("No sources.yaml found; no feeds will be polled.")
            return []
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return [s for s in payload.get("sources", []) if s.get("enabled", False)]

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
        # PostgreSQL-native upsert prevents duplicate notifications under concurrent polls.
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
                    async with self.database.sessions() as session:
                        async with session.begin():
                            source = await self._get_or_create_source(session, config)
                            new_items = []
                            for item in items:
                                if await self._store_item(session, source, item):
                                    new_items.append(item)

                    total_new += len(new_items)
                    for item in new_items:
                        await self._notify(bot, config["name"], item)
                    logger.info(
                        "source=%s fetched=%d new=%d",
                        config["key"], len(items), len(new_items)
                    )
                except Exception:
                    logger.exception("Collector failed for source=%s", config.get("key"))
            return total_new

    async def _notify(self, bot: discord.Client, source_name: str, item: FeedItemData) -> None:
        from app.config import get_settings

        channel = bot.get_channel(get_settings().discord_channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(get_settings().discord_channel_id)
            except discord.DiscordException:
                logger.exception("Unable to access notification channel.")
                return

        title = discord.utils.escape_markdown(item.title)
        message = f"**{discord.utils.escape_markdown(source_name)}**\n{title}\n{item.url}"
        if item.summary:
            summary = " ".join(item.summary.split())
            if len(summary) > 500:
                summary = summary[:497] + "..."
            message += f"\n{summary}"
        await channel.send(message[:1900])

    async def run_forever(self, bot: discord.Client) -> None:
        await bot.wait_until_ready()
        while not bot.is_closed():
            await self.poll_once(bot)
            await asyncio.sleep(self.interval_seconds)
