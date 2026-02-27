"""Jina AI embeddings — 1024-dim, multilingual."""
from __future__ import annotations
from typing import List, Optional
import httpx
from utils.logger import get_logger

logger = get_logger(__name__)


class JinaEmbeddings:
    API_URL = "https://api.jina.ai/v1/embeddings"

    def __init__(self):
        from config.settings import settings
        self.api_key = settings.JINA_API_KEY
        self.model = settings.JINA_EMBEDDINGS_MODEL

    async def generate_embedding(
        self, text: str, task: str = "retrieval.passage"
    ) -> Optional[List[float]]:
        if not self.api_key or not text.strip():
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.API_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "task": task,
                        "input": [text],
                        "dimensions": 1024,
                    },
                )
                if resp.status_code == 200:
                    return resp.json()["data"][0]["embedding"]
                logger.warning(f"Jina API {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"Embedding error: {e}")
            return None

    async def batch_embed(
        self, texts: List[str], task: str = "retrieval.passage"
    ) -> List[Optional[List[float]]]:
        if not self.api_key:
            return [None] * len(texts)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    self.API_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "task": task,
                        "input": texts[:100],
                        "dimensions": 1024,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()["data"]
                    return [d["embedding"] for d in sorted(data, key=lambda x: x["index"])]
                return [None] * len(texts)
        except Exception as e:
            logger.warning(f"batch_embed error: {e}")
            return [None] * len(texts)
