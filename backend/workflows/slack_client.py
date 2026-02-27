"""Slack webhook notifications."""
from __future__ import annotations
import httpx
from datetime import datetime
from typing import Any, Dict, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class SlackClient:
    def __init__(self):
        from config.settings import settings
        self.webhooks = settings.slack_webhooks

    async def send_drift_alert(self, incident: Dict[str, Any]) -> bool:
        webhook = self.webhooks.get("drift-alerts")
        if not webhook:
            logger.warning("No drift-alerts Slack webhook configured")
            return False

        algo = incident.get("algorithm", "unknown")
        kl = incident.get("kl_divergence", 0)
        impact = incident.get("revenue_impact_inr", 0)
        zones = ", ".join(incident.get("affected_zones", [])[:3]) or "unknown zones"
        auto_fixed = incident.get("resolution", {}).get("auto_fixed", False)

        color = "#FF0000" if kl > 0.6 else "#FF8C00"
        status_emoji = "✅ Auto-fixed" if auto_fixed else "🔴 Needs attention"

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"🚨 Algorithm Drift Detected: {algo}",
                    "fields": [
                        {"title": "KL Divergence", "value": f"{kl:.4f}", "short": True},
                        {"title": "Revenue Impact", "value": f"₹{impact:,.0f}/hr", "short": True},
                        {"title": "Affected Zones", "value": zones, "short": True},
                        {"title": "Status", "value": status_emoji, "short": True},
                        {"title": "Incident ID", "value": incident.get("incident_id", ""), "short": False},
                        {"title": "Root Cause", "value": incident.get("root_cause", "Investigating..."), "short": False},
                    ],
                    "footer": "CatalogSentinel DriftSensor",
                    "ts": int(datetime.utcnow().timestamp()),
                }
            ]
        }
        return await self._post(webhook, payload)

    async def send_catalog_alert(self, report: Dict[str, Any]) -> bool:
        webhook = self.webhooks.get("catalog-alerts")
        if not webhook:
            logger.warning("No catalog-alerts Slack webhook configured")
            return False

        payload = {
            "attachments": [
                {
                    "color": "#36a64f",
                    "title": f"📦 CatalogIQ: {report.get('product_name', 'Product')} processed",
                    "fields": [
                        {"title": "Findability Score", "value": f"{report.get('findability_score', 0):.0f}/100", "short": True},
                        {"title": "Mappings Applied", "value": str(report.get("mappings_applied", 0)), "short": True},
                        {"title": "Visibility Gain", "value": f"+{report.get('estimated_visibility_gain_pct', 0):.0f}%", "short": True},
                        {"title": "Product ID", "value": report.get("product_id", ""), "short": True},
                    ],
                    "footer": "CatalogSentinel CatalogIQ",
                    "ts": int(datetime.utcnow().timestamp()),
                }
            ]
        }
        return await self._post(webhook, payload)

    async def _post(self, webhook: str, payload: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook, json=payload)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Slack post failed: {e}")
            return False
