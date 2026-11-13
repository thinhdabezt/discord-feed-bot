import asyncio
import logging

import discord
from discord.ext import commands

from app.config import get_settings
from app.database import Database
from app.services.feed_runner import FeedRunner
from app.sources.registry import build_collectors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("feedbot")


class FeedBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.settings = get_settings()
        self.database = Database(self.settings.database_url)
        self.runner = FeedRunner(
            database=self.database,
            collectors=build_collectors(self.settings),
            interval_seconds=self.settings.poll_interval_seconds,
            max_items_per_source=self.settings.max_items_per_source,
            sources_file=self.settings.sources_file,
            discord_channel_id=self.settings.discord_channel_id,
        )
        self.poll_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        if self.settings.db_create_tables:
            logger.warning(
                "DB_CREATE_TABLES=true: creating missing tables for development. "
                "Use Alembic migrations before production."
            )
            await self.database.create_tables()

        await self.tree.sync()
        self.poll_task = asyncio.create_task(self.runner.run_forever(self), name="feed-poller")

    async def close(self) -> None:
        if self.poll_task:
            self.poll_task.cancel()
            try:
                await self.poll_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error while stopping feed poller")

        try:
            await self.runner.close()
        finally:
            try:
                await self.database.close()
            finally:
                await super().close()


bot = FeedBot()


@bot.tree.command(name="health", description="Check whether the feed bot is online.")
async def health(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("Feed bot is online.", ephemeral=True)


@bot.tree.command(name="poll", description="Trigger a manual feed poll.")
async def poll_now(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        count = await bot.runner.poll_once(bot)
        await interaction.followup.send(
            f"Polling finished. {count} new item(s) stored.",
            ephemeral=True,
        )
    except Exception:
        logger.exception("Manual polling failed")
        await interaction.followup.send(
            "Polling failed. Please check the bot logs.",
            ephemeral=True,
        )


def main() -> None:
    settings = get_settings()
    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN is missing.")
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
