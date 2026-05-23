from fastapi import APIRouter, Request

from app.core.app_context import get_app_context_from_request
from app.operations.events import (
    OperationsAuditRequest,
    OperationsStatusRequest,
    REQUEST_OPERATIONS_AUDIT_LOG,
    REQUEST_OPERATIONS_STATUS,
)


router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/status")
async def status(request: Request, limit: int = 10) -> dict[str, object]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_OPERATIONS_STATUS,
        OperationsStatusRequest(limit=limit),
        source_module="operations.adapters.api.routes",
    )


@router.get("/audit-log")
async def audit_log(request: Request, limit: int = 50) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    return context.event_bus.request(
        REQUEST_OPERATIONS_AUDIT_LOG,
        OperationsAuditRequest(limit=limit),
        source_module="operations.adapters.api.routes",
    )