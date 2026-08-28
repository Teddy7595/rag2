from __future__ import annotations

import importlib.util
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from app.core.settings import AppSettings

_PROVIDER_ALIASES = {
    "llama_cpp": "local",
    "llama-cpp": "local",
    "ollama": "ollama",
    "lm_studio": "lmstudio",
    "lm-studio": "lmstudio",
}

_TEXT_PROVIDER_OPTIONS = ("local", "lmstudio", "ollama")
_VISION_PROVIDER_OPTIONS = ("local", "ollama", "lmstudio")

_RUNTIME_CONFIG_DEFAULTS: dict[str, str | int | float] = {
    "llm_provider": "local",
    "llm_model_path": "",
    "llama_cpp_n_ctx": 32768,
    "lmstudio_base_url": "http://localhost:8000",
    "lmstudio_model": "",
    "lmstudio_n_ctx": 32768,
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "",
    "ollama_timeout_seconds": 120,
    "vision_provider": "local",
    "vision_model_path": "",
    "vision_mm_projector_path": "",
    "vision_ollama_base_url": "http://localhost:11434",
    "vision_ollama_model": "llava",
    "vision_lmstudio_base_url": "http://localhost:8000",
    "vision_lmstudio_model": "",
    "vision_timeout_seconds": 120,
    "text_generation_temperature": 0.55,
    "text_generation_top_p": 0.97,
    "text_generation_max_tokens": 3072,
    "text_generation_min_p": 0.03,
    "text_generation_repeat_penalty": 1.08,
    "text_generation_presence_penalty": 0.0,
    "text_generation_frequency_penalty": 0.0,
    "text_generation_seed": -1,
    "llama_cpp_n_gpu_layers": -1,
    "rag_query_expansion_enabled": 0,
}

_REMOTE_MODEL_RUNTIME_KEYS: dict[str, dict[str, str]] = {
    "text": {"ollama": "ollama_model", "lmstudio": "lmstudio_model"},
    "vision": {"ollama": "vision_ollama_model", "lmstudio": "vision_lmstudio_model"},
}

_PROFILE_PARAM_KEYS_BY_KIND: dict[str, tuple[str, ...]] = {
    "text": (
        "text_generation_temperature",
        "text_generation_top_p",
        "text_generation_max_tokens",
        "text_generation_min_p",
        "text_generation_repeat_penalty",
        "text_generation_presence_penalty",
        "text_generation_frequency_penalty",
        "text_generation_seed",
        "llama_cpp_n_ctx",
        "llama_cpp_n_gpu_layers",
    ),
    "vision": ("vision_timeout_seconds",),
}


def _read_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _normalize_provider(value: str | None, default: str) -> str:
    normalized = (value or default).strip().lower()
    return _PROVIDER_ALIASES.get(normalized, normalized)


