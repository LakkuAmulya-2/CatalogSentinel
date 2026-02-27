"""Analytics stub — metrics are exposed via drift and catalog routers."""
from fastapi import APIRouter
router = APIRouter(prefix="/api/analytics", tags=["analytics"])
