from __future__ import annotations

from pathlib import Path
import json
from uuid import uuid4

from pydantic import BaseModel
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

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


class ModelRuntimeConfigUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model_path: str | None = None
    lmstudio_base_url: str | None = None
    lmstudio_model: str | None = None
    lmstudio_n_ctx: int | None = None
    vision_provider: str | None = None
    vision_model_path: str | None = None
    vision_mm_projector_path: str | None = None
    vision_ollama_base_url: str | None = None
    vision_ollama_model: str | None = None
    vision_lmstudio_base_url: str | None = None
    vision_lmstudio_model: str | None = None
    vision_timeout_seconds: int | None = None
    text_generation_temperature: float | None = None
    text_generation_top_p: float | None = None
    text_generation_max_tokens: int | None = None
    text_generation_min_p: float | None = None
    text_generation_repeat_penalty: float | None = None
    text_generation_presence_penalty: float | None = None
    text_generation_frequency_penalty: float | None = None
    text_generation_seed: int | None = None


class ModelApplyAndRestartRequest(BaseModel):
    selection: ModelSelectionUpdate | None = None
    runtime_config: ModelRuntimeConfigUpdate | None = None
    reason: str | None = "admin_apply"


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


@router.get("/api/models/catalog/validation")
async def models_catalog_validation(request: Request) -> dict[str, object]:
    return _get_model_service(request).validation_report()


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


@router.get("/api/models/runtime-config")
async def models_runtime_config(request: Request) -> dict[str, object]:
    return _get_model_service(request).load_runtime_config()


@router.patch("/api/models/runtime-config")
async def update_models_runtime_config(request: Request, payload: ModelRuntimeConfigUpdate) -> dict[str, object]:
    return _get_model_service(request).update_runtime_config(payload.model_dump(exclude_none=True))


@router.post("/api/models/apply-restart-stream")
async def models_apply_restart_stream(request: Request, payload: ModelApplyAndRestartRequest) -> StreamingResponse:
    model_service = _get_model_service(request)
    runtime_service = _get_runtime_service(request)

    async def event_generator():
        yield f"data: {json.dumps({'stage': 'begin', 'detail': 'Aplicando cambios de modelos'})}\n\n"
        try:
            if payload.selection is not None:
                model_service.update_selection(payload.selection.model_dump(exclude_none=True))
                yield f"data: {json.dumps({'stage': 'selection_updated', 'detail': 'Selección de modelos guardada'})}\n\n"

            if payload.runtime_config is not None:
                model_service.update_runtime_config(payload.runtime_config.model_dump(exclude_none=True))
                yield f"data: {json.dumps({'stage': 'runtime_config_updated', 'detail': 'Configuración runtime guardada'})}\n\n"

            restart_report = runtime_service.restart_runtime(reason=str(payload.reason or "admin_apply"))
            for event in restart_report.get("events", []):
                yield f"data: {json.dumps(event)}\n\n"

            catalog = model_service.catalog()
            yield f"data: {json.dumps({'stage': 'done', 'ok': True, 'catalog': catalog})}\n\n"
        except Exception as exc:  # pragma: no cover - defensive path
            yield f"data: {json.dumps({'stage': 'error', 'ok': False, 'detail': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
