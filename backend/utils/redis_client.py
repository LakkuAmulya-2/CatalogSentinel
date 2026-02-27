"""Optional Redis client — graceful fallback if Redis unavailable."""
import asyncio
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import redis.asyncio as aioredis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False


class RedisClient:
    _instance: Optional[object] = None

    @classmethod
    async def get(cls):
        if not _HAS_REDIS:
            return None
        if cls._instance is None:
            from config.settings import settings
            try:
                cls._instance = aioredis.from_url(
                    settings.REDIS_URL, encoding="utf-8", decode_responses=True
                )
                await cls._instance.ping()
                logger.info("Redis connected")
            except Exception as e:
                logger.warning(f"Redis unavailable: {e}")
                cls._instance = None
        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None


async def ping_redis() -> bool:
    client = await RedisClient.get()
    return client is not None
