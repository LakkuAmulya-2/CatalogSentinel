"""
Elastic Workflow automation engine.
Triggered by drift incidents and catalog events.
Stores all workflow executions in catalogsentinel-workflows.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from es.client import get_async_es
from workflows.slack_client import SlackClient
from workflows.jira_client import JiraClient
from utils.logger import get_logger

logger = get_logger(__name__)

WORKFLOWS_IDX = "catalogsentinel-workflows"


class WorkflowEngine:
    def __init__(self):
        self.slack = SlackClient()
        self.jira = JiraClient()

    async def trigger_drift_workflow(self, incident: Dict[str, Any]) -> Dict[str, Any]:
        wf_id = f"wf-drift-{str(uuid.uuid4())[:8]}"
        started = datetime.utcnow()
        actions_taken = []
        details: Dict[str, Any] = {}

        logger.info(f"Drift workflow {wf_id} starting for incident {incident.get('incident_id')}")

        # Action 1: Slack alert
        slack_ok = await self.slack.send_drift_alert(incident)
        if slack_ok:
            actions_taken.append("slack_alert")
            details["slack"] = "sent"

        # Action 2: Jira ticket
        ticket = await self.jira.create_drift_ticket(incident)
        if ticket:
            actions_taken.append("jira_ticket")
            details["jira_ticket"] = ticket

        # Action 3: Store workflow record
        wf_doc = {
            "workflow_id": wf_id,
            "trigger": "drift_incident",
            "entity_id": incident.get("incident_id", ""),
            "entity_type": "drift_incident",
            "actions": actions_taken,
            "status": "completed",
            "jira_ticket": ticket or "",
            "slack_sent": slack_ok,
            "created_at": started.isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "details": details,
        }

        es = get_async_es()
        await es.index(index=WORKFLOWS_IDX, id=wf_id, document=wf_doc, refresh=True)

        # Action 4: Update incident with workflow reference
        await es.update(
            index="catalogsentinel-drift-incidents",
            id=incident["incident_id"],
            doc={"workflow_id": wf_id, "workflow_actions": actions_taken},
        )

        logger.info(f"Drift workflow {wf_id} completed: {actions_taken}")
        return wf_doc

    async def trigger_catalog_workflow(self, report: Dict[str, Any]) -> Dict[str, Any]:
        wf_id = f"wf-catalog-{str(uuid.uuid4())[:8]}"
        started = datetime.utcnow()
        actions_taken = []
        details: Dict[str, Any] = {}

        # Only trigger full workflow for low-score products
        if report.get("findability_score", 100) < 50:
            slack_ok = await self.slack.send_catalog_alert(report)
            if slack_ok:
                actions_taken.append("slack_alert")

            if report.get("findability_score", 100) < 30:
                ticket = await self.jira.create_catalog_ticket(report)
                if ticket:
                    actions_taken.append("jira_ticket")
                    details["jira_ticket"] = ticket

        wf_doc = {
            "workflow_id": wf_id,
            "trigger": "low_findability",
            "entity_id": report.get("product_id", ""),
            "entity_type": "catalog_product",
            "actions": actions_taken,
            "status": "completed",
            "slack_sent": "slack_alert" in actions_taken,
            "created_at": started.isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "details": {**details, "findability_score": report.get("findability_score")},
        }

        es = get_async_es()
        await es.index(index=WORKFLOWS_IDX, id=wf_id, document=wf_doc, refresh=True)
        return wf_doc

    async def get_workflow_history(
        self, limit: int = 100, status: Optional[str] = None, trigger: Optional[str] = None
    ) -> List[Dict]:
        es = get_async_es()
        must = []
        if status:
            must.append({"term": {"status": status}})
        if trigger:
            must.append({"term": {"trigger": trigger}})
        query = {"bool": {"must": must}} if must else {"match_all": {}}
        try:
            resp = await es.search(
                index=WORKFLOWS_IDX,
                query=query,
                sort=[{"created_at": {"order": "desc"}}],
                size=limit,
            )
            return [h["_source"] for h in resp["hits"]["hits"]]
        except Exception as e:
            logger.error(f"get_workflow_history: {e}")
            return []
