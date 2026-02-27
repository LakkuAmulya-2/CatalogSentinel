"""Product catalog model."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CatalogProduct(BaseModel):
    product_id: str
    sku: str = ""
    name: str
    brand: str = ""
    category: str = ""
    subcategory: str = ""
    price: float = 0.0
    currency: str = "INR"
    description: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)
    images: List[str] = Field(default_factory=list)
    platform: str = ""
    findability_score: float = 0.0
    schema_completeness: float = 0.0
    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    def to_doc(self) -> dict:
        d = self.model_dump()
        d["ingested_at"] = self.ingested_at.isoformat()
        d["updated_at"] = datetime.utcnow().isoformat()
        return d


class SchemaMapping(BaseModel):
    original_attr: str
    mapped_attr: str
    confidence: float
    method: str = "semantic"   # semantic | frequency | exact
    auto_applied: bool = False


class FindabilityIssue(BaseModel):
    field: str
    issue: str
    impact: str   # high | medium | low
    suggestion: str


class FindabilityReport(BaseModel):
    product_id: str
    product_name: str
    score: float
    issues: List[FindabilityIssue] = Field(default_factory=list)
    missing_attributes: List[str] = Field(default_factory=list)
    schema_mappings: List[SchemaMapping] = Field(default_factory=list)
    estimated_visibility_gain_pct: float = 0.0
    computed_at: datetime = Field(default_factory=datetime.utcnow)
