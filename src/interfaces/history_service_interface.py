from abc import ABC, abstractmethod
from typing import Any, List


class IHistoryService(ABC):
    @abstractmethod
    async def save_run_results(self, request_id: str, results: List[Any]) -> None:
        pass

    @abstractmethod
    async def get_run_results(self, request_id: str) -> List[Any]:
        pass

    @abstractmethod
    async def delete_run_results(self, request_id: str) -> None:
        pass
