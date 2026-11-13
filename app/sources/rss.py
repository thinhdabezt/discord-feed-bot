import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from app.schemas import FeedItemData
from app.sources.base import BaseCollector

logger = logging.getLogger(__name__)


def parse_published(entry) -> datetime | None:
    value = entry.get("published") or entry.get("updated")
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


class RssCollector(BaseCollector):
    platform = "rss"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def collect(self, source: dict, limit: int) -> list[FeedItemData]:
        response = await self.client.get(source["url"])
        response.raise_for_status()
        parsed = await asyncio.to_thread(feedparser.parse, response.content)

        items: list[FeedItemData] = []
        for entry in parsed.entries[:limit]:
            url = entry.get("link")
            title = (entry.get("title") or "Untitled").strip()
            if not url:
                continue
            external_id = str(entry.get("id") or entry.get("guid") or url)
            summary = entry.get("summary")
            items.append(
                FeedItemData(
                    external_id=external_id[:500],
                    title=title[:1000],
                    url=url,
                    summary=summary,
                    published_at=parse_published(entry),
                )
            )
        return items

    async def close(self) -> None:
        await self.client.aclose()
