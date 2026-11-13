import httpx

from app.config import Settings
from app.sources.rss import RssCollector


def build_collectors(settings: Settings):
    client = httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    )
    # Keep the client alive for the lifetime of the application.
    return {"rss": RssCollector(client)}
