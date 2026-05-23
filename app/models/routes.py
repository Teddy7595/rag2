from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Request

from app.core.app_context import get_app_context_from_request
from app.models.service import ModelCatalogService

router = APIRouter(tags=["models"])


class ModelSelectionUpdate(BaseModel):
    text_provider: str | None = None
    text_bundle_id: str | None = None
    text_model_name: str | None = None
    vision_provider: str | None = None
    vision_bundle_id: str | None = None
    vision_model_name: str | None = None


def _get_model_service(request: Request) -> ModelCatalogService:
    context = get_app_context_from_request(request)
    service = context.services.get("models")
    if not isinstance(service, ModelCatalogService):
        raise RuntimeError("Model catalog service not available")
    return service


@router.get("/api/models/catalog")
async def models_catalog(request: Request) -> dict[str, object]:
    return _get_model_service(request).catalog()


@router.get("/api/models/selection")
async def models_selection(request: Request) -> dict[str, object]:
    return _get_model_service(request).current_selection()


@router.patch("/api/models/selection")
async def update_models_selection(request: Request, payload: ModelSelectionUpdate) -> dict[str, object]:
    return _get_model_service(request).update_selection(payload.model_dump(exclude_none=True))
