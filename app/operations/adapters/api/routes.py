from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.app_context import get_app_context_from_request


class OperationsSagaStartInput(BaseModel):
    title: str
    premise: str = ""
    summary: str = ""
    world_building: str = ""
    initial_command: str = ""


class OperationsSagaCommandInput(BaseModel):
    command: str
    note: str = ""


class OperationsSagaUpdateInput(BaseModel):
    title: str | None = None
    premise: str | None = None
    summary: str | None = None
    status: str | None = None
    world_building: str | None = None


router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/status")
async def status(request: Request, limit: int = 10) -> dict[str, object]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsStatusRequest
    from app.operations.events import REQUEST_OPERATIONS_STATUS

    return context.event_bus.request(
        REQUEST_OPERATIONS_STATUS,
        OperationsStatusRequest(limit=limit),
        source_module="operations.adapters.api.routes",
    )


@router.get("/audit-log")
async def audit_log(request: Request, limit: int = 50) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsAuditRequest
    from app.operations.events import REQUEST_OPERATIONS_AUDIT_LOG

    return context.event_bus.request(
        REQUEST_OPERATIONS_AUDIT_LOG,
        OperationsAuditRequest(limit=limit),
        source_module="operations.adapters.api.routes",
    )


@router.get("/sagas")
async def list_sagas(request: Request, limit: int = 20) -> list[dict[str, object]]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsSagaListRequest
    from app.operations.events import REQUEST_OPERATIONS_SAGA_LIST

    return context.event_bus.request(
        REQUEST_OPERATIONS_SAGA_LIST,
        OperationsSagaListRequest(limit=limit),
        source_module="operations.adapters.api.routes",
    )


@router.get("/sagas/{saga_id}")
async def get_saga(request: Request, saga_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsSagaDetailRequest
    from app.operations.events import REQUEST_OPERATIONS_SAGA_DETAIL

    return context.event_bus.request(
        REQUEST_OPERATIONS_SAGA_DETAIL,
        OperationsSagaDetailRequest(saga_id=saga_id),
        source_module="operations.adapters.api.routes",
    )


@router.post("/sagas")
async def start_saga(request: Request, payload: OperationsSagaStartInput) -> dict[str, object]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsSagaStartRequest
    from app.operations.events import REQUEST_OPERATIONS_SAGA_START

    return context.event_bus.request(
        REQUEST_OPERATIONS_SAGA_START,
        OperationsSagaStartRequest(
            title=payload.title,
            premise=payload.premise,
            summary=payload.summary,
            world_building=payload.world_building,
            initial_command=payload.initial_command,
        ),
        source_module="operations.adapters.api.routes",
    )


@router.post("/sagas/{saga_id}/commands")
async def append_saga_command(
    request: Request,
    saga_id: str,
    payload: OperationsSagaCommandInput,
) -> dict[str, object]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsSagaCommandAppendRequest
    from app.operations.events import REQUEST_OPERATIONS_SAGA_COMMAND_APPEND

    return context.event_bus.request(
        REQUEST_OPERATIONS_SAGA_COMMAND_APPEND,
        OperationsSagaCommandAppendRequest(saga_id=saga_id, command=payload.command, note=payload.note),
        source_module="operations.adapters.api.routes",
    )


@router.patch("/sagas/{saga_id}")
async def update_saga(
    request: Request,
    saga_id: str,
    payload: OperationsSagaUpdateInput,
) -> dict[str, object]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsSagaUpdateRequest
    from app.operations.events import REQUEST_OPERATIONS_SAGA_UPDATE

    return context.event_bus.request(
        REQUEST_OPERATIONS_SAGA_UPDATE,
        OperationsSagaUpdateRequest(
            saga_id=saga_id,
            title=payload.title,
            premise=payload.premise,
            summary=payload.summary,
            status=payload.status,
            world_building=payload.world_building,
        ),
        source_module="operations.adapters.api.routes",
    )


@router.delete("/sagas/{saga_id}")
async def delete_saga(request: Request, saga_id: str) -> dict[str, object]:
    context = get_app_context_from_request(request)
    from app.operations.events import OperationsSagaDeleteRequest
    from app.operations.events import REQUEST_OPERATIONS_SAGA_DELETE

    return context.event_bus.request(
        REQUEST_OPERATIONS_SAGA_DELETE,
        OperationsSagaDeleteRequest(saga_id=saga_id),
        source_module="operations.adapters.api.routes",
    )