from __future__ import annotations

import re
from typing import Any, cast

import httpx

from app.models.events import ModelTextGenerationRequest
from app.models.service import ModelCatalogService

# Con think:true, Ollama separa el razonamiento en message.thinking y deja
# message.content limpio -- este regex es una red de seguridad por si algun
# modelo/backend igual filtra el bloque de pensamiento dentro de content.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class OllamaInferenceService:
    """Cliente HTTP sincrono contra un servidor `ollama serve` externo.

    Ollama aplica su propia plantilla de chat server-side (via el Modelfile del
    modelo), asi que basta con enviar los mensajes y dejar que el servidor los
    formatee -- a diferencia del runtime local, aqui no hace falta chat_template.py.
    """

    def __init__(self, catalog_service: ModelCatalogService) -> None:
        self.catalog_service = catalog_service

    def _runtime_config(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.catalog_service.load_runtime_config())

    def binding_available(self) -> bool:
        config = self._runtime_config()
        base_url = str(config.get("ollama_base_url") or "").strip()
        if not base_url:
            return False
        try:
            response = httpx.get(f"{base_url}/api/tags", timeout=3.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> dict[str, object]:
        config = self._runtime_config()
        base_url = str(config.get("ollama_base_url") or "").strip()
        if not base_url:
            return {
                "ok": False,
                "provider": "ollama",
                "reason": "config_missing",
                "detail": "No hay ollama_base_url configurada.",
                "models": [],
            }

        try:
            response = httpx.get(f"{base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "ok": False,
                "provider": "ollama",
                "reason": "execution_failed",
                "detail": str(exc),
                "models": [],
            }

        entries = cast(list[dict[str, Any]], body.get("models") or [])
        models = [
            {
                "name": entry.get("name") or entry.get("model"),
                "size": entry.get("size"),
                "modified_at": entry.get("modified_at"),
                "parameter_size": (entry.get("details") or {}).get("parameter_size"),
                "quantization_level": (entry.get("details") or {}).get("quantization_level"),
                "family": (entry.get("details") or {}).get("family"),
                "capabilities": entry.get("capabilities") or [],
            }
            for entry in entries
        ]
        return {
            "ok": True,
            "provider": "ollama",
            "reason": None,
            "models": models,
        }

    def smoke_text(self, prompt: str) -> dict[str, object]:
        return self.generate_text(
            ModelTextGenerationRequest(prompt=prompt, temperature=0.25, max_tokens=256)
        )

    def generate_text(self, request: ModelTextGenerationRequest) -> dict[str, object]:
        config = self._runtime_config()
        base_url = str(config.get("ollama_base_url") or "").strip()
        model = str(config.get("ollama_model") or "").strip()
        timeout_seconds = max(5, int(config.get("ollama_timeout_seconds") or 120))

        if not base_url:
            return {
                "ok": False,
                "provider": "ollama",
                "reason": "config_missing",
                "detail": "No hay ollama_base_url configurada.",
            }
        if not model:
            return {
                "ok": False,
                "provider": "ollama",
                "reason": "model_missing",
                "detail": "No hay ollama_model configurado.",
            }

        min_p = max(0.0, min(1.0, float(config.get("text_generation_min_p") or 0.03)))
        repeat_penalty = max(1.0, min(2.0, float(config.get("text_generation_repeat_penalty") or 1.08)))
        presence_penalty = max(-2.0, min(2.0, float(config.get("text_generation_presence_penalty") or 0.0)))
        frequency_penalty = max(-2.0, min(2.0, float(config.get("text_generation_frequency_penalty") or 0.0)))
        seed = int(config.get("text_generation_seed") or -1)

        options: dict[str, object] = {
            "temperature": request.temperature,
            "top_p": request.top_p,
            "min_p": min_p,
            "repeat_penalty": repeat_penalty,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "num_predict": request.max_tokens,
        }
        if seed >= 0:
            options["seed"] = seed

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": ""},
                {"role": "user", "content": request.prompt},
            ],
            "stream": False,
            "think": True,
            "options": options,
        }

        try:
            response = httpx.post(f"{base_url}/api/chat", json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "ok": False,
                "provider": "ollama",
                "reason": "execution_failed",
                "detail": str(exc),
                "model_path": model,
            }

        message = cast(dict[str, Any], body.get("message") or {})
        content = str(message.get("content") or "").strip()
        content = _THINK_BLOCK_RE.sub("", content).strip()
        return {
            "ok": bool(content),
            "provider": "ollama",
            "reason": None if content else "empty_response",
            "content": content,
            "finish_reason": body.get("done_reason"),
            "model_path": model,
            "chat_template_used": True,
            "chat_template_format": "ollama_server_template",
        }
