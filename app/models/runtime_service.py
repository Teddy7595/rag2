from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
from pathlib import Path
from typing import Any, cast

from app.models.events import ModelTextGenerationRequest, ModelVisionAnalysisRequest
from app.models.service import ModelCatalogService


def _build_multimodal_chat_handler(mmproj_path: str) -> object:
    chat_format_module = importlib.import_module("llama_cpp.llama_chat_format")
    Llava15ChatHandler = getattr(chat_format_module, "Llava15ChatHandler")

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
    _MIN_GGUF_BYTES = 1024 * 1024

    def __init__(self, catalog_service: ModelCatalogService) -> None:
        self.catalog_service = catalog_service
        self._text_models: dict[str, object] = {}
        self._intent_models: dict[str, object] = {}
        self._vision_models: dict[tuple[str, str], object] = {}
        self._last_text_load_error: str | None = None
        self._last_vision_load_error: str | None = None
        self._last_intent_load_error: str | None = None

    def binding_available(self) -> bool:
        return importlib.util.find_spec("llama_cpp") is not None

    def binding_version(self) -> str | None:
        if not self.binding_available():
            return None
        try:
            return importlib.metadata.version("llama-cpp-python")
        except importlib.metadata.PackageNotFoundError:
            return None

    def runtime_status(self) -> dict[str, object]:
        catalog = cast(dict[str, Any], self.catalog_service.catalog())
        runtime = dict(cast(dict[str, object], catalog["runtime"]))
        runtime["binding_version"] = self.binding_version()
        runtime["models_dir"] = str(self.catalog_service.models_dir)
        runtime["selection"] = catalog["selection"]
        runtime["resolved"] = catalog["resolved"]
        return runtime

    def smoke_text(self, prompt: str) -> dict[str, object]:
        return self.generate_text(
            ModelTextGenerationRequest(
                prompt=prompt,
                temperature=0.25,
                max_tokens=256,
            )
        )

    def classify_intent(
        self,
        prompt: str,
        *,
        bundle_id: str | None = None,
        max_tokens: int = 8,
    ) -> dict[str, object]:
        catalog = cast(dict[str, Any], self.catalog_service.catalog())
        bundle = self.catalog_service.resolve_bundle(bundle_id) if bundle_id else None
        if bundle is None and bundle_id:
            return {
                "ok": False,
                "provider": "local",
                "reason": "bundle_not_found",
                "detail": f"No se encontro el bundle de intencion '{bundle_id}'.",
            }

        if bundle is None:
            selection = cast(dict[str, Any], catalog["resolved"])["text"]
            bundle_id = _coerce_text(selection.get("bundle_id"))
            bundle = self.catalog_service.resolve_bundle(bundle_id) if bundle_id else None

        if not bundle or not bundle.primary_text_artifact:
            return {
                "ok": False,
                "provider": "local",
                "reason": "model_missing",
                "detail": "No hay un bundle de texto disponible para clasificacion de intencion.",
            }

        if not self.binding_available():
            return {
                "ok": False,
                "provider": "local",
                "reason": "binding_unavailable",
                "detail": "llama_cpp no esta instalado o no es visible para el runtime.",
            }

        model_file_check = self._validate_local_gguf(str(bundle.primary_text_artifact.relative_path), label="modelo de intencion")
        if model_file_check is not None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "model_invalid",
                "detail": model_file_check,
                "bundle_id": bundle.bundle_id,
                "model_path": bundle.primary_text_artifact.relative_path,
            }

        self._last_intent_load_error = None
        llm = self._load_intent_model(bundle.primary_text_artifact.relative_path)
        if llm is None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "load_failed",
                "detail": self._last_intent_load_error or "No se pudo cargar el modelo local de intencion.",
                "bundle_id": bundle.bundle_id,
                "model_path": bundle.primary_text_artifact.relative_path,
            }

        instruction = (
            "Clasifica la intención del usuario y devuelve SOLO una etiqueta de esta lista: "
            "greeting, identity, conversational, technical, mixed. "
            "No expliques nada, no uses puntuación extra y responde con una sola palabra.\n\n"
            f"Texto: {prompt}\n"
            "Etiqueta:"
        )

        try:
            response = cast(Any, llm).create_completion(
                prompt=instruction,
                max_tokens=max(4, min(16, int(max_tokens))),
                temperature=0.0,
                top_p=0.2,
                stop=["\n", ".", ",", ";", "-", ":"],
                stream=False,
            )
            response_payload = cast(dict[str, Any], response) if isinstance(response, dict) else {}
            choices = cast(list[dict[str, Any]], response_payload.get("choices", []))
            raw_text = ""
            if choices:
                raw_text = str(choices[0].get("text") or "").strip().lower()
            label = next((item for item in ("greeting", "identity", "conversational", "technical", "mixed") if item in raw_text), "")
            if not label and raw_text:
                label = raw_text.split()[0].strip().strip(".,;:")
            return {
                "ok": bool(label),
                "provider": "local",
                "reason": None if label else "empty_response",
                "label": label or None,
                "content": label or raw_text,
                "raw": raw_text,
                "bundle_id": bundle.bundle_id,
                "model_path": bundle.primary_text_artifact.relative_path,
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": "local",
                "reason": "execution_failed",
                "detail": str(exc),
                "bundle_id": bundle.bundle_id,
                "model_path": bundle.primary_text_artifact.relative_path,
            }

    def smoke_vision(self, image_path: str, prompt: str | None = None) -> dict[str, object]:
        return self.analyze_image(
            ModelVisionAnalysisRequest(
                image_path=image_path,
                prompt=prompt or "Describe la imagen en espanol con foco operativo y contextual.",
                max_tokens=256,
            )
        )

    def generate_text(self, request: ModelTextGenerationRequest) -> dict[str, object]:
        catalog = cast(dict[str, Any], self.catalog_service.catalog())
        runtime = cast(dict[str, Any], catalog["runtime"])
        resolved = cast(dict[str, dict[str, Any]], catalog["resolved"])
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

        model_file_check = self._validate_local_gguf(str(model_path), label="modelo de texto")
        if model_file_check is not None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "model_invalid",
                "detail": model_file_check,
                "model_path": model_path,
            }

        self._last_text_load_error = None
        llm = self._load_text_model(str(model_path))
        if llm is None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "load_failed",
                "detail": self._last_text_load_error or "No se pudo cargar el modelo local de texto.",
                "model_path": model_path,
            }

        try:
            response = cast(Any, llm).create_completion(
                prompt=request.prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                stop=["<end_of_turn>", "<|eot_id|>"],
                stream=False,
            )
            response_payload = cast(dict[str, Any], response) if isinstance(response, dict) else {}
            choices = cast(list[dict[str, Any]], response_payload.get("choices", []))
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
        catalog = cast(dict[str, Any], self.catalog_service.catalog())
        runtime = cast(dict[str, Any], catalog["runtime"])
        resolved = cast(dict[str, dict[str, Any]], catalog["resolved"])
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

        model_file_check = self._validate_local_gguf(str(model_path), label="modelo de vision")
        if model_file_check is not None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "model_invalid",
                "detail": model_file_check,
                "model_path": model_path,
                "mmproj_path": mmproj_path,
            }

        mmproj_file_check = self._validate_local_gguf(str(mmproj_path), label="mmproj")
        if mmproj_file_check is not None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "mmproj_invalid",
                "detail": mmproj_file_check,
                "model_path": model_path,
                "mmproj_path": mmproj_path,
            }

        self._last_vision_load_error = None
        llm = self._load_vision_model(str(model_path), str(mmproj_path))
        if llm is None:
            return {
                "ok": False,
                "provider": "local",
                "reason": "load_failed",
                "detail": self._last_vision_load_error or "No se pudo cargar el runtime multimodal local.",
                "model_path": model_path,
                "mmproj_path": mmproj_path,
            }

        try:
            image_uri = Path(request.image_path).resolve().as_uri()
            prompt = request.prompt or (
                "Describe esta imagen en espanol con foco en sujetos, objetos, texto visible, acciones y contexto util."
            )
            response = cast(Any, llm).create_chat_completion(
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
            response_payload = cast(dict[str, Any], response) if isinstance(response, dict) else {}
            choices = cast(list[dict[str, Any]], response_payload.get("choices", []))
            content = ""
            if choices:
                first = choices[0]
                message = cast(dict[str, Any], first.get("message", {}))
                raw_content = message.get("content")
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

    def _load_intent_model(self, relative_model_path: str) -> object | None:
        cached = self._intent_models.get(relative_model_path)
        if cached is not None:
            return cached
        model = self._build_llama_model(relative_model_path, cpu_only=True, n_ctx=1024, n_batch=256)
        if model is not None:
            self._intent_models[relative_model_path] = model
        return model

    def _build_llama_model(
        self,
        relative_model_path: str,
        *,
        cpu_only: bool = False,
        n_ctx: int = 8192,
        n_batch: int = 1024,
    ) -> object | None:
        try:
            llama_module = importlib.import_module("llama_cpp")
            Llama = getattr(llama_module, "Llama")
        except Exception:
            return None

        model_path = str(self.catalog_service.models_dir / relative_model_path)
        attempts: list[str] = []

        profiles: list[dict[str, object]]
        if cpu_only:
            profiles = [
                {
                    "label": "cpu_balanced",
                    "n_ctx": max(512, min(n_ctx, 2048)),
                    "n_gpu_layers": 0,
                    "n_batch": max(32, min(n_batch, 256)),
                    "flash_attn": False,
                },
                {
                    "label": "cpu_lowmem",
                    "n_ctx": 1024,
                    "n_gpu_layers": 0,
                    "n_batch": 64,
                    "flash_attn": False,
                },
            ]
        else:
            profiles = [
                {
                    "label": "gpu_auto",
                    "n_ctx": n_ctx,
                    "n_gpu_layers": -1,
                    "n_batch": n_batch,
                    "flash_attn": True,
                },
                {
                    "label": "gpu_partial",
                    "n_ctx": max(1024, min(n_ctx, 4096)),
                    "n_gpu_layers": 24,
                    "n_batch": max(64, min(n_batch, 512)),
                    "flash_attn": True,
                },
                {
                    "label": "cpu_fallback",
                    "n_ctx": max(1024, min(n_ctx, 4096)),
                    "n_gpu_layers": 0,
                    "n_batch": max(32, min(n_batch, 256)),
                    "flash_attn": False,
                },
                {
                    "label": "cpu_lowmem",
                    "n_ctx": 1024,
                    "n_gpu_layers": 0,
                    "n_batch": 64,
                    "flash_attn": False,
                },
            ]

        for profile in profiles:
            label = str(profile["label"])
            try:
                return Llama(
                    model_path=model_path,
                    n_ctx=int(profile["n_ctx"]),
                    n_gpu_layers=int(profile["n_gpu_layers"]),
                    n_batch=int(profile["n_batch"]),
                    flash_attn=bool(profile["flash_attn"]),
                    use_mmap=True,
                    verbose=False,
                )
            except Exception as exc:
                attempts.append(f"{label}: {exc}")

        if attempts:
            self._last_text_load_error = (
                "No se pudo cargar el modelo local tras varios perfiles de carga. "
                + " | ".join(attempts)
            )
        return None

    def _build_llava_model(self, relative_model_path: str, relative_mmproj_path: str) -> object | None:
        try:
            llama_module = importlib.import_module("llama_cpp")
            Llama = getattr(llama_module, "Llama")
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
        except Exception as exc:
            self._last_vision_load_error = str(exc)
            return None

    def _validate_local_gguf(self, relative_model_path: str, *, label: str) -> str | None:
        full_path = self.catalog_service.models_dir / relative_model_path
        if not full_path.exists():
            return f"No existe el {label} en ruta local: {full_path}"
        if not full_path.is_file():
            return f"La ruta del {label} no es un archivo: {full_path}"
        try:
            size_bytes = full_path.stat().st_size
        except OSError as exc:
            return f"No se pudo leer el {label}: {exc}"

        if size_bytes < self._MIN_GGUF_BYTES:
            return (
                f"El {label} parece invalido/truncado ({size_bytes} bytes) en {full_path}. "
                "Verifica que la descarga GGUF este completa."
            )
        return None
