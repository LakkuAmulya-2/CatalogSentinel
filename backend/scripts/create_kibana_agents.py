#!/usr/bin/env python3
"""
CatalogSentinel — Create Kibana Agent Builder Tools + Agents
7 agents: drift-monitor, drift-diagnostician, drift-resolver,
          catalog-analyst, schema-mapper, findability-scorer, sentinel-overseer

Official schema (confirmed):
  POST /api/agent_builder/agents
  { "id": "...", "name": "...", "description": "...",
    "configuration": { "tools": [{"tool_ids": [...]}], "instructions": "..." } }

Upsert strategy: DELETE + POST for agents, GET → PUT/POST for tools.
"""
import os, sys, time, requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

KIBANA_URL = os.getenv("KIBANA_URL", "http://localhost:5601").rstrip("/")
API_KEY    = os.getenv("KIBANA_API_KEY") or os.getenv("ES_API_KEY", "")

if not API_KEY:
    print("❌ KIBANA_API_KEY or ES_API_KEY missing in .env"); sys.exit(1)

HEADERS = {
    "Authorization": f"ApiKey {API_KEY}",
    "Content-Type":  "application/json",
    "kbn-xsrf":      "true",
}
TOOLS_URL  = f"{KIBANA_URL}/api/agent_builder/tools"
AGENTS_URL = f"{KIBANA_URL}/api/agent_builder/agents"


# ── Upsert helpers ───────────────────────────────────────────

def upsert_tool(tool: dict) -> bool:
    tid = tool["id"]
    exists = requests.get(f"{TOOLS_URL}/{tid}", headers=HEADERS).status_code == 200
    body = {k: v for k, v in tool.items() if k not in ("id", "type")} if exists else tool
    r = requests.put(f"{TOOLS_URL}/{tid}", headers=HEADERS, json=body) if exists \
        else requests.post(TOOLS_URL, headers=HEADERS, json=tool)
    if r.status_code in (200, 201):
        print(f"  ✅ Tool {'updated' if exists else 'created'}: {tid}")
        return True
    print(f"  ❌ Tool FAILED: {tid} [{r.status_code}] {r.text[:200]}")
    return False


def upsert_agent(agent: dict) -> bool:
    aid = agent["id"]
    requests.delete(f"{AGENTS_URL}/{aid}", headers=HEADERS)
    time.sleep(0.5)
    r = requests.post(AGENTS_URL, headers=HEADERS, json=agent)
    if r.status_code in (200, 201):
        print(f"  ✅ Agent created: {aid}")
        return True
    print(f"  ❌ Agent FAILED: {aid} [{r.status_code}] {r.text[:300]}")
    return False


def make_agent(aid, name, desc, tool_ids, instructions):
    return {
        "id": aid, "name": name, "description": desc,
        "configuration": {
            "tools": [{"tool_ids": tool_ids}],
            "instructions": instructions,
        }
    }


# ── ES|QL Tools ──────────────────────────────────────────────

