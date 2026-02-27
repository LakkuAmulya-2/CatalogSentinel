"""
DriftSensor API endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel

from drift.detector import DriftDetector
from es.client import get_async_es
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/drift", tags=["drift"])

_detector: Optional[DriftDetector] = None


def get_detector() -> DriftDetector:
    global _detector
    if _detector is None:
        _detector = DriftDetector()
    return _detector


class DecisionIngestRequest(BaseModel):
    decision_id: str
    algorithm: str
    version: str = "1.0"
    company: str = ""
    platform: str = ""
    input_features: Dict[str, Any] = {}
    output: Dict[str, Any] = {}
    location: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


class BulkDecisionRequest(BaseModel):
    decisions: List[DecisionIngestRequest]


@router.post("/decisions")
async def ingest_decision(req: DecisionIngestRequest, bg: BackgroundTasks):
    """Ingest a single algorithm decision."""
    es = get_async_es()
    doc = req.model_dump()
    doc["timestamp"] = req.timestamp or datetime.utcnow().isoformat()
    doc["ingested_at"] = datetime.utcnow().isoformat()
    try:
        await es.index(index="catalogsentinel-decisions", document=doc)
        return {"status": "indexed", "decision_id": req.decision_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decisions/bulk")
async def ingest_decisions_bulk(req: BulkDecisionRequest):
    """Bulk ingest algorithm decisions."""
    from elasticsearch.helpers import async_bulk
    es = get_async_es()
    actions = []
    for d in req.decisions:
        doc = d.model_dump()
        doc["timestamp"] = d.timestamp or datetime.utcnow().isoformat()
        doc["ingested_at"] = datetime.utcnow().isoformat()
        actions.append({"_index": "catalogsentinel-decisions", "_source": doc})
    try:
        ok, failed = await async_bulk(es, actions)
        return {"indexed": ok, "failed": failed if isinstance(failed, int) else len(failed)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check/{algorithm}")
async def check_algorithm(algorithm: str) -> Dict[str, Any]:
    """Manually trigger drift check for an algorithm."""
    try:
        detector = get_detector()
        result = await detector.check_algorithm(algorithm)

        # No data or no drift
        if result is None or "_debug" in (result or {}):
            return {
                "drift_detected": False,
                "algorithm": algorithm,
                "debug": result or {},
            }

        # Drift detected — trigger workflow
        from workflows.workflow_engine import WorkflowEngine
        wf = WorkflowEngine()
        wf_result = await wf.trigger_drift_workflow(result)
        return {
            "drift_detected": True,
            "incident": result,
            "workflow": wf_result,
        }
    except Exception as e:
        logger.error(f"check_algorithm error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Drift check failed: {str(e)}")


@router.get("/incidents")
async def get_incidents(
    hours: int = Query(24, ge=1, le=168),
    algorithm: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Recent drift incidents."""
    es = get_async_es()
    must = [{"range": {"detected_at": {"gte": f"now-{hours}h"}}}]
    if algorithm:
        must.append({"term": {"algorithm": algorithm}})
    if status:
        must.append({"term": {"status": status}})
    try:
        resp = await es.search(
            index="catalogsentinel-drift-incidents",
            query={"bool": {"must": must}},
            sort=[{"detected_at": {"order": "desc"}}],
            size=limit,
        )
        incidents = [h["_source"] for h in resp["hits"]["hits"]]
        return {
            "total": resp["hits"]["total"]["value"],
            "incidents": incidents,
            "hours": hours,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str) -> Dict[str, Any]:
    es = get_async_es()
    try:
        doc = await es.get(index="catalogsentinel-drift-incidents", id=incident_id)
        return doc["_source"]
    except Exception:
        raise HTTPException(status_code=404, detail="Incident not found")


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    action: str = Query(..., description="rollback|override|pause|restart"),
    confidence: float = Query(0.9),
) -> Dict[str, Any]:
    """Apply a fix to a drift incident."""
    es = get_async_es()
    try:
        resolution = {
            "action": action,
            "confidence": confidence,
            "auto_fixed": confidence >= 0.85,
            "details": f"Applied {action} at confidence {confidence:.0%}",
            "resolved_at": datetime.utcnow().isoformat(),
        }
        await es.update(
            index="catalogsentinel-drift-incidents",
            id=incident_id,
            doc={
                "status": "resolved",
                "resolved_at": datetime.utcnow().isoformat(),
                "resolution": resolution,
            },
        )
        # Trigger Kibana drift-resolver agent
        from kibana.agent_client import get_agent_client
        msg = f"Apply fix '{action}' for incident {incident_id} with confidence {confidence}"
        await get_agent_client().trigger_agent("drift-resolver", msg)
        return {"resolved": True, "incident_id": incident_id, "resolution": resolution}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/baseline/{algorithm}")
async def recompute_baseline(algorithm: str) -> Dict[str, Any]:
    detector = get_detector()
    ok = await detector.compute_and_store_baseline(algorithm)
    return {"success": ok, "algorithm": algorithm}


@router.get("/metrics")
async def drift_metrics(hours: int = Query(24, ge=1, le=168)) -> Dict[str, Any]:
    """Aggregated drift metrics for dashboard."""
    es = get_async_es()
    try:
        resp = await es.search(
            index="catalogsentinel-drift-incidents",
            query={"range": {"detected_at": {"gte": f"now-{hours}h"}}},
            size=0,
            aggs={
                "total": {"value_count": {"field": "incident_id"}},
                "by_status": {"terms": {"field": "status", "size": 10}},
                "by_algorithm": {"terms": {"field": "algorithm", "size": 20}},
                "avg_kl": {"avg": {"field": "kl_divergence"}},
                "total_revenue_impact": {"sum": {"field": "revenue_impact_inr"}},
                "auto_fixed": {
                    "filter": {"term": {"resolution.auto_fixed": True}},
                    "aggs": {"count": {"value_count": {"field": "incident_id"}}},
                },
            },
        )
        aggs = resp["aggregations"]
        total = aggs["total"]["value"]
        auto_fixed = aggs["auto_fixed"]["count"]["value"]
        return {
            "period_hours": hours,
            "total_incidents": total,
            "auto_fixed": auto_fixed,
            "auto_fix_rate": round(auto_fixed / total * 100, 1) if total else 0,
            "avg_kl_divergence": round((aggs["avg_kl"]["value"] or 0), 4),
            "total_revenue_at_risk_inr": round(aggs["total_revenue_impact"]["value"] or 0, 2),
            "by_status": {b["key"]: b["doc_count"] for b in aggs["by_status"]["buckets"]},
            "by_algorithm": {b["key"]: b["doc_count"] for b in aggs["by_algorithm"]["buckets"]},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/stream")
async def get_recent_decisions(
    algorithm: Optional[str] = None,
    minutes: int = Query(5, ge=1, le=60),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    """Recent decisions for live dashboard."""
    es = get_async_es()
    must = [{"range": {"timestamp": {"gte": f"now-{minutes}m"}}}]
    if algorithm:
        must.append({"term": {"algorithm": algorithm}})
    try:
        resp = await es.search(
            index="catalogsentinel-decisions",
            query={"bool": {"must": must}},
            sort=[{"timestamp": {"order": "desc"}}],
            size=limit,
        )
        return {
            "total": resp["hits"]["total"]["value"],
            "decisions": [h["_source"] for h in resp["hits"]["hits"]],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))