import httpx
import pytest

from app.sources.rss import RssCollector, parse_published


def test_parse_published_missing():
    assert parse_published({}) is None


def test_parse_published_invalid_date():
    assert parse_published({"published": "not-a-date"}) is None


@pytest.mark.asyncio
async def test_collect_valid_rss_feed():
    rss_content = b"""
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Test Feed</title>
        <item>
          <title>Test Article</title>
          <link>https://example.com/article-1</link>
          <guid>article-1</guid>
          <description>Test summary</description>
        </item>
      </channel>
    </rss>
    """

    async def handler(request):
        return httpx.Response(
            200,
            content=rss_content,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        collector = RssCollector(client)

        items = await collector.collect(
            {"url": "https://example.com/feed"},
            limit=10,
        )

    assert len(items) == 1
    assert items[0].external_id == "article-1"
    assert items[0].title == "Test Article"
    assert items[0].url == "https://example.com/article-1"


@pytest.mark.asyncio
async def test_collect_http_error():
    async def handler(request):
        return httpx.Response(
            503,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        collector = RssCollector(client)

        with pytest.raises(httpx.HTTPStatusError):
            await collector.collect(
                {"url": "https://example.com/feed"},
                limit=10,
            )