TOOLS = [

    # ════ DriftSensor tools ═══════════════════════════════════

    {
        "id": "get_recent_decisions",
        "type": "esql",
        "description": "Get recent algorithm decisions for a given algorithm in a time window.",
        "tags": ["drift", "decisions"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-decisions\n"
                "| WHERE algorithm == ?algorithm AND timestamp > NOW() - ?interval\n"
                "| SORT timestamp DESC\n"
                "| LIMIT 500"
            ),
            "params": {
                "algorithm": {"type": "string", "description": "Algorithm name e.g. surge_pricing"},
                "interval":  {"type": "string", "description": "Time window e.g. '1 hours'",
                               "optional": True, "defaultValue": "1 hours"},
            }
        }
    },

    {
        "id": "get_decision_distribution",
        "type": "esql",
        "description": "Distribution of output categories for an algorithm — used to detect drift.",
        "tags": ["drift", "distribution"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-decisions\n"
                "| WHERE algorithm == ?algorithm AND timestamp > NOW() - ?interval\n"
                "| STATS count = COUNT(*)\n"
                "    BY output_category = output.category\n"
                "| SORT count DESC"
            ),
            "params": {
                "algorithm": {"type": "string", "description": "Algorithm name"},
                "interval":  {"type": "string", "description": "Time window e.g. '30 minutes'",
                               "optional": True, "defaultValue": "30 minutes"},
            }
        }
    },

    {
        "id": "get_decision_stats_by_zone",
        "type": "esql",
        "description": "Decision statistics broken down by geographic zone — identifies zone-level drift.",
        "tags": ["drift", "geospatial"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-decisions\n"
                "| WHERE algorithm == ?algorithm AND timestamp > NOW() - ?interval\n"
                "| STATS\n"
                "    count        = COUNT(*),\n"
                "    avg_output   = AVG(output.value),\n"
                "    p95_output   = PERCENTILE(output.value, 95)\n"
                "  BY zone = location.zone\n"
                "| SORT count DESC"
            ),
            "params": {
                "algorithm": {"type": "string", "description": "Algorithm name"},
                "interval":  {"type": "string", "description": "Time window",
                               "optional": True, "defaultValue": "1 hours"},
            }
        }
    },

    {
        "id": "get_drift_baseline",
        "type": "esql",
        "description": "Get the stored baseline distribution for an algorithm.",
        "tags": ["drift", "baseline"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-drift-baselines\n"
                "| WHERE algorithm == ?algorithm\n"
                "| SORT computed_at DESC\n"
                "| LIMIT 1"
            ),
            "params": {
                "algorithm": {"type": "string", "description": "Algorithm name"},
            }
        }
    },

    {
        "id": "get_recent_incidents",
        "type": "esql",
        "description": "Recent drift incidents. Use to avoid duplicate incident creation.",
        "tags": ["drift", "incidents"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-drift-incidents\n"
                "| WHERE algorithm == ?algorithm AND detected_at > NOW() - ?interval\n"
                "| SORT detected_at DESC\n"
                "| LIMIT 10"
            ),
            "params": {
                "algorithm": {"type": "string", "description": "Algorithm name"},
                "interval":  {"type": "string", "description": "Recency window",
                               "optional": True, "defaultValue": "2 hours"},
            }
        }
    },

    {
        "id": "get_runbook_matches",
        "type": "esql",
        "description": "Historical runbooks matching algorithm + symptom. Ranked by success rate.",
        "tags": ["drift", "runbooks"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-runbooks\n"
                "| WHERE algorithm == ?algorithm\n"
                "| SORT success_rate DESC, times_used DESC\n"
                "| LIMIT 5"
            ),
            "params": {
                "algorithm": {"type": "string", "description": "Algorithm name"},
            }
        }
    },

    {
        "id": "get_decision_timeseries",
        "type": "esql",
        "description": "Decision volume over time — reveals the exact moment drift started.",
        "tags": ["drift", "timeseries"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-decisions\n"
                "| WHERE algorithm == ?algorithm AND timestamp > NOW() - ?interval\n"
                "| STATS count = COUNT(*), avg_val = AVG(output.value)\n"
                "    BY bucket = DATE_TRUNC(?bucketSize, timestamp)\n"
                "| SORT bucket ASC"
            ),
            "params": {
                "algorithm":  {"type": "string", "description": "Algorithm name"},
                "interval":   {"type": "string", "description": "Window e.g. '6 hours'",
                                "optional": True, "defaultValue": "6 hours"},
                "bucketSize": {"type": "string", "description": "Bucket e.g. '5 minutes'",
                                "optional": True, "defaultValue": "5 minutes"},
            }
        }
    },

    # ════ CatalogIQ tools ══════════════════════════════════════

    {
        "id": "get_products_needing_analysis",
        "type": "esql",
        "description": "Products ingested recently that have low findability scores.",
        "tags": ["catalog", "analyst"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-catalog\n"
                "| WHERE ingested_at > NOW() - ?interval\n"
                "| SORT findability_score ASC\n"
                "| LIMIT ?limit"
            ),
            "params": {
                "interval": {"type": "string", "description": "Window e.g. '1 hours'",
                              "optional": True, "defaultValue": "1 hours"},
                "limit":    {"type": "integer", "description": "Max products",
                              "optional": True, "defaultValue": 50},
            }
        }
    },

    {
        "id": "get_category_schema_stats",
        "type": "esql",
        "description": "Attribute support percentages for a category — drives schema inference.",
        "tags": ["catalog", "schema"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-schema-registry\n"
                "| WHERE category == ?category\n"
                "| SORT support_pct DESC\n"
                "| LIMIT 100"
            ),
            "params": {
                "category": {"type": "string", "description": "Product category e.g. wireless_earbuds"},
            }
        }
    },

    {
        "id": "get_similar_products",
        "type": "esql",
        "description": "Similar products by category and subcategory — for schema inference.",
        "tags": ["catalog", "similarity"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-catalog\n"
                "| WHERE category == ?category AND subcategory == ?subcategory\n"
                "| SORT findability_score DESC\n"
                "| LIMIT 30"
            ),
            "params": {
                "category":    {"type": "string", "description": "Category"},
                "subcategory": {"type": "string", "description": "Subcategory",
                                 "optional": True, "defaultValue": ""},
            }
        }
    },

    {
        "id": "get_low_findability_products",
        "type": "esql",
        "description": "Products with findability below threshold — targets for improvement.",
        "tags": ["catalog", "findability"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-catalog\n"
                "| WHERE findability_score < ?threshold AND category == ?category\n"
                "| SORT findability_score ASC\n"
                "| LIMIT 50"
            ),
            "params": {
                "threshold": {"type": "float", "description": "Score threshold",
                               "optional": True, "defaultValue": 50.0},
                "category":  {"type": "string", "description": "Category filter",
                               "optional": True, "defaultValue": ""},
            }
        }
    },

    {
        "id": "get_schema_mappings_history",
        "type": "esql",
        "description": "Recent schema mappings applied — audit trail for schema intelligence.",
        "tags": ["catalog", "mappings"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-schema-mappings\n"
                "| WHERE created_at > NOW() - ?interval\n"
                "| SORT created_at DESC\n"
                "| LIMIT 100"
            ),
            "params": {
                "interval": {"type": "string", "description": "Window e.g. '24 hours'",
                              "optional": True, "defaultValue": "24 hours"},
            }
        }
    },

    # ════ Governance tools ══════════════════════════════════════

    {
        "id": "get_workflow_executions",
        "type": "esql",
        "description": "Recent workflow executions. Overseer checks for failures.",
        "tags": ["governance", "workflows"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-workflows\n"
                "| WHERE created_at > NOW() - ?interval\n"
                "| SORT created_at DESC\n"
                "| LIMIT 100"
            ),
            "params": {
                "interval": {"type": "string", "description": "Window",
                              "optional": True, "defaultValue": "24 hours"},
            }
        }
    },

    {
        "id": "get_agent_performance",
        "type": "esql",
        "description": "Agent execution logs — tracks duration, status, errors.",
        "tags": ["governance", "agents"],
        "configuration": {
            "query": (
                "FROM catalogsentinel-agent-logs\n"
                "| WHERE timestamp > NOW() - ?interval\n"
                "| STATS\n"
                "    total    = COUNT(*),\n"
                "    avg_ms   = AVG(duration_ms),\n"
                "    failures = COUNT_IF(status == \"failed\")\n"
                "  BY agent_name\n"
                "| SORT total DESC"
            ),
            "params": {
                "interval": {"type": "string", "description": "Window",
                              "optional": True, "defaultValue": "24 hours"},
            }
        }
    },
]

