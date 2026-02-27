"""
Kibana Agent Builder client.
Uses Converse API (POST /api/agent_builder/converse).

Perf fix: check_all_agents() runs ALL 7 health checks in parallel
          using a single shared httpx.AsyncClient + 30s result cache.
          Sequential (7 × 1.3s = 9s) → Parallel (~1.5s).
"""
from __future__ import annotations
import asyncio
import time
from datetime import datetime
import httpx
from typing import Any, Dict, Optional, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)

AGENT_IDS = [
    "drift-monitor", "drift-diagnostician", "drift-resolver",
    "catalog-analyst", "schema-mapper", "findability-scorer", "sentinel-overseer",
]


class KibanaAgentClient:
    def __init__(self):
        from config.settings import settings
        self.base = settings.KIBANA_URL.rstrip("/")
        self.api_key = settings.kibana_api_key_resolved
        self.headers = {
            "Authorization": f"ApiKey {self.api_key}",
            "Content-Type": "application/json",
            "kbn-xsrf": "true",
        }
        self.timeout = 300.0
        # Cache: (result_dict, timestamp) — valid for 30 seconds
        self._status_cache: Optional[Tuple[Dict[str, bool], float]] = None

    async def trigger_agent(self, agent_id: str, message: str) -> Dict[str, Any]:
        url = f"{self.base}/api/agent_builder/converse"
        t0 = time.monotonic()
        status = "success"
        response_text = ""
        error_detail = None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    url,
                    headers=self.headers,
                    json={"input": message, "agent_id": agent_id},
                )
                if resp.status_code == 200:
                    result = resp.json()
                    response_text = (
                        result.get("response", {}).get("message", "")
                        or result.get("message", "")
                        or str(result)[:500]
                    )
                    result_out = {
                        "status": "success",
                        "agent_id": agent_id,
                        "response": response_text,
                        "full_result": result,
                    }
                else:
                    status = "error"
                    error_detail = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.error(f"Agent {agent_id} {error_detail}")
                    result_out = {"error": error_detail}

        except httpx.TimeoutException:
            status = "error"
            error_detail = "timeout"
            result_out = {"error": "timeout", "agent_id": agent_id}
        except Exception as e:
            status = "error"
            error_detail = str(e)
            logger.error(f"trigger_agent {agent_id}: {e}")
            result_out = {"error": str(e), "agent_id": agent_id}

        duration_ms = (time.monotonic() - t0) * 1000

        # Write execution log to ES
        await self._write_agent_log(
            agent_id=agent_id,
            status=status,
            duration_ms=duration_ms,
            trigger=message[:100] if message else "manual",
            response_summary=response_text[:300] if response_text else error_detail or "",
        )

        return result_out

    async def _write_agent_log(
        self,
        agent_id: str,
        status: str,
        duration_ms: float,
        trigger: str = "manual",
        response_summary: str = "",
    ) -> None:
        """Store agent execution log in catalogsentinel-agent-logs index."""
        try:
            from es.client import get_async_es
            es = get_async_es()
            await es.index(
                index="catalogsentinel-agent-logs",
                document={
                    "agent_name": agent_id,
                    "status": status,
                    "duration_ms": round(duration_ms, 1),
                    "trigger": trigger or "manual",
                    "response_summary": response_summary,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(f"_write_agent_log failed: {e}")

    async def _check_one(
        self, client: httpx.AsyncClient, agent_id: str
    ) -> Tuple[str, bool]:
        """Single agent health check — reuses shared client."""
        url = f"{self.base}/api/agent_builder/a2a/{agent_id}.json"
        try:
            resp = await client.get(url, headers=self.headers)
            ok = resp.status_code == 200
            return agent_id, ok
        except Exception as e:
            logger.debug(f"check_one {agent_id}: {e}")
            return agent_id, False

    async def get_agent_card(self, agent_id: str) -> Dict[str, Any]:
        url = f"{self.base}/api/agent_builder/a2a/{agent_id}.json"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=self.headers)
                return resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    async def check_all_agents(self, use_cache: bool = True) -> Dict[str, bool]:
        """
        Check all 7 agents IN PARALLEL using one shared httpx client.
        Results cached for 30s to prevent hammering Kibana on every UI poll.
        Before fix: ~9s (sequential).  After fix: ~1.5s (parallel).
        """
        # Return cached result if still fresh
        if use_cache and self._status_cache is not None:
            cached_result, cached_at = self._status_cache
            if time.monotonic() - cached_at < 30.0:
                return cached_result

        t0 = time.monotonic()
        # One shared client for all 7 parallel requests
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            tasks = [self._check_one(client, aid) for aid in AGENT_IDS]
            pairs = await asyncio.gather(*tasks, return_exceptions=False)

        result = {aid: ok for aid, ok in pairs}
        elapsed = time.monotonic() - t0
        healthy = sum(1 for v in result.values() if v)
        logger.info(f"check_all_agents: {healthy}/{len(AGENT_IDS)} healthy in {elapsed:.2f}s")

        # Cache result
        self._status_cache = (result, time.monotonic())
        return result

    def invalidate_cache(self):
        """Call after creating/deleting agents."""
        self._status_cache = None


_client: Optional[KibanaAgentClient] = None


def get_agent_client() -> KibanaAgentClient:
    global _client
    if _client is None:
        _client = KibanaAgentClient()
    return _client