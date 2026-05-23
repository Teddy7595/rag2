from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from app.models.events import ModelTextGenerationRequest, ModelVisionAnalysisRequest
from app.models.service import ModelCatalogService


def _build_multimodal_chat_handler(mmproj_path: str) -> object:
    from llama_cpp.llama_chat_format import Llava15ChatHandler

    class GemmaMultimodalChatHandler(Llava15ChatHandler):
        DEFAULT_SYSTEM_MESSAGE = None
        CHAT_FORMAT = (
            "{% for message in messages %}"
            "{% if message.role == 'user' %}"
            "<start_of_turn>user\n"
            "{% if message.content is string %}{{ message.content }}{% endif %}"
            "{% if message.content is iterable %}"
            "{% for content in message.content %}"
            "{% if content.type == 'image_url' and content.image_url is string %}{{ content.image_url }}\n{% endif %}"
            "{% if content.type == 'image_url' and content.image_url is mapping %}{{ content.image_url.url }}\n{% endif %}"
            "{% endfor %}"
            "{% for content in message.content %}"
            "{% if content.type == 'text' %}{{ content.text }}{% endif %}"
            "{% endfor %}"
            "{% endif %}"
            "<end_of_turn>\n"
            "{% endif %}"
            "{% if message.role == 'assistant' and message.content is not none %}"
            "<start_of_turn>model\n{{ message.content }}<end_of_turn>\n"
            "{% endif %}"
            "{% endfor %}"
            "{% if add_generation_prompt %}<start_of_turn>model\n{% endif %}"
        )

    return GemmaMultimodalChatHandler(clip_model_path=mmproj_path, verbose=False)


class LocalInferenceService:
    def __init__(self, catalog_service: ModelCatalogService) -> None:
        self.catalog_service = catalog_service
        self._text_models: dict[str, object] = {}
        self._vision_models: dict[tuple[str, str], object] = {}

    def binding_available(self) -> bool:
        return importlib.util.find_spec("llama_cpp") is not None

    def generate_text(self, request: ModelTextGenerationRequest) -> dict[str, object]:
        catalog = self.catalog_service.catalog()
        runtime = catalog["runtime"]
        resolved = catalog["resolved"]
        if not self.binding_available():
            return {
                "ok": False,
                "provider": "local",
                "reason": "binding_unavailable",
                "detail": "llama_cpp no esta instalado o no es visible para el runtime.",
            }

        if not runtime["local_text_requested"]:
            return {
                "ok": False,
                "provider": resolved["text"]["provider"],
                "reason": "provider_not_local",
                "detail": "La seleccion de texto actual no apunta a un bundle local.",
            }

        model_path = resolved["text"].get("model_path")
        if not model_path:
            return {
                "ok": False,
                "provider": "local",
                "reason": "model_missing",
                "detail": "No hay modelo GGUF local resuelto para texto.",
            }

        llm = self._load_text_model(str(model_path))
        if llm is None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "load_failed",
                "detail": "No se pudo cargar el modelo local de texto.",
            }

        try:
            response = llm.create_completion(
                prompt=request.prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stop=["<end_of_turn>", "<|eot_id|>"],
                stream=False,
            )
            choices = response.get("choices", []) if isinstance(response, dict) else []
            text = ""
            if choices:
                text = str(choices[0].get("text") or "").strip()
            return {
                "ok": bool(text),
                "provider": "local",
                "reason": None if text else "empty_response",
                "content": text,
                "model_path": model_path,
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": "local",
                "reason": "execution_failed",
                "detail": str(exc),
                "model_path": model_path,
            }

    def analyze_image(self, request: ModelVisionAnalysisRequest) -> dict[str, object]:
        catalog = self.catalog_service.catalog()
        runtime = catalog["runtime"]
        resolved = catalog["resolved"]
        if not self.binding_available():
            return {
                "ok": False,
                "provider": "local",
                "reason": "binding_unavailable",
                "detail": "llama_cpp no esta instalado o no es visible para el runtime.",
            }

        if not runtime["local_vision_requested"]:
            return {
                "ok": False,
                "provider": resolved["vision"]["provider"],
                "reason": "provider_not_local",
                "detail": "La seleccion de vision actual no apunta a un bundle local.",
            }

        model_path = resolved["vision"].get("model_path")
        mmproj_path = resolved["vision"].get("mmproj_path")
        if not model_path or not mmproj_path:
            return {
                "ok": False,
                "provider": "local",
                "reason": "model_missing",
                "detail": "Falta el modelo local o el mmproj para vision.",
            }

        llm = self._load_vision_model(str(model_path), str(mmproj_path))
        if llm is None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "load_failed",
                "detail": "No se pudo cargar el runtime multimodal local.",
            }

        try:
            image_uri = Path(request.image_path).resolve().as_uri()
            prompt = request.prompt or (
                "Describe esta imagen en espanol con foco en sujetos, objetos, texto visible, acciones y contexto util."
            )
            response = llm.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_uri}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=request.max_tokens,
                temperature=0.2,
                stream=False,
            )
            choices = response.get("choices", []) if isinstance(response, dict) else []
            content = ""
            if choices:
                first = choices[0] if isinstance(choices[0], dict) else {}
                message = first.get("message", {}) if isinstance(first, dict) else {}
                raw_content = message.get("content") if isinstance(message, dict) else None
                if isinstance(raw_content, str):
                    content = raw_content.strip()
            return {
                "ok": bool(content),
                "provider": "local",
                "reason": None if content else "empty_response",
                "content": content,
                "model_path": model_path,
                "mmproj_path": mmproj_path,
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": "local",
                "reason": "execution_failed",
                "detail": str(exc),
                "model_path": model_path,
                "mmproj_path": mmproj_path,
            }

    def _load_text_model(self, relative_model_path: str) -> object | None:
        cached = self._text_models.get(relative_model_path)
        if cached is not None:
            return cached
        model = self._build_llama_model(relative_model_path)
        if model is not None:
            self._text_models[relative_model_path] = model
        return model

    def _load_vision_model(self, relative_model_path: str, relative_mmproj_path: str) -> object | None:
        key = (relative_model_path, relative_mmproj_path)
        cached = self._vision_models.get(key)
        if cached is not None:
            return cached
        model = self._build_llava_model(relative_model_path, relative_mmproj_path)
        if model is not None:
            self._vision_models[key] = model
        return model

    def _build_llama_model(self, relative_model_path: str) -> object | None:
        try:
            from llama_cpp import Llama
        except Exception:
            return None

        try:
            return Llama(
                model_path=str(self.catalog_service.models_dir / relative_model_path),
                n_ctx=8192,
                n_gpu_layers=-1,
                n_batch=1024,
                flash_attn=True,
                use_mmap=True,
                verbose=False,
            )
        except Exception:
            return None

    def _build_llava_model(self, relative_model_path: str, relative_mmproj_path: str) -> object | None:
        try:
            from llama_cpp import Llama
        except Exception:
            return None

        try:
            chat_handler = _build_multimodal_chat_handler(str(self.catalog_service.models_dir / relative_mmproj_path))
            return Llama(
                model_path=str(self.catalog_service.models_dir / relative_model_path),
                chat_handler=chat_handler,
                n_ctx=8192,
                n_gpu_layers=-1,
                n_batch=1024,
                flash_attn=True,
                use_mmap=True,
                verbose=False,
            )
        except Exception:
            return None
