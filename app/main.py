from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Header,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.api.v1 import (
    admin,
    attendance,
    auth,
    duties,
    groups,
    groups_schedule,
    schedule,
    stats,
)
from app.core.config import get_settings
from app.core.security import validate_tg_init_data, validate_vk_sign
from app.db.database import async_session_maker, engine
from app.db.redis_client import close_redis_pool, create_redis_pool, get_redis
from app.models.user import User
from app.services.audit_service import log_action
from app.services.user_service import UserContext, get_display_name
from app.websocket.manager import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("studymanager_api")


def get_client_ip(request: Request | WebSocket) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("▶ Starting StudyManager...")

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection established")
    except Exception as e:
        logger.error("❌ Database connection check failed: %s", e)
        sys.exit(1)

    try:
        create_redis_pool()
        redis_client = await get_redis()
        await redis_client.ping()
        logger.info("✅ Redis pool initialised and connection verified")
    except Exception as e:
        logger.error("❌ Redis connection check failed: %s", e)
        sys.exit(1)

    logger.info("🚀 StudyManager is ready")
    yield

    try:
        await close_redis_pool()
        logger.info("✅ Redis pool closed cleanly")
    except Exception as e:
        logger.error("❌ Error closing Redis pool: %s", e)

    try:
        await engine.dispose()
        logger.info("✅ Database engine disposed cleanly")
    except Exception as e:
        logger.error("❌ Error disposing database engine: %s", e)

    logger.info("🛑 StudyManager stopped")


settings = get_settings()

app = FastAPI(
    title="StudyManager API",
    version="2.0.0",
    docs_url="/docs" if settings.show_docs else None,
    redoc_url="/redoc" if settings.show_docs else None,
    openapi_url="/openapi.json" if settings.show_docs else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    if request.url.path in ("/api/ping", "/health"):
        return await call_next(request)

    start_time = time.time()
    response: Response = await call_next(request)
    process_time_ms = (time.time() - start_time) * 1000
    client_ip = get_client_ip(request)

    logger.info(
        '%s - "%s %s" %s (%.2fms)',
        client_ip,
        request.method,
        request.url.path,
        response.status_code,
        process_time_ms,
    )
    return response


PREFIX = "/api"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(schedule.router, prefix=PREFIX)
app.include_router(attendance.router, prefix=PREFIX)
app.include_router(duties.router, prefix=PREFIX)
app.include_router(stats.router, prefix=PREFIX)
app.include_router(admin.router, prefix=PREFIX)
app.include_router(groups.router, prefix=PREFIX)
app.include_router(groups_schedule.router, prefix=PREFIX)


@app.get("/api/ping", summary="Ping health check")
@app.get("/health", summary="Liveness check")
async def ping_health():
    return {"status": "ok"}


@app.get("/ready", summary="Readiness check")
async def readiness_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        redis_client = await get_redis()
        await redis_client.ping()
        return {"status": "ok", "postgres": "connected", "redis": "connected"}
    except Exception as e:
        logger.error("[READY CHECK FAILED]: %s", e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "message": "Системы не готовы: БД или Redis недоступны",
            },
        )


@app.post("/internal/broadcast_duties")
@app.post("/api/internal/broadcast_duties")
async def internal_broadcast_duties(
    request: Request,
    x_internal_secret: str | None = Header(default=None),
):
    app_settings = get_settings()
    secret = x_internal_secret or request.headers.get("X-Internal-Secret", "")
    if app_settings.internal_secret and secret != app_settings.internal_secret:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    await manager.broadcast({"type": "update_duties"})
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    ip = get_client_ip(websocket)
    user_agent = websocket.headers.get("user-agent", "N/A")

    await manager.connect(websocket)
    try:
        auth_data = await websocket.receive_text()
        app_settings = get_settings()

        tg_user = validate_tg_init_data(auth_data)
        if tg_user and tg_user.get("id"):
            ctx = UserContext(
                id=int(tg_user["id"]),
                first_name=tg_user.get("first_name", ""),
                platform="telegram",
            )
        else:
            vk_params = validate_vk_sign(auth_data, app_settings.vk_protected_key)
            user_obj: User | None = None
            if vk_params and "vk_user_id" in vk_params:
                vk_user_id = int(vk_params["vk_user_id"])
                async with async_session_maker() as session:
                    stmt = select(User).where(User.vk_user_id == vk_user_id)
                    res = await session.execute(stmt)
                    user_obj = res.scalar_one_or_none()

            if not user_obj:
                async with async_session_maker() as session:
                    await log_action(
                        session,
                        "System",
                        "WS Auth Failed",
                        f"IP: {ip}, Agent: {user_agent}",
                    )
                await websocket.close(code=4003)
                return

            first_name = (
                user_obj.full_name.split()[1]
                if len(user_obj.full_name.split()) > 1
                else user_obj.full_name
            )
            ctx = UserContext(
                id=user_obj.tg_user_id or user_obj.id,
                first_name=first_name,
                platform="vk",
            )

        user_name = get_display_name(ctx)

        async with async_session_maker() as session:
            await log_action(
                session,
                user_name,
                "WS Connected",
                f"IP: {ip}, Platform: {ctx.platform}, Agent: {user_agent}",
            )

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
