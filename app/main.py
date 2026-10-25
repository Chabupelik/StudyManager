from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.dependencies import get_client_ip
from app.api.v1 import (
    admin,
    attendance,
    duties,
    groups,
    groups_schedule,
    internal,
    schedule,
    stats,
    websocket,
)
from app.core.config import get_settings
from app.db.database import DbSession, engine
from app.db.redis_client import RedisClient, get_raw_redis_client
from app.schemas.common import ResponseError, ResponseOK

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("studymanager_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        await get_raw_redis_client().ping()
        logger.info("Database and Redis connections established successfully")
    except Exception as e:
        logger.error("Connection check failed: %s", e)
        sys.exit(1)

    yield

    try:
        await engine.dispose()
        await get_raw_redis_client().aclose()
        logger.info("Database and Redis connections closed cleanly")
    except Exception as e:
        logger.error("Error during connection teardown: %s", e)


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
    url_path = (
        f"{request.url.path}?{request.url.query}"
        if request.url.query
        else request.url.path
    )

    logger.info(
        '%s - "%s %s" %s (%.2fms)',
        client_ip,
        request.method,
        url_path,
        response.status_code,
        process_time_ms,
    )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ResponseError(message=exc.detail).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        f"[{' -> '.join(str(x) for x in e['loc'])}]: {e['msg']}" for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ResponseError(
            message="Ошибка валидации входных данных", details=errors
        ).model_dump(),
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    errors = [
        f"[{' -> '.join(str(x) for x in e['loc'])}]: {e['msg']}" for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ResponseError(
            message="Ошибка валидации входных данных", details=errors
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("%s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ResponseError(
            message="Внутренняя ошибка сервера. Пожалуйста, попробуйте позже."
        ).model_dump(),
    )


@app.get(
    "/health",
    response_model=ResponseOK[dict],
    summary="Liveness check",
)
@app.get(
    "/api/ping",
    summary="Legacy ping check",
)
async def health_check():
    return ResponseOK(data={"message": "API is alive"})


@app.get(
    "/ready",
    response_model=ResponseOK[dict],
    summary="Readiness check",
)
async def ready_check(
    db: DbSession,
    redis: RedisClient,
):
    try:
        await db.execute(text("SELECT 1"))
        await redis.ping()
        return ResponseOK(data={"postgres": "connected", "redis": "connected"})
    except Exception as e:
        logger.error("[READY CHECK FAILED]: %s", e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ResponseError(
                message="Системы не готовы к работе: БД или Redis недоступны"
            ).model_dump(),
        )


PREFIX = "/api"
app.include_router(schedule.router, prefix=PREFIX)
app.include_router(attendance.router, prefix=PREFIX)
app.include_router(duties.router, prefix=PREFIX)
app.include_router(stats.router, prefix=PREFIX)
app.include_router(admin.router, prefix=PREFIX)
app.include_router(groups.router, prefix=PREFIX)
app.include_router(groups_schedule.router, prefix=PREFIX)
app.include_router(internal.router)
app.include_router(websocket.router)
