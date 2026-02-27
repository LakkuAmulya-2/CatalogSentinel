"""
Index definitions — Serverless-compatible mappings.
No ILM, no index.lifecycle.*, no number_of_shards in settings.
"""
from __future__ import annotations
from es.client import get_es
from utils.logger import get_logger

logger = get_logger(__name__)

INDICES: dict[str, dict] = {

    # ── Algorithm decisions (10M+/day) ───────────────────────
    "catalogsentinel-decisions": {
        "mappings": {
            "properties": {
                "decision_id":   {"type": "keyword"},
                "algorithm":     {"type": "keyword"},
                "version":       {"type": "keyword"},
                "company":       {"type": "keyword"},
                "platform":      {"type": "keyword"},
                "input_features":{"type": "object", "dynamic": True},
                "output":        {"type": "object", "dynamic": True},
                "location": {
                    "properties": {
                        "lat":  {"type": "float"},
                        "lon":  {"type": "float"},
                        "zone": {"type": "keyword"},
                        "city": {"type": "keyword"},
                    }
                },
                "timestamp": {"type": "date"},
                "ingested_at": {"type": "date"},
            }
        }
    },

    # ── Drift baselines (rolling 7-day distributions) ────────
    "catalogsentinel-drift-baselines": {
        "mappings": {
            "properties": {
                "algorithm":     {"type": "keyword"},
                "metric":        {"type": "keyword"},
                "window":        {"type": "keyword"},
                "computed_at":   {"type": "date"},
                "stats": {
                    "properties": {
                        "mean":   {"type": "float"},
                        "std":    {"type": "float"},
                        "p50":    {"type": "float"},
                        "p95":    {"type": "float"},
                        "p99":    {"type": "float"},
                        "min":    {"type": "float"},
                        "max":    {"type": "float"},
                        "count":  {"type": "long"},
                    }
                },
                "distribution":  {"type": "object", "dynamic": True},
            }
        }
    },

    # ── Detected drift incidents ──────────────────────────────
    "catalogsentinel-drift-incidents": {
        "mappings": {
            "properties": {
                "incident_id":       {"type": "keyword"},
                "algorithm":         {"type": "keyword"},
                "drift_score":       {"type": "float"},
                "kl_divergence":     {"type": "float"},
                "affected_metric":   {"type": "keyword"},
                "affected_zones":    {"type": "keyword"},
                "root_cause":        {"type": "text"},
                "root_cause_feature":{"type": "keyword"},
                "revenue_impact_inr":{"type": "float"},
                "status":            {"type": "keyword"},
                "detected_at":       {"type": "date"},
                "resolved_at":       {"type": "date"},
                "resolution": {
                    "properties": {
                        "action":     {"type": "keyword"},
                        "confidence": {"type": "float"},
                        "auto_fixed": {"type": "boolean"},
                        "details":    {"type": "text"},
                    }
                },
                "agent_analysis": {"type": "text"},
            }
        }
    },

    # ── Fix runbooks (historical incident → fix pairs) ────────
    "catalogsentinel-runbooks": {
        "mappings": {
            "properties": {
                "runbook_id":    {"type": "keyword"},
                "algorithm":     {"type": "keyword"},
                "symptom":       {"type": "text"},
                "symptom_vec":   {"type": "dense_vector", "dims": 1024, "index": True,
                                  "similarity": "cosine", "index_options": {"type": "hnsw"}},
                "root_cause":    {"type": "text"},
                "fix_action":    {"type": "keyword"},
                "fix_details":   {"type": "object", "dynamic": True},
                "success_rate":  {"type": "float"},
                "times_used":    {"type": "integer"},
                "created_at":    {"type": "date"},
                "updated_at":    {"type": "date"},
            }
        }
    },

    # ── Product catalog ────────────────────────────────────────
    "catalogsentinel-catalog": {
        "mappings": {
            "properties": {
                "product_id":    {"type": "keyword"},
                "sku":           {"type": "keyword"},
                "name":          {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "brand":         {"type": "keyword"},
                "category":      {"type": "keyword"},
                "subcategory":   {"type": "keyword"},
                "price":         {"type": "float"},
                "currency":      {"type": "keyword"},
                "description":   {"type": "text"},
                "attributes":    {"type": "object", "dynamic": True},
                "images":        {"type": "keyword"},
                "embedding":     {"type": "dense_vector", "dims": 1024, "index": True,
                                  "similarity": "cosine", "index_options": {"type": "hnsw"}},
                "findability_score": {"type": "float"},
                "schema_completeness": {"type": "float"},
                "ingested_at":   {"type": "date"},
                "updated_at":    {"type": "date"},
                "platform":      {"type": "keyword"},
            }
        }
    },

    # ── Schema attribute registry ─────────────────────────────
    "catalogsentinel-schema-registry": {
        "mappings": {
            "properties": {
                "category":      {"type": "keyword"},
                "attribute_name":{"type": "keyword"},
                "canonical_name":{"type": "keyword"},
                "aliases":       {"type": "keyword"},
                "data_type":     {"type": "keyword"},
                "support_pct":   {"type": "float"},
                "product_count": {"type": "integer"},
                "sample_values": {"type": "keyword"},
                "updated_at":    {"type": "date"},
            }
        }
    },

    # ── Schema mapping decisions (learned mappings) ───────────
    "catalogsentinel-schema-mappings": {
        "mappings": {
            "properties": {
                "mapping_id":    {"type": "keyword"},
                "product_id":    {"type": "keyword"},
                "original_attr": {"type": "keyword"},
                "mapped_attr":   {"type": "keyword"},
                "confidence":    {"type": "float"},
                "method":        {"type": "keyword"},
                "auto_applied":  {"type": "boolean"},
                "created_at":    {"type": "date"},
            }
        }
    },

    # ── Findability scores history ────────────────────────────
    "catalogsentinel-findability-scores": {
        "mappings": {
            "properties": {
                "product_id":    {"type": "keyword"},
                "score":         {"type": "float"},
                "issues":        {"type": "keyword"},
                "suggestions":   {"type": "text"},
                "before_score":  {"type": "float"},
                "after_score":   {"type": "float"},
                "computed_at":   {"type": "date"},
            }
        }
    },

    # ── Agent execution logs ──────────────────────────────────
    "catalogsentinel-agent-logs": {
        "mappings": {
            "properties": {
                "run_id":        {"type": "keyword"},
                "agent_name":    {"type": "keyword"},
                "trigger":       {"type": "keyword"},
                "status":        {"type": "keyword"},
                "input":         {"type": "text"},
                "output":        {"type": "text"},
                "duration_ms":   {"type": "float"},
                "timestamp":     {"type": "date"},
            }
        }
    },

    # ── Workflow executions ───────────────────────────────────
    "catalogsentinel-workflows": {
        "mappings": {
            "properties": {
                "workflow_id":   {"type": "keyword"},
                "trigger":       {"type": "keyword"},
                "entity_id":     {"type": "keyword"},
                "entity_type":   {"type": "keyword"},
                "actions":       {"type": "keyword"},
                "status":        {"type": "keyword"},
                "jira_ticket":   {"type": "keyword"},
                "slack_sent":    {"type": "boolean"},
                "created_at":    {"type": "date"},
                "completed_at":  {"type": "date"},
                "details":       {"type": "object", "dynamic": True},
            }
        }
    },
}


def create_all_indices() -> dict[str, bool]:
    es = get_es()
    results: dict[str, bool] = {}
    for name, body in INDICES.items():
        try:
            if not es.indices.exists(index=name):
                es.indices.create(index=name, **body)
                logger.info(f"Created index: {name}")
            else:
                logger.info(f"Index exists: {name}")
            results[name] = True
        except Exception as e:
            logger.error(f"Failed to create {name}: {e}")
            results[name] = False
    return results
