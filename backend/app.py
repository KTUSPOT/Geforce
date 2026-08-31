import os
import sys
import time
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

from backend.config import settings
from backend.db.database import db_manager
from backend.db.repository import repository
from backend.cache.manager import cache_manager
from backend.cache.warmer import cache_warmer
from backend.cache.singleflight import single_flight
from backend.services.result_service import result_service
from backend.services.import_service import import_service
from backend.auth import (
    verify_password,
    create_access_token,
    get_current_admin
)
from backend.middleware.rate_limiter import RateLimiterMiddleware
from backend.middleware.security import SecurityHeadersMiddleware
from backend.monitoring.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    ACTIVE_REQUESTS,
    export_metrics
)

# Application Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db_manager.initialize()
    await cache_manager.initialize()
    yield
    # Shutdown
    await cache_manager.close()
    await db_manager.close()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None
)

# Middlewares (Order: Outer to Inner)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimiterMiddleware, requests_per_minute=settings.RATE_LIMIT_SEARCH_PER_MINUTE, burst_limit=settings.RATE_LIMIT_BURST)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Metrics Middleware Hook
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    ACTIVE_REQUESTS.inc()
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        duration = time.perf_counter() - start_time
        path = request.url.path
        # Group result lookups for clean metrics
        metric_path = "/api/v1/results" if path.startswith("/api/v1/results") else path
        HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=metric_path, status=response.status_code).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(endpoint=metric_path).observe(duration)
        return response
    finally:
        ACTIVE_REQUESTS.dec()

# ----------------- Models -----------------
class LoginRequest(BaseModel):
    username: str
    password: str

class PublishRequest(BaseModel):
    is_published: bool

class WarmCacheRequest(BaseModel):
    exam_id: str

# ----------------- Public Student Endpoints -----------------

@app.get("/api/v1/results", summary="Fetch KTU Student Exam Result")
async def get_student_result(
    registerNumber: str = Query(..., description="KTU Student Register Number, e.g. TVE21CS001"),
    examId: str = Query(..., description="Examination ID, e.g. BT_S6_MAY26")
):
    """
    Ultra-High-Throughput Endpoint for searching exam results.
    Primary Flow: L1 Memory Cache -> L2 Redis Cache -> Single-Flight Coalescer -> Indexed Database.
    """
    res = await result_service.search_result(registerNumber, examId)
    if not res.get("success"):
        raise HTTPException(
            status_code=res.get("status_code", 400),
            detail=res.get("error", "Error retrieving result")
        )
    return res

@app.get("/api/v1/exams", summary="Get Active Examinations")
async def get_active_exams():
    """Retrieve published examinations for the homepage dropdown."""
    exams = await repository.get_published_exams()
    return {"success": True, "data": exams}

# ----------------- Admin Endpoints -----------------

@app.post("/api/v1/admin/auth/login", summary="Admin Login")
async def admin_login(body: LoginRequest):
    admin = await repository.get_admin_user(body.username)
    if not admin or not verify_password(body.password, admin["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
    
    token = create_access_token({"sub": admin["username"], "role": admin["role"], "name": admin["full_name"]})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": admin["username"],
            "name": admin["full_name"],
            "role": admin["role"]
        }
    }

@app.get("/api/v1/admin/auth/me", summary="Get Current Admin Profile")
async def admin_profile(current_admin: dict = Depends(get_current_admin)):
    return {"success": True, "data": current_admin}

@app.get("/api/v1/admin/exams", summary="List All Exams (Admin View)")
async def admin_list_exams(current_admin: dict = Depends(get_current_admin)):
    exams = await repository.get_all_exams_admin()
    return {"success": True, "data": exams}

@app.post("/api/v1/admin/exams/{exam_id}/publish", summary="Publish or Unpublish Exam")
async def admin_toggle_publish(
    exam_id: str, 
    body: PublishRequest, 
    current_admin: dict = Depends(get_current_admin)
):
    await repository.set_exam_published(exam_id, body.is_published)
    # If unpublishing, purge cache
    if not body.is_published:
        await cache_manager.invalidate_exam(exam_id)
    return {"success": True, "message": f"Examination {'published' if body.is_published else 'unpublished'} successfully."}

