"""
CatalogIQ API endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from catalog.intelligence import CatalogIntelligence
from es.client import get_async_es
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/catalog", tags=["catalog"])

_ci: Optional[CatalogIntelligence] = None


def get_ci() -> CatalogIntelligence:
    global _ci
    if _ci is None:
        _ci = CatalogIntelligence()
    return _ci


class ProductIngestRequest(BaseModel):
    product_id: Optional[str] = None
    sku: str = ""
    name: str
    brand: str = ""
    category: str = ""
    subcategory: str = ""
    price: float = 0.0
    currency: str = "INR"
    description: str = ""
    attributes: Dict[str, Any] = {}
    images: List[str] = []
    platform: str = ""


@router.post("/products")
async def ingest_product(req: ProductIngestRequest) -> Dict[str, Any]:
    """Ingest a product and auto-compute findability + schema mappings."""
    ci = get_ci()
    result = await ci.process_new_product(req.model_dump())

    # Trigger workflow if score is low
    if result["findability_score"] < 50:
        from workflows.workflow_engine import WorkflowEngine
        wf = WorkflowEngine()
        await wf.trigger_catalog_workflow(result)

    return result


@router.post("/products/bulk")
async def ingest_products_bulk(products: List[ProductIngestRequest]) -> Dict[str, Any]:
    """Bulk product ingestion."""
    ci = get_ci()
    results = []
    for p in products[:100]:
        try:
            r = await ci.process_new_product(p.model_dump())
            results.append(r)
        except Exception as e:
            results.append({"product_id": p.product_id, "error": str(e)})
    return {
        "processed": len(results),
        "avg_findability": (
            sum(r.get("findability_score", 0) for r in results if "findability_score" in r)
            / max(sum(1 for r in results if "findability_score" in r), 1)
        ),
        "results": results,
    }


@router.get("/products/{product_id}/findability")
async def get_findability(product_id: str) -> Dict[str, Any]:
    ci = get_ci()
    report = await ci.get_findability_report(product_id)
    if not report:
        raise HTTPException(status_code=404, detail="Product not found")
    return report


@router.get("/products")
async def search_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_score: float = Query(0.0, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Search products with optional filters."""
    es = get_async_es()
    must = []
    if q:
        must.append({"multi_match": {"query": q, "fields": ["name^3", "description", "brand"]}})
    if category:
        must.append({"term": {"category": category}})
    if min_score > 0:
        must.append({"range": {"findability_score": {"gte": min_score}}})

    query = {"bool": {"must": must}} if must else {"match_all": {}}
    try:
        resp = await es.search(
            index="catalogsentinel-catalog",
            query=query,
            sort=[{"findability_score": {"order": "desc"}}],
            size=limit,
            _source={"excludes": ["embedding"]},
        )
        return {
            "total": resp["hits"]["total"]["value"],
            "products": [h["_source"] for h in resp["hits"]["hits"]],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schema-registry/{category}/rebuild")
async def rebuild_registry(category: str) -> Dict[str, Any]:
    ci = get_ci()
    ok = await ci.update_schema_registry(category)
    return {"success": ok, "category": category}


@router.get("/schema-registry/{category}")
async def get_registry(category: str) -> Dict[str, Any]:
    es = get_async_es()
    try:
        resp = await es.search(
            index="catalogsentinel-schema-registry",
            query={"term": {"category": category}},
            sort=[{"support_pct": {"order": "desc"}}],
            size=200,
        )
        return {
            "category": category,
            "attributes": [h["_source"] for h in resp["hits"]["hits"]],
            "total": resp["hits"]["total"]["value"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def catalog_metrics() -> Dict[str, Any]:
    """Dashboard metrics for catalog intelligence."""
    es = get_async_es()
    try:
        resp = await es.search(
            index="catalogsentinel-catalog",
            query={"match_all": {}},
            size=0,
            aggs={
                "total": {"value_count": {"field": "product_id"}},
                "avg_findability": {"avg": {"field": "findability_score"}},
                "low_score": {"filter": {"range": {"findability_score": {"lt": 50}}},
                              "aggs": {"count": {"value_count": {"field": "product_id"}}}},
                "by_category": {"terms": {"field": "category", "size": 20},
                                "aggs": {"avg_score": {"avg": {"field": "findability_score"}}}},
                "score_dist": {"histogram": {"field": "findability_score", "interval": 10}},
            },
        )
        aggs = resp["aggregations"]
        total = aggs["total"]["value"]
        low = aggs["low_score"]["count"]["value"]

        # Total mappings applied
        m_resp = await es.search(
            index="catalogsentinel-schema-mappings",
            query={"match_all": {}},
            size=0,
            aggs={"total": {"value_count": {"field": "mapping_id"}}},
        )
        total_mappings = m_resp["aggregations"]["total"]["value"]

        return {
            "total_products": total,
            "avg_findability_score": round(aggs["avg_findability"]["value"] or 0, 1),
            "low_score_products": low,
            "low_score_pct": round(low / total * 100, 1) if total else 0,
            "total_schema_mappings": total_mappings,
            "by_category": [
                {"category": b["key"], "count": b["doc_count"],
                 "avg_score": round(b["avg_score"]["value"] or 0, 1)}
                for b in aggs["by_category"]["buckets"]
            ],
            "score_distribution": [
                {"range": f"{int(b['key'])}-{int(b['key'])+10}", "count": b["doc_count"]}
                for b in aggs["score_dist"]["buckets"]
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
