import json
from typing import Any, List

import redis.asyncio as redis

from src.config import config
from src.interfaces.history_service_interface import IHistoryService


class RedisService(IHistoryService):
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def save_run_results(self, request_id: str, results: List[Any]) -> None:
        key = f"undo:{request_id}"
        await self._redis.set(
            key, json.dumps(results), ex=config.UNDO_EXPIRATION_SECONDS
        )

    async def get_run_results(self, request_id: str) -> List[Any]:
        key = f"undo:{request_id}"
        data = await self._redis.get(key)
        return json.loads(data) if data else []

    async def delete_run_results(self, request_id: str) -> None:
        key = f"undo:{request_id}"
        await self._redis.delete(key)