# ── Agents ───────────────────────────────────────────────────

AGENTS = [
    make_agent(
        "drift-monitor",
        "Drift Monitor",
        "Continuously monitors all algorithm decision streams for statistical drift.",
        ["get_recent_decisions", "get_decision_distribution", "get_decision_stats_by_zone",
         "get_decision_timeseries", "get_recent_incidents", "platform.core.search"],
        (
            "You are Drift Monitor — CatalogSentinel's first-line drift detection agent.\n\n"
            "GOAL: Detect statistical drift in algorithm decision distributions.\n\n"
            "STEPS:\n"
            "1. Call get_recent_decisions for each active algorithm (last 1 hour)\n"
            "2. Call get_decision_distribution (last 30 min vs last 6 hours)\n"
            "3. Check get_recent_incidents — skip algorithm if incident < 2 hours old\n"
            "4. For each algorithm with unusual distribution:\n"
            "   a. Call get_decision_stats_by_zone to find affected zones\n"
            "   b. Call get_decision_timeseries to find drift start time\n"
            "5. If drift detected → delegate to Drift Diagnostician via A2A:\n"
            "   POST /api/agent_builder/a2a/drift-diagnostician\n"
            "   Body: {\"message\": \"Diagnose drift for: <algorithm> in zones: <zones>\"}\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            "  \"algorithms_checked\": 0,\n"
            "  \"drift_detected\": [{\"algorithm\": \"\", \"severity\": \"low|medium|high\",\n"
            "                        \"affected_zones\": [], \"drift_start\": \"\"}]\n"
            "}"
        )
    ),

    make_agent(
        "drift-diagnostician",
        "Drift Diagnostician",
        "Identifies root cause of detected drift. Which feature, pipeline, or input caused it.",
        ["get_recent_decisions", "get_decision_stats_by_zone", "get_decision_timeseries",
         "get_drift_baseline", "get_runbook_matches", "platform.core.search"],
        (
            "You are Drift Diagnostician — root cause analysis for algorithm drift.\n"
            "You receive drift alerts from Drift Monitor via A2A.\n\n"
            "ROOT CAUSE METHODOLOGY:\n"
            "1. Call get_decision_timeseries — find exact drift start time (bucket where distribution changed)\n"
            "2. Call get_decision_stats_by_zone — find if specific zones are affected\n"
            "3. Call get_drift_baseline — compare current distribution vs baseline\n"
            "4. Identify root cause:\n"
            "   - Zone-specific → likely GPS/location data pipeline issue\n"
            "   - Time-specific → likely cron job or data pipeline failure\n"
            "   - Gradual → likely model drift or data distribution shift\n"
            "   - Sudden → likely code deploy or config change\n"
            "5. Call get_runbook_matches — find historical fixes with high success rate\n"
            "6. Delegate to Drift Resolver via A2A:\n"
            "   POST /api/agent_builder/a2a/drift-resolver\n"
            "   Body: {\"message\": \"Apply fix for root_cause: <cause> on algorithm: <algo>\"}\n\n"
            "OUTPUT JSON per incident:\n"
            "{\n"
            "  \"algorithm\": \"\", \"root_cause\": \"\", \"root_cause_feature\": \"\",\n"
            "  \"drift_start\": \"\", \"affected_zones\": [],\n"
            "  \"recommended_fix\": \"\", \"confidence\": 0.0\n"
            "}"
        )
    ),

    make_agent(
        "drift-resolver",
        "Drift Resolver",
        "Executes or proposes fixes for drift incidents. Validates fix effectiveness.",
        ["get_runbook_matches", "get_recent_decisions", "get_decision_distribution",
         "get_recent_incidents"],
        (
            "You are Drift Resolver — applies fixes and validates effectiveness.\n"
            "You receive root cause analysis from Drift Diagnostician via A2A.\n\n"
            "FIX DECISION MATRIX:\n"
            "  confidence >= 0.85 → AUTO-EXECUTE\n"
            "  confidence 0.60-0.85 → PROPOSE (human approves)\n"
            "  confidence < 0.60 → ESCALATE with full context\n\n"
            "FIX OPTIONS (ranked):\n"
            "  1. rollback: Revert algorithm to last known good version\n"
            "  2. feature_override: Use cached/fallback value for drifting feature\n"
            "  3. zone_exclude: Temporarily exclude affected zones from algorithm\n"
            "  4. pause: Stop algorithm, use flat rate/default until fixed\n\n"
            "STEPS:\n"
            "1. Call get_runbook_matches — match root cause to historical fix\n"
            "2. Select fix option based on confidence\n"
            "3. If AUTO-EXECUTE: apply fix via backend API, verify via get_decision_distribution\n"
            "4. Verification: new distribution should match baseline within 10 minutes\n"
            "5. Update incident status to resolved or escalated\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            "  \"incident_id\": \"\", \"fix_applied\": \"\",\n"
            "  \"auto_executed\": false, \"confidence\": 0.0,\n"
            "  \"verification_status\": \"pending|verified|failed\"\n"
            "}"
        )
    ),

    make_agent(
        "catalog-analyst",
        "Catalog Analyst",
        "Analyzes newly ingested products. Identifies schema gaps and missing attributes.",
        ["get_products_needing_analysis", "get_category_schema_stats",
         "get_similar_products", "platform.core.search"],
        (
            "You are Catalog Analyst — first-stage catalog intelligence agent.\n\n"
            "GOAL: Find schema gaps in newly ingested products.\n\n"
            "STEPS:\n"
            "1. Call get_products_needing_analysis (interval='1 hours', limit=50)\n"
            "2. For each product:\n"
            "   a. Call get_category_schema_stats for product's category\n"
            "   b. Compare product.attributes vs high-support schema attributes\n"
            "   c. Flag attributes present in >50% of similar products but missing from this product\n"
            "3. Prioritize by: high support% AND high revenue impact categories\n"
            "4. Delegate to Schema Mapper via A2A:\n"
            "   POST /api/agent_builder/a2a/schema-mapper\n"
            "   Body: {\"message\": \"Map attributes for products: <JSON list>\"}\n\n"
            "OUTPUT JSON per product:\n"
            "{\n"
            "  \"product_id\": \"\", \"category\": \"\",\n"
            "  \"missing_attrs\": [], \"unknown_attrs\": [],\n"
            "  \"schema_completeness\": 0.0\n"
            "}"
        )
    ),

    make_agent(
        "schema-mapper",
        "Schema Mapper",
        "Maps unknown/non-standard product attributes to canonical schema names.",
        ["get_category_schema_stats", "get_similar_products", "get_schema_mappings_history"],
        (
            "You are Schema Mapper — maps product attributes to canonical schema.\n"
            "You receive schema gap analysis from Catalog Analyst via A2A.\n\n"
            "MAPPING STRATEGY:\n"
            "1. Call get_category_schema_stats — get canonical attribute names\n"
            "2. For each unknown attribute:\n"
            "   a. EXACT MATCH: normalize (lowercase, remove spaces/_) → if matches canonical, confidence=0.95\n"
            "   b. TOKEN OVERLAP: 'noise_cancellation' ↔ 'active_noise_cancellation' → confidence=0.8\n"
            "   c. SEMANTIC: use meaning ('anc' → 'active_noise_cancellation') → confidence=0.7\n"
            "3. Call get_schema_mappings_history — check if same mapping was done before\n"
            "4. Apply mappings where confidence >= 0.75\n"
            "5. Delegate to Findability Scorer via A2A:\n"
            "   POST /api/agent_builder/a2a/findability-scorer\n"
            "   Body: {\"message\": \"Score products after mapping: <product_ids>\"}\n\n"
            "OUTPUT JSON per mapping:\n"
            "{\n"
            "  \"product_id\": \"\", \"original\": \"\",\n"
            "  \"canonical\": \"\", \"confidence\": 0.0, \"method\": \"\"\n"
            "}"
        )
    ),

    make_agent(
        "findability-scorer",
        "Findability Scorer",
        "Scores product findability 0-100. Flags products needing improvement.",
        ["get_category_schema_stats", "get_similar_products", "get_low_findability_products"],
        (
            "You are Findability Scorer — measures how discoverable each product is in search.\n"
            "You receive mapped products from Schema Mapper via A2A.\n\n"
            "SCORING FORMULA (0-100):\n"
            "  Start: 100\n"
            "  For each high-support attr (>70%) missing: -15 points\n"
            "  For each medium-support attr (40-70%) missing: -8 points\n"
            "  Description < 30 words: -10\n"
            "  No images: -15\n"
            "  Price = 0: -5\n"
            "  Score = max(0, 100 - total_deductions)\n\n"
            "STEPS:\n"
            "1. Call get_category_schema_stats — get attribute support percentages\n"
            "2. Score each product against the formula\n"
            "3. Call get_similar_products — compare to avg score of similar products\n"
            "4. Calculate visibility_gain_pct: (avg_similar_score - product_score) * 3\n"
            "5. Products < 50: trigger workflow via backend API POST /api/workflows/execute\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            "  \"scored\": 0, \"avg_score\": 0.0,\n"
            "  \"low_score_products\": [{\"product_id\": \"\", \"score\": 0, \"top_issue\": \"\"}],\n"
            "  \"workflows_triggered\": 0\n"
            "}"
        )
    ),

    make_agent(
        "sentinel-overseer",
        "Sentinel Overseer",
        "Governance meta-agent. Monitors all agents, data quality, and system health.",
        ["get_agent_performance", "get_workflow_executions",
         "get_recent_incidents", "get_low_findability_products"],
        (
            "You are Sentinel Overseer — CatalogSentinel's governance meta-agent.\n"
            "Run every 24 hours or on demand. Do NOT participate in main pipelines.\n\n"
            "GOVERNANCE CHECKS:\n"
            "1. Agent health: call get_agent_performance\n"
            "   → FLAG if any agent has failure_rate > 20% in last 24h\n"
            "   → FLAG if avg_duration > 5000ms for any agent\n"
            "2. Drift incidents: call get_recent_incidents (interval='24 hours')\n"
            "   → FLAG if any incident status=detected for >2 hours without resolution\n"
            "   → FLAG if auto_fix_rate < 50%\n"
            "3. Catalog health: call get_low_findability_products (threshold=30)\n"
            "   → FLAG if >1000 products below score 30\n"
            "4. Workflow health: call get_workflow_executions (interval='24 hours')\n"
            "   → FLAG if failure_rate > 10%\n\n"
            "SEVERITY: GOOD (0 flags) | DEGRADED (1-2) | CRITICAL (3+)\n"
            "CRITICAL → set human_review_required = true\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            "  \"checked_at\": \"\", \"overall_health\": \"GOOD|DEGRADED|CRITICAL\",\n"
            "  \"flags\": [], \"human_review_required\": false,\n"
            "  \"agents_healthy\": 0, \"incidents_unresolved\": 0\n"
            "}"
        )
    ),
]


