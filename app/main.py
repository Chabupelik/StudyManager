from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from app.api.v1 import admin, attendance, auth, duties, schedule, stats
from app.core.config import get_settings
from app.core.security import validate_tg_init_data, validate_vk_sign
from app.data.students_data import STAFF, STUDENTS
from app.db.database import async_session_maker, engine
from app.services.audit_service import log_action
from app.services.user_service import UserContext, get_display_name, load_student_cache
from app.websocket.manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("▶ Starting StudyManager...")
    try:
        async with engine.begin() as conn:
            from app.models.base import Base

            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        raise

    async with async_session_maker() as session:
        await load_student_cache(session)
    logger.info("✅ Student cache loaded")

    logger.info("🚀 StudyManager is ready")
    yield

    await engine.dispose()
    logger.info("🛑 StudyManager stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="StudyManager API",
        version="2.0.0",
        docs_url="/docs" if settings.show_docs else None,
        redoc_url="/redoc" if settings.show_docs else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    PREFIX = "/api"
    app.include_router(auth.router, prefix=PREFIX)
    app.include_router(schedule.router, prefix=PREFIX)
    app.include_router(attendance.router, prefix=PREFIX)
    app.include_router(duties.router, prefix=PREFIX)
    app.include_router(stats.router, prefix=PREFIX)
    app.include_router(admin.router, prefix=PREFIX)

    @app.get("/api/uploads/{filename}")
    async def get_upload(filename: str):
        path = f"data/uploads/{filename}"
        if os.path.exists(path):
            headers = {"Cache-Control": "public, max-age=31536000"}
            return FileResponse(path, headers=headers)
        return Response(status_code=404)

    @app.get("/api/avatar/{tg_id}")
    async def get_avatar(tg_id: int):
        path = f"data/avatars/{tg_id}.jpg"
        if os.path.exists(path):
            return FileResponse(path, media_type="image/jpeg")
        return Response(status_code=404)

    @app.get("/api/ping")
    async def ping_health():
        return {"status": "ok"}

    @app.post("/internal/broadcast_duties")
    @app.post("/api/internal/broadcast_duties")
    async def internal_broadcast_duties(
        request: Request,
        x_internal_secret: str | None = Header(default=None),
    ):
        settings = get_settings()
        secret = x_internal_secret or request.headers.get("X-Internal-Secret", "")
        if settings.internal_secret and secret != settings.internal_secret:
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        await manager.broadcast({"type": "update_duties"})
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        ip = websocket.headers.get("x-forwarded-for", "")
        if ip:
            ip = ip.split(",")[0].strip()
        else:
            ip = websocket.client.host if websocket.client else "Unknown"
        user_agent = websocket.headers.get("user-agent", "N/A")

        await manager.connect(websocket)
        try:
            auth_data = await websocket.receive_text()
            settings = get_settings()

            # Попытка 1: TG initData
            tg_user = validate_tg_init_data(auth_data)
            if tg_user and tg_user.get("id"):
                ctx = UserContext(
                    id=int(tg_user["id"]),
                    first_name=tg_user.get("first_name", ""),
                    platform="telegram",
                )
            else:
                # Попытка 2: VK query-строка
                vk_params = validate_vk_sign(auth_data, settings.vk_protected_key)
                person = None
                if vk_params and "vk_user_id" in vk_params:
                    vk_user_id = int(vk_params["vk_user_id"])
                    person = next(
                        (p for p in STUDENTS + STAFF if p.get("vk_id") == vk_user_id),
                        None,
                    )
                if not person:
                    async with async_session_maker() as session:
                        await log_action(
                            session,
                            "System",
                            "WS Auth Failed",
                            f"IP: {ip}, Agent: {user_agent}",
                        )
                    await websocket.close(code=4003)
                    return
                ctx = UserContext(
                    id=person["tg_id"],
                    first_name=person["name"].split()[1]
                    if len(person["name"].split()) > 1
                    else person["name"],
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

    return app


app = create_app()
