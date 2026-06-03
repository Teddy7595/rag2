from __future__ import annotations

from dataclasses import dataclass

from app.core.events import EventChannel, EventKind, EventSpec


@dataclass(frozen=True)
class ModelTextGenerationRequest:
    prompt: str
    temperature: float = 0.35
    top_p: float = 1.0
    max_tokens: int = 768


@dataclass(frozen=True)
class ModelVisionAnalysisRequest:
    image_path: str
    prompt: str | None = None
    max_tokens: int = 768
    system_prompt: str | None = None


@dataclass(frozen=True)
class ModelGenerationDefaultsRequest:
    pass


REQUEST_MODEL_TEXT_GENERATION = EventSpec[ModelTextGenerationRequest, dict](
    name="models.text.generation.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=ModelTextGenerationRequest,
    output_type=dict,
)

REQUEST_MODEL_VISION_ANALYSIS = EventSpec[ModelVisionAnalysisRequest, dict](
    name="models.vision.analysis.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=ModelVisionAnalysisRequest,
    output_type=dict,
)

REQUEST_MODEL_GENERATION_DEFAULTS = EventSpec[ModelGenerationDefaultsRequest, dict](
    name="models.generation.defaults.request",
    kind=EventKind.REQUEST,
    channel=EventChannel.DOMAIN,
    input_type=ModelGenerationDefaultsRequest,
    output_type=dict,
)


__all__ = [
    "ModelTextGenerationRequest",
    "ModelVisionAnalysisRequest",
    "ModelGenerationDefaultsRequest",
    "REQUEST_MODEL_GENERATION_DEFAULTS",
    "REQUEST_MODEL_TEXT_GENERATION",
    "REQUEST_MODEL_VISION_ANALYSIS",
]
