from __future__ import annotations

from pathlib import Path
import json
from uuid import uuid4

from pydantic import BaseModel
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.app_context import get_app_context_from_request
from app.knowledge.events import IdentityResolveRequest, REQUEST_KNOWLEDGE_IDENTITY_RESOLVE
from app.models.ollama_service import OllamaInferenceService
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
    llama_cpp_n_ctx: int | None = None
    lmstudio_base_url: str | None = None
    lmstudio_model: str | None = None
    lmstudio_n_ctx: int | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    ollama_timeout_seconds: int | None = None
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


class ModelProfileParams(BaseModel):
    text_generation_temperature: float | None = None
    text_generation_top_p: float | None = None
    text_generation_max_tokens: int | None = None
    text_generation_min_p: float | None = None
    text_generation_repeat_penalty: float | None = None
    text_generation_presence_penalty: float | None = None
    text_generation_frequency_penalty: float | None = None
    text_generation_seed: int | None = None
    llama_cpp_n_ctx: int | None = None
    llama_cpp_n_gpu_layers: int | None = None
    vision_timeout_seconds: int | None = None


class ModelProfileCreate(BaseModel):
    name: str
    kind: str
    params: ModelProfileParams = ModelProfileParams()


class ModelProfileUpdate(BaseModel):
    name: str | None = None
    params: ModelProfileParams | None = None


class ModelProfileAssignRequest(BaseModel):
    kind: str
    bundle_id: str
    profile_id: str | None = None


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


def _get_ollama_runtime_service(request: Request) -> OllamaInferenceService:
    context = get_app_context_from_request(request)
    service = context.services.get("model_runtime_ollama")
    if not isinstance(service, OllamaInferenceService):
        raise RuntimeError("Ollama inference runtime not available")
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


@router.get("/api/models/runtime/ollama/models")
async def models_runtime_ollama_models(request: Request) -> dict[str, object]:
    return _get_ollama_runtime_service(request).list_models()


@router.post("/api/models/runtime/text")
async def models_runtime_text(request: Request, payload: ModelTextSmokeRequest) -> dict[str, object]:
    text_provider = _get_model_service(request).current_selection().get("text_provider")
    if text_provider == "ollama":
        return _get_ollama_runtime_service(request).smoke_text(payload.prompt)
    return _get_runtime_service(request).smoke_text(payload.prompt)


@router.post("/api/models/runtime/vision")
async def models_runtime_vision(
    request: Request,
    image: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    identity_id: str | None = Form(default=None),
) -> dict[str, object]:
    content_type = str(image.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="image must be an image/* upload")

    suffix = Path(image.filename or "upload.bin").suffix or ".bin"
    temp_path = _runtime_upload_dir(request) / f"{uuid4()}{suffix}"
    data = await image.read()
    temp_path.write_bytes(data)

    # Build engram system prompt so the model responds in the character's voice.
    system_prompt: str | None = None
    if identity_id:
        try:
            context = get_app_context_from_request(request)
            identity = context.event_bus.request(
                REQUEST_KNOWLEDGE_IDENTITY_RESOLVE,
                IdentityResolveRequest(raw_text=prompt or "", identity_id=identity_id),
                source_module="models.routes",
            )
            if isinstance(identity, dict):
                parts: list[str] = []
                name = str(identity.get("name") or "").strip()
                meta_rule = str(identity.get("meta_rule") or "").strip()
                behavior_prompt = str(identity.get("behavior_prompt") or "").strip()
                backstory = str(identity.get("backstory") or "").strip()
                if name:
                    parts.append(f"Eres {name}.")
                if meta_rule:
                    parts.append(meta_rule)
                if behavior_prompt:
                    parts.append(behavior_prompt)
                if backstory:
                    parts.append(backstory[:800])
                if parts:
                    system_prompt = "\n".join(parts)
        except Exception:
            pass  # If identity lookup fails, proceed without engram context.

    try:
        result = _get_runtime_service(request).smoke_vision(
            str(temp_path), prompt=prompt, system_prompt=system_prompt
        )
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


@router.get("/api/models/profiles")
async def models_profiles(request: Request) -> dict[str, object]:
    return _get_model_service(request).load_profiles()


@router.post("/api/models/profiles")
async def create_models_profile(request: Request, payload: ModelProfileCreate) -> dict[str, object]:
    return _get_model_service(request).create_profile(payload.model_dump(exclude_none=True))


@router.patch("/api/models/profiles/{profile_id}")
async def update_models_profile(request: Request, profile_id: str, payload: ModelProfileUpdate) -> dict[str, object]:
    model_service = _get_model_service(request)
    result = model_service.update_profile(profile_id, payload.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    kind = str(result.get("kind") or "text")
    assigned_bundle_ids = result.get("assigned_bundle_ids") or []
    restarted = False
    if any(model_service.is_bundle_active(kind, bundle_id) for bundle_id in assigned_bundle_ids):
        _get_runtime_service(request).restart_runtime(reason="profile_updated")
        restarted = True
    return {**result, "restarted": restarted}


@router.delete("/api/models/profiles/{profile_id}")
async def delete_models_profile(request: Request, profile_id: str) -> dict[str, object]:
    deleted = _get_model_service(request).delete_profile(profile_id)
    return {"deleted": deleted, "profile_id": profile_id}


@router.post("/api/models/profiles/assign")
async def assign_models_profile(request: Request, payload: ModelProfileAssignRequest) -> dict[str, object]:
    model_service = _get_model_service(request)
    try:
        result = model_service.set_bundle_profile(payload.kind, payload.bundle_id, payload.profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    restarted = False
    if payload.profile_id is not None and model_service.is_bundle_active(payload.kind, payload.bundle_id):
        _get_runtime_service(request).restart_runtime(reason="profile_assigned")
        restarted = True
    return {**result, "restarted": restarted}


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
