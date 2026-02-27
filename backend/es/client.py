"""
Elasticsearch client — singleton, sync + async.
Supports Elastic Cloud Serverless (no ILM, no index settings).
"""
from __future__ import annotations
from typing import Optional
from elasticsearch import Elasticsearch, AsyncElasticsearch
from utils.logger import get_logger

logger = get_logger(__name__)


class ESClient:
    _sync: Optional[Elasticsearch] = None
    _async: Optional[AsyncElasticsearch] = None

    @classmethod
    def _kwargs(cls) -> dict:
        from config.settings import settings
        return dict(
            hosts=[settings.ES_URL],
            api_key=settings.ES_API_KEY,
            verify_certs=True,
            request_timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )

    @classmethod
    def sync(cls) -> Elasticsearch:
        if cls._sync is None:
            cls._sync = Elasticsearch(**cls._kwargs())
            logger.info("ES sync client ready")
        return cls._sync

    @classmethod
    def async_client(cls) -> AsyncElasticsearch:
        if cls._async is None:
            cls._async = AsyncElasticsearch(**cls._kwargs())
            logger.info("ES async client ready")
        return cls._async

    @classmethod
    async def close(cls):
        if cls._async:
            await cls._async.close()
        if cls._sync:
            cls._sync.close()


def get_es() -> Elasticsearch:
    return ESClient.sync()


def get_async_es() -> AsyncElasticsearch:
    return ESClient.async_client()
