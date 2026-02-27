"""Algorithm decision model."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float
    lon: float
    zone: str = ""
    city: str = ""


class AlgorithmDecision(BaseModel):
    decision_id: str
    algorithm: str          # surge_pricing | recommendation | search_rank | delivery_eta
    version: str = "1.0"
    company: str = ""
    platform: str = ""
    input_features: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    location: Optional[Location] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_doc(self) -> dict:
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        d["ingested_at"] = datetime.utcnow().isoformat()
        if self.location:
            d["location"] = self.location.model_dump()
        return d


class DriftIncident(BaseModel):
    incident_id: str
    algorithm: str
    drift_score: float
    kl_divergence: float
    affected_metric: str
    affected_zones: list[str] = Field(default_factory=list)
    root_cause: str = ""
    root_cause_feature: str = ""
    revenue_impact_inr: float = 0.0
    status: str = "detected"   # detected | investigating | auto_fixing | resolved
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    resolution: Dict[str, Any] = Field(default_factory=dict)
    agent_analysis: str = ""
