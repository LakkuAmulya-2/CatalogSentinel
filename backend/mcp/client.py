"""MCP client — calls Kibana-exposed ES|QL tools via MCP endpoint."""
from __future__ import annotations
import httpx
from typing import Any, Dict
from utils.logger import get_logger

logger = get_logger(__name__)


class MCPClient:
    def __init__(self):
        from config.settings import settings
        self.endpoint = f"{settings.KIBANA_URL.rstrip('/')}/api/agent_builder/mcp"
        self.api_key = settings.kibana_api_key_resolved
        self.headers = {
            "Authorization": f"ApiKey {self.api_key}",
            "Content-Type": "application/json",
            "kbn-xsrf": "true",
        }

    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.endpoint,
                    headers=self.headers,
                    json={"name": tool_name, "parameters": parameters},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"MCP call_tool {tool_name}: {e}")
            raise
