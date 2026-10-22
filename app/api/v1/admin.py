from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import (
    CurrentUser,
    RequireAdmin,
    RequireDeveloper,
)
from app.services.audit_service import AuditSrv

router = APIRouter(tags=["admin"])


@router.get("/admin/ping")
async def ping(
    current_user: CurrentUser,
    service: AuditSrv,
):
    return await service.ping(current_user)


@router.get("/admin/users")
async def get_admin_users(
    current_user: RequireAdmin,
    service: AuditSrv,
):
    return await service.get_admin_users(current_user)


@router.get("/init")
async def get_init(
    current_user: CurrentUser,
    service: AuditSrv,
):
    return service.get_init(current_user)


@router.get("/admin/logs")
async def get_admin_logs(
    current_user: RequireAdmin,
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
    current_user: RequireDeveloper,
    service: AuditSrv,
):
    return await service.delete_log(log_id)
