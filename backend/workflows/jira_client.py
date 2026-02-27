"""Jira ticket creation for drift incidents."""
from __future__ import annotations
import base64
import httpx
from typing import Any, Dict, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class JiraClient:
    def __init__(self):
        from config.settings import settings
        self.url = settings.JIRA_URL.rstrip("/")
        self.email = settings.JIRA_EMAIL
        self.token = settings.JIRA_API_TOKEN
        self.project = settings.JIRA_PROJECT_KEY

    @property
    def _headers(self) -> Dict[str, str]:
        creds = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
        return {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }

    async def create_drift_ticket(self, incident: Dict[str, Any]) -> Optional[str]:
        if not all([self.url, self.email, self.token]):
            logger.warning("Jira not configured — skipping ticket creation")
            return None

        algo = incident.get("algorithm", "unknown")
        kl = incident.get("kl_divergence", 0)
        impact = incident.get("revenue_impact_inr", 0)

        payload = {
            "fields": {
                "project": {"key": self.project},
                "summary": f"[DRIFT] {algo} algorithm — KL={kl:.4f} impact=₹{impact:,.0f}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        f"Algorithm drift detected on '{algo}'.\n\n"
                                        f"KL Divergence: {kl:.4f}\n"
                                        f"Revenue Impact: ₹{impact:,.0f}/hr\n"
                                        f"Incident ID: {incident.get('incident_id', '')}\n"
                                        f"Affected Zones: {', '.join(incident.get('affected_zones', []))}\n\n"
                                        f"Root Cause: {incident.get('root_cause', 'Under investigation')}\n\n"
                                        f"Agent Analysis:\n{incident.get('agent_analysis', 'Pending...')}"
                                    ),
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {"name": "Bug"},
                "priority": {"name": "Highest" if kl > 0.6 else "High"},
                "labels": ["drift", "algorithm", algo],
            }
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.url}/rest/api/3/issue",
                    headers=self._headers,
                    json=payload,
                )
                if resp.status_code in (200, 201):
                    key = resp.json().get("key")
                    logger.info(f"Jira ticket created: {key}")
                    return key
                logger.error(f"Jira failed: {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Jira create_drift_ticket: {e}")
            return None

    async def create_catalog_ticket(self, report: Dict[str, Any]) -> Optional[str]:
        if not all([self.url, self.email, self.token]):
            return None

        payload = {
            "fields": {
                "project": {"key": self.project},
                "summary": f"[CATALOG] Low findability: {report.get('product_name', '')} — score {report.get('findability_score', 0):.0f}/100",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        f"Product: {report.get('product_name')}\n"
                                        f"ID: {report.get('product_id')}\n"
                                        f"Findability Score: {report.get('findability_score', 0):.0f}/100\n\n"
                                        f"Issues:\n"
                                        + "\n".join(
                                            f"- [{i['impact'].upper()}] {i['field']}: {i['suggestion']}"
                                            for i in report.get("issues", [])
                                        )
                                    ),
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {"name": "Task"},
                "priority": {"name": "Medium"},
                "labels": ["catalog", "findability"],
            }
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.url}/rest/api/3/issue",
                    headers=self._headers,
                    json=payload,
                )
                if resp.status_code in (200, 201):
                    return resp.json().get("key")
                return None
        except Exception as e:
            logger.error(f"Jira catalog ticket: {e}")
            return None
