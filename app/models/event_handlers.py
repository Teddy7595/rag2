from __future__ import annotations

from fastapi import FastAPI

from app.core.app_context import get_app_context_from_app
from app.core.events import EventEnvelope
from app.models.events import (
    REQUEST_MODEL_GENERATION_DEFAULTS,
    REQUEST_MODEL_TEXT_GENERATION,
    REQUEST_MODEL_VISION_ANALYSIS,
)
from app.models.ollama_service import OllamaInferenceService
from app.models.runtime_service import LocalInferenceService
from app.models.service import ModelCatalogService


def register_model_event_handlers(app: FastAPI) -> None:
    context = get_app_context_from_app(app)
    service = context.services.get("model_runtime")
    if not isinstance(service, LocalInferenceService):
        raise RuntimeError("Local inference service not registered")
    ollama_service = context.services.get("model_runtime_ollama")
    if not isinstance(ollama_service, OllamaInferenceService):
        raise RuntimeError("Ollama inference service not registered")
    catalog_service = context.services.get("models")
    if not isinstance(catalog_service, ModelCatalogService):
        raise RuntimeError("Model catalog service not registered")

    def handle_text_generation(envelope: EventEnvelope[object]) -> dict[str, object]:
        selection = catalog_service.current_selection()
        if selection.get("text_provider") == "ollama":
            return ollama_service.generate_text(envelope.payload)
        return service.generate_text(envelope.payload)

    def handle_vision_analysis(envelope: EventEnvelope[object]) -> dict[str, object]:
        return service.analyze_image(envelope.payload)

    def handle_generation_defaults(envelope: EventEnvelope[object]) -> dict[str, object]:
        _ = envelope
        return service.generation_defaults()

    context.event_bus.subscribe_request(REQUEST_MODEL_TEXT_GENERATION, handle_text_generation)
    context.event_bus.subscribe_request(REQUEST_MODEL_VISION_ANALYSIS, handle_vision_analysis)
    context.event_bus.subscribe_request(REQUEST_MODEL_GENERATION_DEFAULTS, handle_generation_defaults)
