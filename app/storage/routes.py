from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.app_context import get_app_context_from_request
from app.storage.service import UploadStorage

router = APIRouter(tags=["storage"])


def _get_storage(request: Request) -> UploadStorage:
    context = get_app_context_from_request(request)
    storage = context.services.get("storage")
    if not isinstance(storage, UploadStorage):
        raise RuntimeError("Storage service not available")
    return storage


@router.get("/api/storage/overview")
async def storage_overview(request: Request) -> dict[str, object]:
    return _get_storage(request).overview()


@router.get("/api/storage/public")
async def list_public_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_public_files())


@router.get("/api/storage/uploads")
async def list_upload_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_upload_files())
