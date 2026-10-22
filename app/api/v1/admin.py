from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import (
    CurrentUserContext,
    RequireAdmin,
    RequireDeveloper,
)
from app.services.audit_service import AuditSrv

router = APIRouter(tags=["admin"])


@router.get("/admin/ping")
async def ping(
    ctx: CurrentUserContext,
    service: AuditSrv,
):
    return await service.ping(ctx)


@router.get("/admin/users")
async def get_admin_users(
    ctx: RequireAdmin,
    service: AuditSrv,
):
    return await service.get_admin_users(ctx)


@router.get("/init")
async def get_init(
    ctx: CurrentUserContext,
    service: AuditSrv,
):
    return service.get_init(ctx)


@router.get("/admin/logs")
async def get_admin_logs(
    ctx: RequireAdmin,
    service: AuditSrv,
    offset: int = 0,
    limit: int = 20,
    user_filter: str = "all",
    action_filter: str = "all",
):
    return await service.get_logs(offset, limit, user_filter, action_filter)


@router.delete("/admin/logs/{log_id}")
async def delete_log(
    log_id: int,
    ctx: RequireDeveloper,
    service: AuditSrv,
):
    return await service.delete_log(log_id)