# ── Main ─────────────────────────────────────────────────────

def main():
    print(f"\n{'='*65}")
    print("  CatalogSentinel — Kibana Agent Builder Setup")
    print(f"  Target: {KIBANA_URL}")
    print(f"{'='*65}\n")

    # Connectivity check
    try:
        r = requests.get(TOOLS_URL, headers=HEADERS, timeout=10)
        if r.status_code == 401:
            print("❌ Auth failed — check KIBANA_API_KEY in .env"); sys.exit(1)
        if r.status_code == 404:
            print("❌ Agent Builder not found — need Kibana 9.x / Elastic Cloud Serverless")
            sys.exit(1)
        print("✅ Kibana connected\n")
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to {KIBANA_URL}"); sys.exit(1)

    print(f"📦 Upserting {len(TOOLS)} tools…")
    ok_tools = sum(upsert_tool(t) for t in TOOLS)

    time.sleep(2)

    print(f"\n🤖 Creating {len(AGENTS)} agents (DELETE + POST)…")
    ok_agents = sum(upsert_agent(a) for a in AGENTS)

    ft = len(TOOLS)  - ok_tools
    fa = len(AGENTS) - ok_agents
    print(f"\n{'='*65}")
    print(f"  Tools:  {ok_tools}/{len(TOOLS)}  ({ft} failed)")
    print(f"  Agents: {ok_agents}/{len(AGENTS)}  ({fa} failed)")
    print(f"{'='*65}")

    if ft == 0 and fa == 0:
        print(f"""
✅ {len(TOOLS)} tools + {len(AGENTS)} agents ready!

A2A endpoints:
  POST {KIBANA_URL}/api/agent_builder/a2a/drift-monitor
  POST {KIBANA_URL}/api/agent_builder/a2a/drift-diagnostician
  POST {KIBANA_URL}/api/agent_builder/a2a/catalog-analyst

MCP endpoint:
  {KIBANA_URL}/api/agent_builder/mcp

Next steps:
  1. python backend/scripts/init_indices.py
  2. uvicorn backend.api.main:app --reload
  3. POST http://localhost:8000/api/agents/run-pipeline
""")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()