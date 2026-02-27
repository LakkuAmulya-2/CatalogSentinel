"""Health check endpoints."""
from fastapi import APIRouter
from datetime import datetime
from es.client import get_async_es
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    es = get_async_es()
    es_ok = False
    try:
        await es.ping()
        es_ok = True
    except Exception:
        pass
    return {
        "status": "healthy" if es_ok else "degraded",
        "elasticsearch": es_ok,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/detailed")
async def detailed_health():
    es = get_async_es()
    try:
        info = await es.info()
        es_version = info["version"]["number"]
        es_ok = True
    except Exception as e:
        es_version = str(e)
        es_ok = False

    from utils.redis_client import ping_redis
    redis_ok = await ping_redis()

    from kibana.agent_client import get_agent_client
    try:
        agents = await get_agent_client().check_all_agents()
        agents_ok = sum(1 for v in agents.values() if v)
    except Exception:
        agents = {}
        agents_ok = 0

    return {
        "status": "healthy" if es_ok else "degraded",
        "components": {
            "elasticsearch": {"ok": es_ok, "version": es_version},
            "redis": {"ok": redis_ok},
            "kibana_agents": {"ok": agents_ok > 0, "healthy": agents_ok, "total": len(agents)},
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
