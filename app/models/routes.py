from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.core.app_context import get_app_context_from_request
from app.models.runtime_service import LocalInferenceService
from app.models.service import ModelCatalogService

router = APIRouter(tags=["models"])


class ModelSelectionUpdate(BaseModel):
    text_provider: str | None = None
    text_bundle_id: str | None = None
    text_model_name: str | None = None
    vision_provider: str | None = None
    vision_bundle_id: str | None = None
    vision_model_name: str | None = None


class ModelTextSmokeRequest(BaseModel):
    prompt: str


def _get_model_service(request: Request) -> ModelCatalogService:
    context = get_app_context_from_request(request)
    service = context.services.get("models")
    if not isinstance(service, ModelCatalogService):
        raise RuntimeError("Model catalog service not available")
    return service


def _get_runtime_service(request: Request) -> LocalInferenceService:
    context = get_app_context_from_request(request)
    service = context.services.get("model_runtime")
    if not isinstance(service, LocalInferenceService):
        raise RuntimeError("Local inference runtime not available")
    return service


def _runtime_upload_dir(request: Request) -> Path:
    context = get_app_context_from_request(request)
    upload_dir = context.settings.vault_dir / "runtime-vision"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


@router.get("/api/models/catalog")
async def models_catalog(request: Request) -> dict[str, object]:
    return _get_model_service(request).catalog()


@router.get("/api/models/selection")
async def models_selection(request: Request) -> dict[str, object]:
    return _get_model_service(request).current_selection()


@router.get("/api/models/runtime/status")
async def models_runtime_status(request: Request) -> dict[str, object]:
    return _get_runtime_service(request).runtime_status()


@router.post("/api/models/runtime/text")
async def models_runtime_text(request: Request, payload: ModelTextSmokeRequest) -> dict[str, object]:
    return _get_runtime_service(request).smoke_text(payload.prompt)


@router.post("/api/models/runtime/vision")
async def models_runtime_vision(
    request: Request,
    image: UploadFile = File(...),
    prompt: str | None = Form(default=None),
) -> dict[str, object]:
    content_type = str(image.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="image must be an image/* upload")

    suffix = Path(image.filename or "upload.bin").suffix or ".bin"
    temp_path = _runtime_upload_dir(request) / f"{uuid4()}{suffix}"
    data = await image.read()
    temp_path.write_bytes(data)
    try:
        result = _get_runtime_service(request).smoke_vision(str(temp_path), prompt=prompt)
    finally:
        temp_path.unlink(missing_ok=True)
    return result


@router.patch("/api/models/selection")
async def update_models_selection(request: Request, payload: ModelSelectionUpdate) -> dict[str, object]:
    return _get_model_service(request).update_selection(payload.model_dump(exclude_none=True))
