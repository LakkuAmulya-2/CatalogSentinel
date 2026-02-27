"""
Kibana agent management endpoints.
Fire-and-forget pattern for pipeline/trigger:
  POST /run-pipeline  → immediately returns job_id, runs in background
  GET  /jobs/{job_id} → poll for completion
"""
from __future__ import annotations
import asyncio
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import Any, Dict, Optional
from datetime import datetime

from kibana.agent_client import get_agent_client
from es.client import get_async_es
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])

# In-memory job store (process lifetime)
_jobs: Dict[str, Dict] = {}


def _new_job(kind: str) -> Dict:
    jid = str(uuid.uuid4())[:8]
    job = {"job_id": jid, "kind": kind, "status": "running",
           "started_at": datetime.utcnow().isoformat(),
           "results": {}, "error": None}
    _jobs[jid] = job
    return job


@router.get("/status")
async def agents_status() -> Dict[str, Any]:
    client = get_agent_client()
    availability = await client.check_all_agents()
    healthy = sum(1 for v in availability.values() if v)
    return {
        "overall": "healthy" if healthy == len(availability) else "degraded",
        "agents": availability,
        "healthy": healthy,
        "total": len(availability),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Background workers ────────────────────────────────────────

async def _run_trigger_bg(job: Dict, agent_id: str, message: str):
    client = get_agent_client()
    try:
        result = await client.trigger_agent(agent_id, message)
        job["results"][agent_id] = result
        job["status"] = "completed"
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
    job["finished_at"] = datetime.utcnow().isoformat()


async def _run_pipeline_bg(job: Dict, trigger: str, algorithm: Optional[str]):
    client = get_agent_client()
    try:
        tasks = []
        labels = []

        if trigger in ("manual", "drift", "all"):
            msg = (f"Check all algorithms for drift. Focus on '{algorithm}'."
                   if algorithm else "Check all active algorithms for drift in the last hour.")
            tasks.append(client.trigger_agent("drift-monitor", msg))
            labels.append("drift_monitor")

        if trigger in ("manual", "catalog", "all"):
            tasks.append(client.trigger_agent(
                "catalog-analyst",
                "Analyze newly ingested products in the last hour. Find schema gaps."
            ))
            labels.append("catalog_analyst")
            tasks.append(client.trigger_agent(
                "findability-scorer",
                "Score all products updated in the last hour and flag those below 50."
            ))
            labels.append("findability_scorer")

        tasks.append(client.trigger_agent(
            "sentinel-overseer",
            "Perform governance check: review agent performance and system health."
        ))
        labels.append("sentinel_overseer")

        # Run ALL agents in parallel — no sequential waiting
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for label, res in zip(labels, results):
            job["results"][label] = res if not isinstance(res, Exception) else {"error": str(res)}

        job["status"] = "completed"
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
    job["finished_at"] = datetime.utcnow().isoformat()
    logger.info(f"Pipeline job {job['job_id']} {job['status']}")


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/trigger/{agent_id}")
async def trigger_agent(
    agent_id: str,
    background_tasks: BackgroundTasks,
    message: str = "",
) -> Dict[str, Any]:
    """Fire-and-forget: starts agent, returns job_id immediately."""
    if not message:
        message = "Perform your standard analysis task for CatalogSentinel."
    job = _new_job(f"trigger:{agent_id}")
    background_tasks.add_task(_run_trigger_bg, job, agent_id, message)
    return {
        "job_id": job["job_id"],
        "status": "started",
        "agent_id": agent_id,
        "message": "Agent triggered in background. Poll /api/agents/jobs/{job_id} for result.",
    }


@router.post("/run-pipeline")
async def run_full_pipeline(
    background_tasks: BackgroundTasks,
    trigger: str = "manual",
    algorithm: Optional[str] = None,
) -> Dict[str, Any]:
    """Fire-and-forget: starts pipeline, returns job_id immediately."""
    job = _new_job(f"pipeline:{trigger}")
    background_tasks.add_task(_run_pipeline_bg, job, trigger, algorithm)
    return {
        "job_id": job["job_id"],
        "status": "started",
        "trigger": trigger,
        "message": "Pipeline started in background. Poll /api/agents/jobs/{job_id} for status.",
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> Dict[str, Any]:
    """Poll pipeline/trigger job status."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job


@router.get("/jobs")
async def list_jobs(limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    """List recent jobs."""
    recent = sorted(_jobs.values(), key=lambda j: j["started_at"], reverse=True)[:limit]
    return {"jobs": recent, "total": len(_jobs)}


@router.get("/logs")
async def get_agent_logs(
    hours: int = Query(24, ge=1, le=168),
    agent_name: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    es = get_async_es()
    must = [{"range": {"timestamp": {"gte": f"now-{hours}h"}}}]
    if agent_name:
        must.append({"term": {"agent_name": agent_name}})
    try:
        resp = await es.search(
            index="catalogsentinel-agent-logs",
            query={"bool": {"must": must}},
            sort=[{"timestamp": {"order": "desc"}}],
            size=limit,
        )
        return {
            "logs": [h["_source"] for h in resp["hits"]["hits"]],
            "total": resp["hits"]["total"]["value"],
        }
    except Exception as e:
        return {"logs": [], "total": 0, "error": str(e)}