@app.post("/api/v1/admin/cache/warm", summary="Trigger Cache Pre-Warming")
async def admin_warm_cache(
    body: WarmCacheRequest,
    current_admin: dict = Depends(get_current_admin)
):
    job_id = await cache_warmer.start_warming_job(body.exam_id)
    return {"success": True, "job_id": job_id, "message": f"Cache pre-warming started for exam '{body.exam_id}'."}

@app.get("/api/v1/admin/cache/warm/{job_id}", summary="Get Cache Warming Status")
async def admin_warm_cache_status(job_id: str, current_admin: dict = Depends(get_current_admin)):
    st = cache_warmer.get_job_status(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="Warming job not found.")
    return {"success": True, "data": st}

@app.post("/api/v1/admin/results/upload", summary="Bulk Upload Result File (CSV/Excel)")
async def admin_upload_results(
    exam_id: str = Form(...),
    file: UploadFile = File(...),
    current_admin: dict = Depends(get_current_admin)
):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".csv", ".xlsx", ".xls"]:
        raise HTTPException(status_code=400, detail="Only CSV (.csv) and Excel (.xlsx) files are supported.")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File exceeds maximum size of 50MB.")

    job_id = await import_service.create_import_job(exam_id, file.filename)
    # Trigger background parsing & db import
    import asyncio
    asyncio.create_task(import_service.process_file_in_background(job_id, exam_id, file_bytes, ext))

    return {
        "success": True, 
        "job_id": job_id, 
        "message": f"File '{file.filename}' uploaded successfully. Processing {file.filename} in background."
    }

@app.get("/api/v1/admin/results/import-jobs/{job_id}", summary="Get Import Job Status")
async def admin_get_import_job(job_id: str, current_admin: dict = Depends(get_current_admin)):
    st = import_service.get_job_status(job_id)
    if not st:
        # Fallback to database
        row = await db_manager.fetch_one("SELECT * FROM import_jobs WHERE id = ?", (job_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Import job not found.")
        st = dict(row)
    return {"success": True, "data": st}

@app.get("/api/v1/admin/stats", summary="Live System & Cache Statistics")
async def admin_get_stats(current_admin: dict = Depends(get_current_admin)):
    db_stats = await repository.get_system_stats()
    c_stats = cache_manager.get_stats()
    return {
        "success": True,
        "database": db_stats,
        "cache": c_stats,
        "coalescer": {
            "stampede_queries_prevented": single_flight.coalesced_count
        }
    }

# ----------------- Health & Monitoring Endpoints -----------------

@app.get("/health/live", summary="Liveness Probe")
async def health_live():
    return {"status": "UP", "timestamp": time.time()}

@app.get("/health/ready", summary="Readiness Probe")
async def health_ready():
    # Verify DB connectivity
    try:
        await db_manager.fetch_one("SELECT 1")
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "DOWN", "error": f"Database unreachable: {e}"})

    return {
        "status": "READY",
        "database": "CONNECTED",
        "redis": "CONNECTED" if cache_manager.redis_available else "STANDALONE_L1",
        "l1_cache_size": cache_manager.l1.size()
    }

@app.get("/metrics", summary="Prometheus Metrics")
async def metrics():
    return export_metrics()

# ----------------- Frontend & Static Files -----------------

frontend_path = settings.FRONTEND_DIR
if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")
    app.mount("/css", StaticFiles(directory=str(frontend_path / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(frontend_path / "js")), name="js")

    @app.get("/", response_class=FileResponse)
    async def serve_home():
        return FileResponse(frontend_path / "index.html")

    @app.get("/admin", response_class=FileResponse)
    async def serve_admin():
        return FileResponse(frontend_path / "admin.html")

    @app.get("/result", response_class=FileResponse)
    async def serve_result_deep_link():
        return FileResponse(frontend_path / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app:app", 
        host=settings.HOST, 
        port=settings.PORT, 
        reload=settings.DEBUG,
        workers=1
    )
