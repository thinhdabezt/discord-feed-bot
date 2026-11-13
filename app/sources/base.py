from abc import ABC, abstractmethod

from app.schemas import FeedItemData


class BaseCollector(ABC):
    platform: str

    @abstractmethod
    async def collect(self, source: dict, limit: int) -> list[FeedItemData]:
        raise NotImplementedError

    async def close(self) -> None:
        pass
