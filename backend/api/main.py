"""
CatalogSentinel FastAPI Application
Real-time Algorithm Drift Detection + Catalog Intelligence
"""
from __future__ import annotations
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from utils.logger import setup_logging, get_logger
from es.client import ESClient

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CatalogSentinel starting…")

    # 1. Elasticsearch
    try:
        es = ESClient.sync()
        info = es.info()
        logger.info(f"Elasticsearch {info['version']['number']} connected")
    except Exception as e:
        logger.error(f"Elasticsearch connection failed: {e}")
        raise

    # 2. Create indices if they don't exist
    try:
        from es.indices import create_all_indices
        results = create_all_indices()
        ok = sum(1 for v in results.values() if v)
        logger.info(f"Indices ready: {ok}/{len(results)}")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

    # 3. Redis (optional)
    try:
        from utils.redis_client import ping_redis
        if await ping_redis():
            logger.info("Redis connected")
        else:
            logger.warning("Redis unavailable — proceeding without cache")
    except Exception:
        pass

    # 4. Start drift detector background loop
    try:
        from drift.detector import DriftDetector
        detector = DriftDetector()
        await detector.start()
        app.state.drift_detector = detector
        logger.info("DriftDetector loop started")
    except Exception as e:
        logger.warning(f"DriftDetector start warning: {e}")

    logger.info("CatalogSentinel ready ✓")
    yield

    # Shutdown
    logger.info("Shutting down…")
    try:
        if hasattr(app.state, "drift_detector"):
            await app.state.drift_detector.stop()
        await ESClient.close()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


app = FastAPI(
    title="CatalogSentinel API",
    description=(
        "Real-time Algorithm Drift Detection (DriftSensor) + "
        "Autonomous Catalog Intelligence (CatalogIQ) — powered by Elasticsearch"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request ID + timing ─────────────────────────────────────
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = rid
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Request-ID"] = rid
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    if elapsed > 2.0:
        logger.warning(f"Slow request: {request.method} {request.url.path} {elapsed:.2f}s")
    return response


# ── Routers ──────────────────────────────────────────────────
from api.routers import health, drift, catalog, agents, workflows

app.include_router(health.router, prefix="/api")
app.include_router(drift.router)
app.include_router(catalog.router)
app.include_router(agents.router)
app.include_router(workflows.router)


# ── Root ─────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": "CatalogSentinel",
        "version": "1.0.0",
        "modules": {
            "drift_sensor": "Real-time algorithm drift detection",
            "catalog_iq": "Autonomous schema inference + findability scoring",
        },
        "docs": "/docs",
        "health": "/api/health",
    }


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse(status_code=404, content={"error": "Not found", "path": request.url.path})


@app.exception_handler(500)
async def server_error(request: Request, exc):
    logger.error(f"500 error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": getattr(request.state, "request_id", "")},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )
