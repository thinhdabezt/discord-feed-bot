from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class FeedItemData:
    external_id: str
    title: str
    url: str
    summary: str | None = None
    published_at: datetime | None = None
