"""Workflow management endpoints."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

from workflows.workflow_engine import WorkflowEngine
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["workflows"])

_engine: Optional[WorkflowEngine] = None


def get_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine


@router.get("/history")
async def workflow_history(
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    trigger: Optional[str] = None,
) -> Dict[str, Any]:
    engine = get_engine()
    workflows = await engine.get_workflow_history(limit=limit, status=status, trigger=trigger)
    return {"total": len(workflows), "workflows": workflows}


@router.get("/stats")
async def workflow_stats() -> Dict[str, Any]:
    from es.client import get_async_es
    es = get_async_es()
    try:
        resp = await es.search(
            index="catalogsentinel-workflows",
            query={"match_all": {}},
            size=0,
            aggs={
                "total": {"value_count": {"field": "workflow_id"}},
                "by_status": {"terms": {"field": "status", "size": 10}},
                "by_trigger": {"terms": {"field": "trigger", "size": 10}},
                "slack_sent": {"filter": {"term": {"slack_sent": True}},
                               "aggs": {"count": {"value_count": {"field": "workflow_id"}}}},
            },
        )
        aggs = resp["aggregations"]
        total = aggs["total"]["value"]
        completed = next(
            (b["doc_count"] for b in aggs["by_status"]["buckets"] if b["key"] == "completed"), 0
        )
        return {
            "total_workflows": total,
            "completed": completed,
            "success_rate": round(completed / total * 100, 1) if total else 0,
            "slack_alerts_sent": aggs["slack_sent"]["count"]["value"],
            "by_trigger": {b["key"]: b["doc_count"] for b in aggs["by_trigger"]["buckets"]},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
