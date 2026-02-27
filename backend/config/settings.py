"""
CatalogSentinel Configuration
Pydantic-based settings loaded from .env
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    # ── Elasticsearch ────────────────────────────────────────
    ES_URL: str
    ES_API_KEY: str
    ES_CLOUD_ID: Optional[str] = None

    # ── Kibana ───────────────────────────────────────────────
    KIBANA_URL: str = "http://localhost:5601"
    KIBANA_API_KEY: str = ""

    # ── Redis ────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── FastAPI ──────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    LOG_LEVEL: str = "info"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def kibana_api_key_resolved(self) -> str:
        return self.KIBANA_API_KEY or self.ES_API_KEY

    # ── Jina ────────────────────────────────────────────────
    JINA_API_KEY: str = ""
    JINA_EMBEDDINGS_MODEL: str = "jina-embeddings-v3"

    # ── Slack ────────────────────────────────────────────────
    SLACK_WEBHOOK_URLS: str = "{}"

    @property
    def slack_webhooks(self) -> Dict[str, str]:
        try:
            return json.loads(self.SLACK_WEBHOOK_URLS)
        except Exception:
            return {}

    # ── Jira ────────────────────────────────────────────────
    JIRA_URL: str = ""
    JIRA_EMAIL: str = ""
    JIRA_API_TOKEN: str = ""
    JIRA_PROJECT_KEY: str = "CS"

    # ── Drift Detection ──────────────────────────────────────
    DRIFT_KL_THRESHOLD: float = 0.3
    DRIFT_CHECK_INTERVAL_SECONDS: int = 60
    DRIFT_BASELINE_DAYS: int = 7
    DRIFT_AUTO_FIX_CONFIDENCE: float = 0.85

    # ── Catalog Intelligence ─────────────────────────────────
    CATALOG_FINDABILITY_THRESHOLD: int = 50
    CATALOG_SCHEMA_INFERENCE_MIN_SUPPORT: float = 0.3
    CATALOG_AUTO_MAP_CONFIDENCE: float = 0.75


settings = Settings()
