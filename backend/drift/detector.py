"""
DriftSensor — Core detection engine.

ES|QL aggregates decision distributions every DRIFT_CHECK_INTERVAL_SECONDS.
Computes KL divergence vs 7-day baseline.
Triggers agent pipeline when drift_score > DRIFT_KL_THRESHOLD.
"""
from __future__ import annotations
import asyncio
import math
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from es.client import get_async_es
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

DECISIONS_IDX = "catalogsentinel-decisions"
BASELINES_IDX = "catalogsentinel-drift-baselines"
INCIDENTS_IDX = "catalogsentinel-drift-incidents"


def _kl_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """KL(P || Q) — smoothed to avoid log(0)."""
    eps = 1e-8
    keys = set(p) | set(q)
    kl = 0.0
    for k in keys:
        pi = p.get(k, eps)
        qi = q.get(k, eps)
        kl += pi * math.log(pi / qi)
    return kl


class DriftDetector:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ── Public API ───────────────────────────────────────────

    async def start(self):
        """Start background drift-check loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("DriftDetector loop started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def check_algorithm(self, algorithm: str) -> Optional[Dict[str, Any]]:
        """
        One-shot check for a single algorithm.
        Returns incident dict if drift detected, else None.
        """
        current = await self._get_current_distribution(algorithm)
        baseline = await self._get_baseline(algorithm)

        if not current:
            logger.warning(f"[{algorithm}] No current distribution data (need 5+ recent decisions)")
            return {"_debug": "no_current_data", "algorithm": algorithm}
        if not baseline:
            logger.warning(f"[{algorithm}] No baseline found")
            return {"_debug": "no_baseline", "algorithm": algorithm}

        kl = _kl_divergence(current["dist"], baseline.get("distribution", {}))
        logger.info(
            f"[{algorithm}] KL={kl:.4f} threshold={settings.DRIFT_KL_THRESHOLD} "
            f"current={current['dist']} baseline={baseline.get('distribution', {})}"
        )

        if kl > settings.DRIFT_KL_THRESHOLD:
            return await self._create_incident(algorithm, kl, current, baseline)

        # Return debug info even when no drift
        return {
            "_debug": "no_drift",
            "algorithm": algorithm,
            "kl_divergence": round(kl, 4),
            "threshold": settings.DRIFT_KL_THRESHOLD,
            "current_dist": current["dist"],
            "baseline_dist": baseline.get("distribution", {}),
            "current_count": current["count"],
        }

    async def get_recent_incidents(self, hours: int = 24) -> List[Dict]:
        es = get_async_es()
        try:
            resp = await es.search(
                index=INCIDENTS_IDX,
                query={"range": {"detected_at": {"gte": f"now-{hours}h"}}},
                sort=[{"detected_at": {"order": "desc"}}],
                size=50,
            )
            return [h["_source"] for h in resp["hits"]["hits"]]
        except Exception as e:
            logger.error(f"get_recent_incidents error: {e}")
            return []

    async def compute_and_store_baseline(self, algorithm: str) -> bool:
        """Recompute baseline from last DRIFT_BASELINE_DAYS days."""
        es = get_async_es()
        days = settings.DRIFT_BASELINE_DAYS
        try:
            resp = await es.search(
                index=DECISIONS_IDX,
                query={
                    "bool": {
                        "must": [
                            {"term": {"algorithm": algorithm}},
                            {"range": {"timestamp": {"gte": f"now-{days}d"}}},
                        ]
                    }
                },
                size=0,
                aggs={
                    "output_distribution": {
                        "terms": {"field": "output.category.keyword", "size": 20}
                    },
                    "avg_output": {"avg": {"field": "output.value"}},
                    "p95_output": {"percentiles": {"field": "output.value", "percents": [50, 95, 99]}},
                    "stddev_output": {"extended_stats": {"field": "output.value"}},
                },
            )

            aggs = resp.get("aggregations", {})
            buckets = aggs.get("output_distribution", {}).get("buckets", [])
            total = sum(b["doc_count"] for b in buckets) or 1
            dist = {b["key"]: b["doc_count"] / total for b in buckets}

            baseline_doc = {
                "algorithm": algorithm,
                "metric": "output.category",
                "window": f"{days}d",
                "computed_at": datetime.utcnow().isoformat(),
                "stats": {
                    "mean": (aggs.get("avg_output") or {}).get("value", 0),
                    "std": (aggs.get("stddev_output") or {}).get("std_deviation", 0),
                    "p50": (aggs.get("p95_output") or {}).get("values", {}).get("50.0", 0),
                    "p95": (aggs.get("p95_output") or {}).get("values", {}).get("95.0", 0),
                    "p99": (aggs.get("p95_output") or {}).get("values", {}).get("99.0", 0),
                    "count": resp["hits"]["total"]["value"],
                },
                "distribution": dist,
            }

            await es.index(
                index=BASELINES_IDX,
                id=f"{algorithm}_baseline",
                document=baseline_doc,
                refresh=True,
            )
            logger.info(f"Baseline updated for {algorithm}: {dist}")
            return True
        except Exception as e:
            logger.error(f"compute_baseline error for {algorithm}: {e}")
            return False

    # ── Internal helpers ─────────────────────────────────────

    async def _loop(self):
        while self._running:
            try:
                await self._check_all_algorithms()
            except Exception as e:
                logger.error(f"Drift loop error: {e}")
            await asyncio.sleep(settings.DRIFT_CHECK_INTERVAL_SECONDS)

    async def _check_all_algorithms(self):
        es = get_async_es()
        # Find all distinct algorithms active in last hour
        try:
            resp = await es.search(
                index=DECISIONS_IDX,
                query={"range": {"timestamp": {"gte": "now-1h"}}},
                size=0,
                aggs={"algorithms": {"terms": {"field": "algorithm", "size": 50}}},
            )
            algos = [b["key"] for b in resp["aggregations"]["algorithms"]["buckets"]]
            for algo in algos:
                incident = await self.check_algorithm(algo)
                if incident:
                    # Trigger agent pipeline async
                    asyncio.create_task(self._trigger_agent_pipeline(incident))
        except Exception as e:
            logger.error(f"_check_all_algorithms error: {e}")

    async def _get_current_distribution(self, algorithm: str) -> Optional[Dict]:
        es = get_async_es()
        # Use 30-minute window for manual checks, wider for background loop
        window_minutes = 30
        try:
            resp = await es.search(
                index=DECISIONS_IDX,
                query={
                    "bool": {
                        "must": [
                            {"term": {"algorithm": algorithm}},
                            {"range": {"timestamp": {"gte": f"now-{window_minutes}m"}}},
                        ]
                    }
                },
                size=0,
                aggs={
                    "dist": {"terms": {"field": "output.category.keyword", "size": 20}},
                    "avg_val": {"avg": {"field": "output.value"}},
                    "zone_dist": {"terms": {"field": "location.zone", "size": 20}},
                },
            )
            total = resp["hits"]["total"]["value"]
            if total < 5:
                logger.warning(f"[{algorithm}] Only {total} decisions in last {window_minutes}m — need at least 5")
                return None
            buckets = resp["aggregations"]["dist"]["buckets"]
            total_b = sum(b["doc_count"] for b in buckets) or 1
            dist = {b["key"]: b["doc_count"] / total_b for b in buckets}
            zone_buckets = resp["aggregations"]["zone_dist"]["buckets"]
            logger.info(f"[{algorithm}] Current dist ({total} decisions, {window_minutes}m): {dist}")
            return {
                "algorithm": algorithm,
                "count": total,
                "dist": dist,
                "avg_value": (resp["aggregations"]["avg_val"] or {}).get("value", 0),
                "zones": {b["key"]: b["doc_count"] for b in zone_buckets},
                "window_minutes": window_minutes,
            }
        except Exception as e:
            logger.error(f"_get_current_distribution error: {e}")
            return None

    async def _get_baseline(self, algorithm: str) -> Optional[Dict]:
        es = get_async_es()
        try:
            doc = await es.get(index=BASELINES_IDX, id=f"{algorithm}_baseline")
            return doc["_source"]
        except Exception:
            # No baseline yet — compute on-the-fly
            await self.compute_and_store_baseline(algorithm)
            try:
                doc = await es.get(index=BASELINES_IDX, id=f"{algorithm}_baseline")
                return doc["_source"]
            except Exception:
                return None

    async def _create_incident(
        self,
        algorithm: str,
        kl: float,
        current: Dict,
        baseline: Dict,
    ) -> Dict:
        es = get_async_es()
        incident_id = f"drift-{algorithm}-{str(uuid.uuid4())[:8]}"

        # Find which zones are most affected
        current_zones = current.get("zones", {})
        affected_zones = [z for z, c in current_zones.items() if c > 100][:5]

        # Estimate revenue impact (simple heuristic)
        drift_severity = min(kl / settings.DRIFT_KL_THRESHOLD, 5.0)
        revenue_impact = drift_severity * 230000  # ₹2.3L base per severity unit

        incident = {
            "incident_id": incident_id,
            "algorithm": algorithm,
            "drift_score": round(kl, 4),
            "kl_divergence": round(kl, 4),
            "affected_metric": "output.category",
            "affected_zones": affected_zones,
            "revenue_impact_inr": round(revenue_impact, 2),
            "status": "detected",
            "detected_at": datetime.utcnow().isoformat(),
            "resolution": {},
            "agent_analysis": "",
        }

        await es.index(
            index=INCIDENTS_IDX,
            id=incident_id,
            document=incident,
            refresh=True,
        )
        logger.warning(
            f"DRIFT DETECTED [{algorithm}] KL={kl:.4f} impact=₹{revenue_impact:,.0f}",
            extra={"incident_id": incident_id},
        )
        return incident

    async def _trigger_agent_pipeline(self, incident: Dict):
        """Hand off to Kibana agent pipeline for root-cause + fix."""
        try:
            from kibana.agent_client import get_agent_client
            client = get_agent_client()
            msg = (
                f"DRIFT DETECTED on algorithm '{incident['algorithm']}'. "
                f"KL divergence: {incident['drift_score']}. "
                f"Affected zones: {', '.join(incident['affected_zones'])}. "
                f"Incident ID: {incident['incident_id']}. "
                "Please diagnose root cause and propose auto-fix options."
            )
            result = await client.trigger_agent("drift-diagnostician", msg)
            # Store agent analysis back to incident
            if "response" in result:
                es = get_async_es()
                await es.update(
                    index=INCIDENTS_IDX,
                    id=incident["incident_id"],
                    doc={
                        "agent_analysis": result["response"],
                        "status": "investigating",
                    },
                )
        except Exception as e:
            logger.error(f"Agent pipeline trigger failed: {e}")