def _human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_runtime_int(value: object, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        if isinstance(value, bool):
            raise TypeError
        if isinstance(value, (int, float, str)):
            result = int(value)
        else:
            raise TypeError
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _coerce_runtime_float(value: object, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        if isinstance(value, bool):
            raise TypeError
        if isinstance(value, (int, float, str)):
            result = float(value)
        else:
            raise TypeError
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


@dataclass(frozen=True)
class ModelArtifact:
    file_name: str
    relative_path: str
    kind: str
    size_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "file_name": self.file_name,
            "relative_path": self.relative_path,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "size_label": _human_size(self.size_bytes),
        }


@dataclass(frozen=True)
class ModelBundle:
    bundle_id: str
    display_name: str
    relative_path: str
    artifacts: tuple[ModelArtifact, ...]
    supports_text: bool
    supports_vision: bool
    is_embedding_cache: bool

    @property
    def primary_text_artifact(self) -> ModelArtifact | None:
        return next((artifact for artifact in self.artifacts if artifact.kind == "text_model"), None)

    @property
    def primary_projector_artifact(self) -> ModelArtifact | None:
        return next((artifact for artifact in self.artifacts if artifact.kind == "vision_projector"), None)

    def as_dict(self) -> dict[str, object]:
        primary_text_artifact = self.primary_text_artifact
        primary_projector_artifact = self.primary_projector_artifact
        return {
            "bundle_id": self.bundle_id,
            "display_name": self.display_name,
            "relative_path": self.relative_path,
            "artifact_count": len(self.artifacts),
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "supports_text": self.supports_text,
            "supports_vision": self.supports_vision,
            "is_embedding_cache": self.is_embedding_cache,
            "selectable": self.supports_text or self.supports_vision,
            "primary_text_path": primary_text_artifact.relative_path if primary_text_artifact else None,
            "primary_projector_path": primary_projector_artifact.relative_path if primary_projector_artifact else None,
        }


class ModelCatalogService:
    _MIN_VALID_GGUF_BYTES = 1024 * 1024

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.models_dir = settings.ai_model_dir
        self.selection_path = settings.vault_dir / "model-selection.json"
        self.runtime_config_path = settings.vault_dir / "model-runtime-config.json"
        self.profiles_path = settings.vault_dir / "model-profiles.json"
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def catalog(self) -> dict[str, object]:
        bundles = self.discover_bundles()
        runtime_config = self.load_runtime_config()
        selection = self.load_selection(bundles)
        resolved = self._resolve_selection(selection, bundles)
        validation = self.validation_report(bundles)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "models_dir": str(self.models_dir),
            "summary": self._build_summary(bundles),
            "providers": self._build_provider_overview(runtime_config),
            "runtime_config": runtime_config,
            "selection": selection,
            "profiles": self.load_profiles(),
            "resolved": resolved,
            "runtime": self._build_runtime_status(selection, resolved, bundles),
            "validation": validation,
            "bundles": [bundle.as_dict() for bundle in bundles],
        }

    def validation_report(self, bundles: tuple[ModelBundle, ...] | None = None) -> dict[str, object]:
        bundles = bundles if bundles is not None else self.discover_bundles()
        report_entries = [self._validate_bundle(bundle) for bundle in bundles if not bundle.is_embedding_cache]

        ready_text = sum(1 for entry in report_entries if bool(entry.get("text_ready")))
        ready_vision = sum(1 for entry in report_entries if bool(entry.get("vision_ready")))
        invalid = sum(1 for entry in report_entries if not bool(entry.get("valid")))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "models_dir": str(self.models_dir),
            "total_bundles": len(report_entries),
            "ready_text_bundle_count": ready_text,
            "ready_vision_bundle_count": ready_vision,
            "invalid_bundle_count": invalid,
            "bundles": report_entries,
        }

    def current_selection(self) -> dict[str, object]:
        return self.load_selection(self.discover_bundles())

    def load_runtime_config(self) -> dict[str, object]:
        config: dict[str, object] = dict(_RUNTIME_CONFIG_DEFAULTS)
        config["llm_provider"] = _normalize_provider(_read_env("LLM_PROVIDER", str(config["llm_provider"])), "local")
        config["llm_model_path"] = _read_env("LLM_MODEL_PATH", str(config["llm_model_path"]))
        config["llama_cpp_n_ctx"] = _coerce_runtime_int(
            _read_env("LLAMA_CPP_N_CTX", str(config["llama_cpp_n_ctx"])),
            int(config["llama_cpp_n_ctx"]) if isinstance(config["llama_cpp_n_ctx"], int) else 32768,
            minimum=512,
        )
        config["lmstudio_base_url"] = _read_env("LMSTUDIO_BASE_URL", str(config["lmstudio_base_url"]))
        config["lmstudio_model"] = _read_env("LMSTUDIO_MODEL", str(config["lmstudio_model"]))
        config["lmstudio_n_ctx"] = _coerce_runtime_int(_read_env("LMSTUDIO_N_CTX", str(config["lmstudio_n_ctx"])), int(config["lmstudio_n_ctx"]) if isinstance(config["lmstudio_n_ctx"], int) else 32768, minimum=512)
        config["ollama_base_url"] = _read_env("OLLAMA_BASE_URL", str(config["ollama_base_url"]))
        config["ollama_model"] = _read_env("OLLAMA_MODEL", str(config["ollama_model"]))
        config["ollama_timeout_seconds"] = _coerce_runtime_int(
            _read_env("OLLAMA_TIMEOUT_SECONDS", str(config["ollama_timeout_seconds"])),
            int(config["ollama_timeout_seconds"]) if isinstance(config["ollama_timeout_seconds"], int) else 120,
            minimum=5,
        )
        config["vision_provider"] = _normalize_provider(_read_env("VISION_PROVIDER", str(config["vision_provider"])), "local")
        config["vision_model_path"] = _read_env("VISION_MODEL_PATH", str(config["vision_model_path"]))
        config["vision_mm_projector_path"] = _read_env("VISION_MM_PROJECTOR_PATH", str(config["vision_mm_projector_path"]))
        config["vision_ollama_base_url"] = _read_env("VISION_OLLAMA_BASE_URL", str(config["vision_ollama_base_url"]))
        config["vision_ollama_model"] = _read_env("VISION_OLLAMA_MODEL", str(config["vision_ollama_model"]))
        config["vision_lmstudio_base_url"] = _read_env(
            "VISION_LMSTUDIO_BASE_URL",
            _read_env("LMSTUDIO_BASE_URL", str(config["vision_lmstudio_base_url"])),
        )
        config["vision_lmstudio_model"] = _read_env(
            "VISION_LMSTUDIO_MODEL",
            _read_env("LMSTUDIO_MODEL", str(config["vision_lmstudio_model"])),
        )
        config["vision_timeout_seconds"] = _coerce_runtime_int(
            _read_env("VISION_TIMEOUT_SECONDS", str(config["vision_timeout_seconds"])),
            int(config["vision_timeout_seconds"]) if isinstance(config["vision_timeout_seconds"], int) else 120,
            minimum=5,
        )
        config["text_generation_min_p"] = _coerce_runtime_float(
            _read_env("TEXT_GENERATION_MIN_P", str(config["text_generation_min_p"])),
            float(config["text_generation_min_p"]) if isinstance(config["text_generation_min_p"], (int, float)) else 0.03,
            minimum=0.0,
            maximum=1.0,
        )
        config["text_generation_repeat_penalty"] = _coerce_runtime_float(
            _read_env("TEXT_GENERATION_REPEAT_PENALTY", str(config["text_generation_repeat_penalty"])),
            float(config["text_generation_repeat_penalty"]) if isinstance(config["text_generation_repeat_penalty"], (int, float)) else 1.08,
            minimum=1.0,
            maximum=2.0,
        )
        config["text_generation_presence_penalty"] = _coerce_runtime_float(
            _read_env("TEXT_GENERATION_PRESENCE_PENALTY", str(config["text_generation_presence_penalty"])),
            float(config["text_generation_presence_penalty"]) if isinstance(config["text_generation_presence_penalty"], (int, float)) else 0.0,
            minimum=-2.0,
            maximum=2.0,
        )
        config["text_generation_frequency_penalty"] = _coerce_runtime_float(
            _read_env("TEXT_GENERATION_FREQUENCY_PENALTY", str(config["text_generation_frequency_penalty"])),
            float(config["text_generation_frequency_penalty"]) if isinstance(config["text_generation_frequency_penalty"], (int, float)) else 0.0,
            minimum=-2.0,
            maximum=2.0,
        )
        config["text_generation_seed"] = _coerce_runtime_int(
            _read_env("TEXT_GENERATION_SEED", str(config["text_generation_seed"])),
            int(config["text_generation_seed"]) if isinstance(config["text_generation_seed"], int) else -1,
        )

        file_payload = self._load_runtime_config_file()
        if file_payload:
            for key, value in file_payload.items():
                if key in config:
                    config[key] = value

        return self._normalize_runtime_config(config)

    def update_runtime_config(self, patch: dict[str, object]) -> dict[str, object]:
        current = self.load_runtime_config()
        for key, value in patch.items():
            if key not in _RUNTIME_CONFIG_DEFAULTS:
                continue
            current[key] = value
        normalized = self._normalize_runtime_config(current)
        self._write_runtime_config(normalized)
        return normalized

    def resolve_bundle(self, bundle_id: str | None) -> ModelBundle | None:
        normalized = _coerce_text(bundle_id)
        if not normalized:
            return None
        return next((bundle for bundle in self.discover_bundles() if bundle.bundle_id == normalized), None)

    def update_selection(self, patch: dict[str, object]) -> dict[str, object]:
        bundles = self.discover_bundles()
        selection = self.load_selection(bundles)
        previous_text_bundle_id = selection.get("text_bundle_id")
        previous_vision_bundle_id = selection.get("vision_bundle_id")
        for key, value in patch.items():
            if value is None:
                continue
            selection[key] = value
        selection["source"] = "file"
        selection["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        normalized = self._normalize_selection(selection, bundles)
        self._write_selection(normalized)
        self._apply_bundle_profile_if_changed("text", previous_text_bundle_id, normalized)
        self._apply_bundle_profile_if_changed("vision", previous_vision_bundle_id, normalized)
        self._sync_remote_model_name_to_runtime_config("text", normalized)
        self._sync_remote_model_name_to_runtime_config("vision", normalized)
        return self.catalog()

    def _sync_remote_model_name_to_runtime_config(self, kind: str, selection: dict[str, object]) -> None:
        """Local bundle selection already propagates to the runtime config via
        assigned profiles (`_apply_bundle_profile_if_changed`); ollama/lmstudio
        selection did not, so `generate_text` kept using whatever model name
        was last set directly on the runtime config instead of the one picked
        here, silently failing generation when they drifted apart."""
        provider = str(selection.get(f"{kind}_provider") or "")
        runtime_key = _REMOTE_MODEL_RUNTIME_KEYS.get(kind, {}).get(provider)
        if not runtime_key:
            return
        model_name = _coerce_text(selection.get(f"{kind}_model_name"))
        if not model_name:
            return
        self.update_runtime_config({runtime_key: model_name})

    def is_bundle_active(self, kind: str, bundle_id: str) -> bool:
        bundles = self.discover_bundles()
        selection = self.load_selection(bundles)
        return selection.get(f"{kind}_provider") == "local" and selection.get(f"{kind}_bundle_id") == bundle_id

    def _apply_profile_to_runtime_config(self, kind: str, bundle_id: str) -> bool:
        profile = self.resolve_profile_for_bundle(kind, bundle_id)
        if profile is None:
            return False
        self.update_runtime_config(cast(dict[str, object], profile["params"]))
        return True

    def _apply_bundle_profile_if_changed(
        self,
        kind: str,
        previous_bundle_id: object,
        normalized_selection: dict[str, object],
    ) -> None:
        provider = normalized_selection.get(f"{kind}_provider")
        new_bundle_id = normalized_selection.get(f"{kind}_bundle_id")
        if provider != "local" or not new_bundle_id or new_bundle_id == previous_bundle_id:
            return
        self._apply_profile_to_runtime_config(kind, str(new_bundle_id))

    def discover_bundles(self) -> tuple[ModelBundle, ...]:
        if not self.models_dir.exists():
            return ()

        bundle_map: dict[str, list[Path]] = {}
        for file_path in sorted(self.models_dir.rglob("*.gguf")):
            if not file_path.is_file():
                continue
            bundle_id = self._bundle_id_for(file_path)
            bundle_map.setdefault(bundle_id, []).append(file_path)

        bundles: list[ModelBundle] = []
        for bundle_id, files in sorted(bundle_map.items()):
            artifacts = tuple(self._build_artifact(file_path) for file_path in sorted(files))
            supports_text = any(artifact.kind == "text_model" for artifact in artifacts)
            supports_vision = supports_text and any(artifact.kind == "vision_projector" for artifact in artifacts)
            display_name = self._bundle_display_name(bundle_id)
            is_embedding_cache = bundle_id.startswith("embeddings/") or bundle_id == "embeddings"
            bundles.append(
                ModelBundle(
                    bundle_id=bundle_id,
                    display_name=display_name,
                    relative_path=bundle_id,
                    artifacts=artifacts,
                    supports_text=supports_text,
                    supports_vision=supports_vision,
                    is_embedding_cache=is_embedding_cache,
                )
            )
        return tuple(bundles)

    def load_selection(self, bundles: tuple[ModelBundle, ...]) -> dict[str, object]:
        selection = self._load_selection_file() or self._build_default_selection(bundles)
        return self._normalize_selection(selection, bundles)

    def _build_summary(self, bundles: tuple[ModelBundle, ...]) -> dict[str, int]:
        selectable_bundles = [bundle for bundle in bundles if not bundle.is_embedding_cache and (bundle.supports_text or bundle.supports_vision)]
        text_bundles = [bundle for bundle in bundles if bundle.supports_text and not bundle.is_embedding_cache]
        vision_bundles = [bundle for bundle in bundles if bundle.supports_vision and not bundle.is_embedding_cache]
        projector_count = sum(1 for bundle in bundles if bundle.primary_projector_artifact is not None and not bundle.is_embedding_cache)
        root_bundle_count = sum(1 for bundle in bundles if "/" not in bundle.bundle_id and bundle.bundle_id not in {"", "."})
        return {
            "bundle_count": len(bundles),
            "selectable_bundle_count": len(selectable_bundles),
            "text_bundle_count": len(text_bundles),
            "vision_bundle_count": len(vision_bundles),
            "projector_count": projector_count,
            "root_bundle_count": root_bundle_count,
        }

    def _build_runtime_status(
        self,
        selection: dict[str, object],
        resolved: dict[str, object],
        bundles: tuple[ModelBundle, ...],
    ) -> dict[str, object]:
        llama_cpp_available = importlib.util.find_spec("llama_cpp") is not None
        text = cast(dict[str, object], resolved["text"])
        vision = cast(dict[str, object], resolved["vision"])
        local_text_requested = selection.get("text_provider") == "local"
        local_vision_requested = selection.get("vision_provider") == "local"
        local_text_ready = bool(local_text_requested and text.get("model_path") and llama_cpp_available)
        local_vision_ready = bool(local_vision_requested and vision.get("model_path") and vision.get("mmproj_path") and llama_cpp_available)
        return {
            "llama_cpp_binding_available": llama_cpp_available,
            "local_text_requested": local_text_requested,
            "local_vision_requested": local_vision_requested,
            "local_text_ready": local_text_ready,
            "local_vision_ready": local_vision_ready,
            "selected_text_model_path": text.get("model_path"),
            "selected_vision_model_path": vision.get("model_path"),
            "selected_vision_mmproj_path": vision.get("mmproj_path"),
            "flat_file_support": True,
            "nested_bundle_support": True,
            "embedding_cache_support": True,
            "runtime_adapter_status": "wired",
            "runtime_adapter_note": (
                "El servicio de inferencia local ya esta cableado por el modulo models. "
                "Si llama_cpp no esta disponible o faltan paths locales, el chat mantiene el fallback contextual actual."
            ),
            "bundle_count": len(bundles),
        }

    def _build_provider_overview(self, runtime_config: dict[str, object]) -> dict[str, object]:
        return {
            "text": {
                "configured_provider": _normalize_provider(_coerce_text(runtime_config.get("llm_provider")) or "local", "local"),
                "supported_providers": list(_TEXT_PROVIDER_OPTIONS),
                "lmstudio_base_url": _coerce_text(runtime_config.get("lmstudio_base_url")) or "http://localhost:8000",
                "lmstudio_model": _coerce_text(runtime_config.get("lmstudio_model")),
                "lmstudio_n_ctx": _coerce_runtime_int(runtime_config.get("lmstudio_n_ctx"), 32768, minimum=512),
                "ollama_base_url": _coerce_text(runtime_config.get("ollama_base_url")) or "http://localhost:11434",
                "ollama_model": _coerce_text(runtime_config.get("ollama_model")),
                "ollama_timeout_seconds": _coerce_runtime_int(runtime_config.get("ollama_timeout_seconds"), 120, minimum=5),
            },
            "vision": {
                "configured_provider": _normalize_provider(_coerce_text(runtime_config.get("vision_provider")) or "local", "local"),
                "supported_providers": list(_VISION_PROVIDER_OPTIONS),
                "ollama_base_url": _coerce_text(runtime_config.get("vision_ollama_base_url")) or "http://localhost:11434",
                "ollama_model": _coerce_text(runtime_config.get("vision_ollama_model")) or "llava",
                "lmstudio_base_url": _coerce_text(runtime_config.get("vision_lmstudio_base_url")) or "http://localhost:8000",
                "lmstudio_model": _coerce_text(runtime_config.get("vision_lmstudio_model")),
                "timeout_seconds": _coerce_runtime_int(runtime_config.get("vision_timeout_seconds"), 120, minimum=5),
            },
        }

    def _build_artifact(self, file_path: Path) -> ModelArtifact:
        relative_path = file_path.relative_to(self.models_dir).as_posix()
        kind = "vision_projector" if self._is_projector_file(file_path.name) else "text_model"
        return ModelArtifact(
            file_name=file_path.name,
            relative_path=relative_path,
            kind=kind,
            size_bytes=file_path.stat().st_size,
        )

    def _build_default_selection(self, bundles: tuple[ModelBundle, ...]) -> dict[str, object]:
        runtime_config = self.load_runtime_config()
        text_provider = self._default_provider("LLM_PROVIDER", "local", bundles, supports_vision=False)
        vision_provider = self._default_provider("VISION_PROVIDER", "local", bundles, supports_vision=True)

        selection: dict[str, object] = {
            "text_provider": text_provider,
            "text_bundle_id": None,
            "text_model_name": None,
            "vision_provider": vision_provider,
            "vision_bundle_id": None,
            "vision_model_name": None,
            "source": "env",
            "updated_at": None,
        }

        if text_provider == "local":
            selection["text_bundle_id"] = self._first_bundle_id(bundles, require_vision=False)
        elif text_provider == "lmstudio":
            selection["text_model_name"] = _coerce_text(runtime_config.get("lmstudio_model"))
        elif text_provider == "ollama":
            selection["text_model_name"] = _coerce_text(runtime_config.get("ollama_model"))

        if vision_provider == "local":
            selection["vision_bundle_id"] = self._first_bundle_id(bundles, require_vision=True)
        elif vision_provider == "ollama":
            selection["vision_model_name"] = _coerce_text(runtime_config.get("vision_ollama_model")) or "llava"
        elif vision_provider == "lmstudio":
            selection["vision_model_name"] = _coerce_text(runtime_config.get("vision_lmstudio_model") or runtime_config.get("lmstudio_model"))

        return self._normalize_selection(selection, bundles)

    def _default_provider(self, env_name: str, fallback: str, bundles: tuple[ModelBundle, ...], *, supports_vision: bool) -> str:
        configured_provider = _normalize_provider(_read_env(env_name, fallback), fallback)
        if configured_provider != "auto":
            return configured_provider
        if supports_vision:
            return "local" if self._first_bundle_id(bundles, require_vision=True) else "ollama"
        return "local" if self._first_bundle_id(bundles, require_vision=False) else "lmstudio"

    def _first_bundle_id(self, bundles: tuple[ModelBundle, ...], *, require_vision: bool) -> str | None:
        for bundle in bundles:
            if bundle.is_embedding_cache:
                continue
            if require_vision and not bundle.supports_vision:
                continue
            if not require_vision and not bundle.supports_text:
                continue
            return bundle.bundle_id
        return None

    def _load_selection_file(self) -> dict[str, object] | None:
        if not self.selection_path.exists():
            return None
        try:
            loaded = json.loads(self.selection_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        return cast(dict[str, object], loaded)

    def _normalize_selection(self, selection: dict[str, object], bundles: tuple[ModelBundle, ...]) -> dict[str, object]:
        bundle_lookup = {bundle.bundle_id: bundle for bundle in bundles}
        runtime_config = self.load_runtime_config()

        text_provider = _normalize_provider(_coerce_text(selection.get("text_provider")) or "local", "local")
        vision_provider = _normalize_provider(_coerce_text(selection.get("vision_provider")) or "local", "local")

        text_bundle_id = _coerce_text(selection.get("text_bundle_id"))
        text_model_name = _coerce_text(selection.get("text_model_name"))
        vision_bundle_id = _coerce_text(selection.get("vision_bundle_id"))
        vision_model_name = _coerce_text(selection.get("vision_model_name"))

        if text_provider == "local":
            text_bundle = bundle_lookup.get(text_bundle_id or "")
            if not text_bundle or not text_bundle.supports_text or text_bundle.is_embedding_cache:
                text_bundle_id = self._first_bundle_id(bundles, require_vision=False)
            text_model_name = None
        elif text_provider == "lmstudio":
            text_bundle_id = None
            if not text_model_name:
                text_model_name = _coerce_text(runtime_config.get("lmstudio_model"))
        elif text_provider == "ollama":
            text_bundle_id = None
            if not text_model_name:
                text_model_name = _coerce_text(runtime_config.get("ollama_model"))
        else:
            text_provider = "local" if self._first_bundle_id(bundles, require_vision=False) else "lmstudio"
            if text_provider == "local":
                text_bundle_id = self._first_bundle_id(bundles, require_vision=False)
                text_model_name = None
            else:
                text_bundle_id = None
                text_model_name = _coerce_text(runtime_config.get("lmstudio_model"))

        if vision_provider == "local":
            vision_bundle = bundle_lookup.get(vision_bundle_id or "")
            if not vision_bundle or not vision_bundle.supports_vision or vision_bundle.is_embedding_cache:
                vision_bundle_id = self._first_bundle_id(bundles, require_vision=True)
            vision_model_name = None
        elif vision_provider == "ollama":
            vision_bundle_id = None
            if not vision_model_name:
                vision_model_name = _coerce_text(runtime_config.get("vision_ollama_model")) or "llava"
        elif vision_provider == "lmstudio":
            vision_bundle_id = None
            if not vision_model_name:
                vision_model_name = _coerce_text(runtime_config.get("vision_lmstudio_model") or runtime_config.get("lmstudio_model"))
        else:
            vision_provider = "local" if self._first_bundle_id(bundles, require_vision=True) else "ollama"
            if vision_provider == "local":
                vision_bundle_id = self._first_bundle_id(bundles, require_vision=True)
                vision_model_name = None
            else:
                vision_bundle_id = None
                vision_model_name = _coerce_text(runtime_config.get("vision_ollama_model")) or "llava"

        return {
            "text_provider": text_provider,
            "text_bundle_id": text_bundle_id,
            "text_model_name": text_model_name,
            "vision_provider": vision_provider,
            "vision_bundle_id": vision_bundle_id,
            "vision_model_name": vision_model_name,
            "source": _coerce_text(selection.get("source")) or "env",
            "updated_at": _coerce_text(selection.get("updated_at")),
        }

    def _resolve_selection(self, selection: dict[str, object], bundles: tuple[ModelBundle, ...]) -> dict[str, object]:
        bundle_lookup = {bundle.bundle_id: bundle for bundle in bundles}

        text_bundle = bundle_lookup.get(_coerce_text(selection.get("text_bundle_id")) or "")
        vision_bundle = bundle_lookup.get(_coerce_text(selection.get("vision_bundle_id")) or "")

        return {
            "text": {
                "provider": selection.get("text_provider"),
                "bundle_id": selection.get("text_bundle_id"),
                "model_name": selection.get("text_model_name"),
                "bundle": text_bundle.as_dict() if text_bundle else None,
                "model_path": text_bundle.primary_text_artifact.relative_path if text_bundle and text_bundle.primary_text_artifact else None,
            },
            "vision": {
                "provider": selection.get("vision_provider"),
                "bundle_id": selection.get("vision_bundle_id"),
                "model_name": selection.get("vision_model_name"),
                "bundle": vision_bundle.as_dict() if vision_bundle else None,
                "model_path": vision_bundle.primary_text_artifact.relative_path if vision_bundle and vision_bundle.primary_text_artifact else None,
                "mmproj_path": vision_bundle.primary_projector_artifact.relative_path if vision_bundle and vision_bundle.primary_projector_artifact else None,
            },
        }

    def _write_selection(self, selection: dict[str, object]) -> None:
        self.selection_path.parent.mkdir(parents=True, exist_ok=True)
        self.selection_path.write_text(json.dumps(selection, indent=2, sort_keys=True), encoding="utf-8")

    def load_profiles(self) -> dict[str, object]:
        payload = self._load_profiles_file() or {"profiles": []}
        raw_profiles = payload.get("profiles")
        records = raw_profiles if isinstance(raw_profiles, list) else []
        return {"profiles": [self._normalize_profile(cast(dict[str, object], record)) for record in records if isinstance(record, dict)]}

    def create_profile(self, payload: dict[str, object]) -> dict[str, object]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = dict(payload)
        record["id"] = str(uuid.uuid4())
        record["created_at"] = now
        record["updated_at"] = now
        normalized = self._normalize_profile(record)
        profiles = self.load_profiles()
        profiles["profiles"].append(normalized)
        self._write_profiles_file(profiles)
        return normalized

    def update_profile(self, profile_id: str, patch: dict[str, object]) -> dict[str, object] | None:
        profiles = self.load_profiles()
        records = cast(list[dict[str, object]], profiles["profiles"])
        existing = next((record for record in records if record.get("id") == profile_id), None)
        if existing is None:
            return None
        if "name" in patch and patch["name"] is not None:
            existing["name"] = patch["name"]
        patch_params = patch.get("params")
        if isinstance(patch_params, dict):
            merged_params = dict(cast(dict[str, object], existing.get("params") or {}))
            for key, value in patch_params.items():
                if value is not None:
                    merged_params[key] = value
            existing["params"] = merged_params
        existing["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        normalized = self._normalize_profile(existing)
        records[records.index(existing)] = normalized
        self._write_profiles_file({"profiles": records})
        for assigned_bundle_id in cast(list[str], normalized.get("assigned_bundle_ids") or []):
            if self.is_bundle_active(str(normalized["kind"]), assigned_bundle_id):
                self._apply_profile_to_runtime_config(str(normalized["kind"]), assigned_bundle_id)
        return normalized

    def delete_profile(self, profile_id: str) -> bool:
        profiles = self.load_profiles()
        records = cast(list[dict[str, object]], profiles["profiles"])
        remaining = [record for record in records if record.get("id") != profile_id]
        if len(remaining) == len(records):
            return False
        self._write_profiles_file({"profiles": remaining})
        return True

    def set_bundle_profile(self, kind: str, bundle_id: str, profile_id: str | None) -> dict[str, object]:
        kind = kind if kind in _PROFILE_PARAM_KEYS_BY_KIND else "text"
        profiles = self.load_profiles()
        records = cast(list[dict[str, object]], profiles["profiles"])
        target: dict[str, object] | None = None
        for record in records:
            if record.get("kind") != kind:
                continue
            assigned = cast(list[str], record.get("assigned_bundle_ids") or [])
            if bundle_id in assigned:
                record["assigned_bundle_ids"] = [b for b in assigned if b != bundle_id]
            if profile_id is not None and record.get("id") == profile_id:
                target = record
        if profile_id is not None:
            if target is None:
                raise ValueError(f"Profile '{profile_id}' of kind '{kind}' not found")
            assigned = cast(list[str], target.get("assigned_bundle_ids") or [])
            if bundle_id not in assigned:
                target["assigned_bundle_ids"] = [*assigned, bundle_id]
        self._write_profiles_file({"profiles": records})
        if profile_id is not None and self.is_bundle_active(kind, bundle_id):
            self._apply_profile_to_runtime_config(kind, bundle_id)
        return self.load_profiles()

    def resolve_profile_for_bundle(self, kind: str, bundle_id: str) -> dict[str, object] | None:
        profiles = self.load_profiles()
        for record in cast(list[dict[str, object]], profiles["profiles"]):
            if record.get("kind") == kind and bundle_id in cast(list[str], record.get("assigned_bundle_ids") or []):
                return record
        return None

    def _load_profiles_file(self) -> dict[str, object] | None:
        if not self.profiles_path.exists():
            return None
        try:
            loaded = json.loads(self.profiles_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        return cast(dict[str, object], loaded)

    def _write_profiles_file(self, profiles: dict[str, object]) -> None:
        self.profiles_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles_path.write_text(json.dumps(profiles, indent=2, sort_keys=True), encoding="utf-8")

    def _normalize_profile(self, record: dict[str, object]) -> dict[str, object]:
        kind = _coerce_text(record.get("kind")) or "text"
        if kind not in _PROFILE_PARAM_KEYS_BY_KIND:
            kind = "text"
        allowed_keys = _PROFILE_PARAM_KEYS_BY_KIND[kind]
        raw_params = record.get("params")
        raw_params = raw_params if isinstance(raw_params, dict) else {}
        params = {key: raw_params[key] for key in allowed_keys if key in raw_params}
        normalized_params = self._normalize_profile_params(kind, params)
        assigned_raw = record.get("assigned_bundle_ids")
        assigned_bundle_ids = []
        if isinstance(assigned_raw, list):
            for item in assigned_raw:
                text = _coerce_text(item)
                if text and text not in assigned_bundle_ids:
                    assigned_bundle_ids.append(text)
        return {
            "id": _coerce_text(record.get("id")) or str(uuid.uuid4()),
            "name": _coerce_text(record.get("name")) or "Sin nombre",
            "kind": kind,
            "params": normalized_params,
            "assigned_bundle_ids": assigned_bundle_ids,
            "created_at": _coerce_text(record.get("created_at")),
            "updated_at": _coerce_text(record.get("updated_at")),
        }

    def _normalize_profile_params(self, kind: str, params: dict[str, object]) -> dict[str, object]:
        if kind == "vision":
            return {"vision_timeout_seconds": _coerce_runtime_int(params.get("vision_timeout_seconds"), 120, minimum=5)}
        return {
            "text_generation_temperature": _coerce_runtime_float(params.get("text_generation_temperature"), 0.55, minimum=0.0, maximum=2.0),
            "text_generation_top_p": _coerce_runtime_float(params.get("text_generation_top_p"), 0.97, minimum=0.0, maximum=1.0),
            "text_generation_max_tokens": _coerce_runtime_int(params.get("text_generation_max_tokens"), 3072, minimum=64, maximum=4096),
            "text_generation_min_p": _coerce_runtime_float(params.get("text_generation_min_p"), 0.03, minimum=0.0, maximum=1.0),
            "text_generation_repeat_penalty": _coerce_runtime_float(params.get("text_generation_repeat_penalty"), 1.08, minimum=1.0, maximum=2.0),
            "text_generation_presence_penalty": _coerce_runtime_float(params.get("text_generation_presence_penalty"), 0.0, minimum=-2.0, maximum=2.0),
            "text_generation_frequency_penalty": _coerce_runtime_float(params.get("text_generation_frequency_penalty"), 0.0, minimum=-2.0, maximum=2.0),
            "text_generation_seed": _coerce_runtime_int(params.get("text_generation_seed"), -1),
            "llama_cpp_n_ctx": _coerce_runtime_int(params.get("llama_cpp_n_ctx"), 32768, minimum=512),
            "llama_cpp_n_gpu_layers": _coerce_runtime_int(params.get("llama_cpp_n_gpu_layers"), -1),
        }

    def _load_runtime_config_file(self) -> dict[str, object] | None:
        if not self.runtime_config_path.exists():
            return None
        try:
            loaded = json.loads(self.runtime_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        return cast(dict[str, object], loaded)

    def _write_runtime_config(self, config: dict[str, object]) -> None:
        self.runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _normalize_runtime_config(self, config: dict[str, object]) -> dict[str, object]:
        normalized: dict[str, object] = dict(_RUNTIME_CONFIG_DEFAULTS)
        for key in normalized:
            if key in config:
                normalized[key] = config[key]

        normalized["llm_provider"] = _normalize_provider(_coerce_text(normalized.get("llm_provider")) or "local", "local")
        normalized["vision_provider"] = _normalize_provider(_coerce_text(normalized.get("vision_provider")) or "local", "local")
        normalized["lmstudio_base_url"] = _coerce_text(normalized.get("lmstudio_base_url")) or "http://localhost:8000"
        normalized["lmstudio_model"] = _coerce_text(normalized.get("lmstudio_model")) or ""
        normalized["llama_cpp_n_ctx"] = _coerce_runtime_int(normalized.get("llama_cpp_n_ctx"), 32768, minimum=512)
        normalized["lmstudio_n_ctx"] = _coerce_runtime_int(normalized.get("lmstudio_n_ctx"), 32768, minimum=512)
        normalized["ollama_base_url"] = _coerce_text(normalized.get("ollama_base_url")) or "http://localhost:11434"
        normalized["ollama_model"] = _coerce_text(normalized.get("ollama_model")) or ""
        normalized["ollama_timeout_seconds"] = _coerce_runtime_int(normalized.get("ollama_timeout_seconds"), 120, minimum=5)
        normalized["vision_ollama_base_url"] = _coerce_text(normalized.get("vision_ollama_base_url")) or "http://localhost:11434"
        normalized["vision_ollama_model"] = _coerce_text(normalized.get("vision_ollama_model")) or "llava"
        normalized["vision_lmstudio_base_url"] = _coerce_text(normalized.get("vision_lmstudio_base_url")) or "http://localhost:8000"
        normalized["vision_lmstudio_model"] = _coerce_text(normalized.get("vision_lmstudio_model")) or ""
        normalized["vision_timeout_seconds"] = _coerce_runtime_int(normalized.get("vision_timeout_seconds"), 120, minimum=5)
        normalized["llm_model_path"] = _coerce_text(normalized.get("llm_model_path")) or ""
        normalized["vision_model_path"] = _coerce_text(normalized.get("vision_model_path")) or ""
        normalized["vision_mm_projector_path"] = _coerce_text(normalized.get("vision_mm_projector_path")) or ""
        normalized["text_generation_temperature"] = _coerce_runtime_float(normalized.get("text_generation_temperature"), 0.55, minimum=0.0, maximum=2.0)
        normalized["text_generation_top_p"] = _coerce_runtime_float(normalized.get("text_generation_top_p"), 0.97, minimum=0.0, maximum=1.0)
        normalized["text_generation_max_tokens"] = _coerce_runtime_int(normalized.get("text_generation_max_tokens"), 3072, minimum=64, maximum=4096)
        normalized["text_generation_min_p"] = _coerce_runtime_float(normalized.get("text_generation_min_p"), 0.03, minimum=0.0, maximum=1.0)
        normalized["text_generation_repeat_penalty"] = _coerce_runtime_float(normalized.get("text_generation_repeat_penalty"), 1.08, minimum=1.0, maximum=2.0)
        normalized["text_generation_presence_penalty"] = _coerce_runtime_float(normalized.get("text_generation_presence_penalty"), 0.0, minimum=-2.0, maximum=2.0)
        normalized["text_generation_frequency_penalty"] = _coerce_runtime_float(normalized.get("text_generation_frequency_penalty"), 0.0, minimum=-2.0, maximum=2.0)
        normalized["text_generation_seed"] = _coerce_runtime_int(normalized.get("text_generation_seed"), -1)
        return normalized

    def _bundle_id_for(self, file_path: Path) -> str:
        relative_path = file_path.relative_to(self.models_dir)
        parent = relative_path.parent.as_posix()
        if parent not in {"", "."}:
            return parent

        stem = file_path.stem
        if self._is_projector_file(file_path.name):
            return f"projector/{stem}"
        return stem

    def _bundle_display_name(self, bundle_id: str) -> str:
        if bundle_id in {"", "."}:
            return self.models_dir.name
        return bundle_id.split("/")[-1]

    def _is_projector_file(self, file_name: str) -> bool:
        lowered = file_name.lower()
        return any(marker in lowered for marker in ("mmproj", "mm-proj", "projector"))

    def _validate_bundle(self, bundle: ModelBundle) -> dict[str, object]:
        issues: list[str] = []

        text_artifact = bundle.primary_text_artifact
        projector_artifact = bundle.primary_projector_artifact

        text_validation = self._validate_artifact(text_artifact, label="modelo_texto") if text_artifact else None
        projector_validation = self._validate_artifact(projector_artifact, label="mmproj") if projector_artifact else None

        if text_artifact is None:
            issues.append("missing_text_model")
        elif text_validation and not bool(text_validation.get("ok")):
            text_issues = cast(list[object], text_validation.get("issues") or [])
            issues.extend([f"text:{item}" for item in text_issues])

        if bundle.supports_vision:
            if projector_artifact is None:
                issues.append("missing_mmproj")
            elif projector_validation and not bool(projector_validation.get("ok")):
                projector_issues = cast(list[object], projector_validation.get("issues") or [])
                issues.extend([f"mmproj:{item}" for item in projector_issues])

        text_ready = bool(text_validation and text_validation.get("ok"))
        vision_ready = bool(text_ready and projector_validation and projector_validation.get("ok"))

        return {
            "bundle_id": bundle.bundle_id,
            "display_name": bundle.display_name,
            "valid": not issues,
            "text_ready": text_ready,
            "vision_ready": vision_ready,
            "issues": issues,
            "text_artifact": text_validation,
            "projector_artifact": projector_validation,
        }

    def _validate_artifact(self, artifact: ModelArtifact | None, *, label: str) -> dict[str, object] | None:
        if artifact is None:
            return None

        full_path = self.models_dir / artifact.relative_path
        issues: list[str] = []
        size_bytes = 0
        exists = full_path.exists()
        is_file = full_path.is_file() if exists else False
        header_magic = ""

        if not exists:
            issues.append("missing_file")
        elif not is_file:
            issues.append("not_a_file")
        else:
            try:
                size_bytes = full_path.stat().st_size
            except OSError:
                issues.append("stat_error")

            if size_bytes < self._MIN_VALID_GGUF_BYTES:
                issues.append("too_small")

            try:
                with full_path.open("rb") as handle:
                    header = handle.read(4)
                header_magic = header.decode("ascii", errors="ignore")
                if header != b"GGUF":
                    issues.append("invalid_gguf_header")
            except OSError:
                issues.append("header_read_error")

        return {
            "label": label,
            "relative_path": artifact.relative_path,
            "size_bytes": size_bytes,
            "size_label": _human_size(size_bytes),
            "exists": exists,
            "is_file": is_file,
            "header_magic": header_magic,
            "ok": not issues,
            "issues": issues,
        }