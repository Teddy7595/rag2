from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.settings import AppSettings

_PROVIDER_ALIASES = {
    "llama_cpp": "local",
    "llama-cpp": "local",
    "lm_studio": "lmstudio",
    "lm-studio": "lmstudio",
}

_TEXT_PROVIDER_OPTIONS = ("local", "lmstudio")
_VISION_PROVIDER_OPTIONS = ("local", "ollama", "lmstudio")

_RUNTIME_CONFIG_DEFAULTS = {
    "llm_provider": "local",
    "llm_model_path": "",
    "lmstudio_base_url": "http://localhost:8000",
    "lmstudio_model": "",
    "lmstudio_n_ctx": 32768,
    "vision_provider": "local",
    "vision_model_path": "",
    "vision_mm_projector_path": "",
    "vision_ollama_base_url": "http://localhost:11434",
    "vision_ollama_model": "llava",
    "vision_lmstudio_base_url": "http://localhost:8000",
    "vision_lmstudio_model": "",
    "vision_timeout_seconds": 120,
    "text_generation_temperature": 0.35,
    "text_generation_top_p": 1.0,
    "text_generation_max_tokens": 768,
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
        config = dict(_RUNTIME_CONFIG_DEFAULTS)
        config["llm_provider"] = _normalize_provider(_read_env("LLM_PROVIDER", str(config["llm_provider"])), "local")
        config["llm_model_path"] = _read_env("LLM_MODEL_PATH", str(config["llm_model_path"]))
        config["lmstudio_base_url"] = _read_env("LMSTUDIO_BASE_URL", str(config["lmstudio_base_url"]))
        config["lmstudio_model"] = _read_env("LMSTUDIO_MODEL", str(config["lmstudio_model"]))
        config["lmstudio_n_ctx"] = int(_read_env("LMSTUDIO_N_CTX", str(config["lmstudio_n_ctx"])) or config["lmstudio_n_ctx"])
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
        config["vision_timeout_seconds"] = int(
            _read_env("VISION_TIMEOUT_SECONDS", str(config["vision_timeout_seconds"])) or config["vision_timeout_seconds"]
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
        for key, value in patch.items():
            if value is None:
                continue
            selection[key] = value
        selection["source"] = "file"
        selection["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        normalized = self._normalize_selection(selection, bundles)
        self._write_selection(normalized)
        return self.catalog()

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
        text = resolved["text"]
        vision = resolved["vision"]
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
                "lmstudio_n_ctx": int(runtime_config.get("lmstudio_n_ctx") or 32768),
            },
            "vision": {
                "configured_provider": _normalize_provider(_coerce_text(runtime_config.get("vision_provider")) or "local", "local"),
                "supported_providers": list(_VISION_PROVIDER_OPTIONS),
                "ollama_base_url": _coerce_text(runtime_config.get("vision_ollama_base_url")) or "http://localhost:11434",
                "ollama_model": _coerce_text(runtime_config.get("vision_ollama_model")) or "llava",
                "lmstudio_base_url": _coerce_text(runtime_config.get("vision_lmstudio_base_url")) or "http://localhost:8000",
                "lmstudio_model": _coerce_text(runtime_config.get("vision_lmstudio_model")),
                "timeout_seconds": max(5, int(runtime_config.get("vision_timeout_seconds") or 120)),
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
        return loaded

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

    def _load_runtime_config_file(self) -> dict[str, object] | None:
        if not self.runtime_config_path.exists():
            return None
        try:
            loaded = json.loads(self.runtime_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        return loaded

    def _write_runtime_config(self, config: dict[str, object]) -> None:
        self.runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")

    def _normalize_runtime_config(self, config: dict[str, object]) -> dict[str, object]:
        normalized = dict(_RUNTIME_CONFIG_DEFAULTS)
        for key in normalized:
            if key in config:
                normalized[key] = config[key]

        normalized["llm_provider"] = _normalize_provider(_coerce_text(normalized.get("llm_provider")) or "local", "local")
        normalized["vision_provider"] = _normalize_provider(_coerce_text(normalized.get("vision_provider")) or "local", "local")
        normalized["lmstudio_base_url"] = _coerce_text(normalized.get("lmstudio_base_url")) or "http://localhost:8000"
        normalized["lmstudio_model"] = _coerce_text(normalized.get("lmstudio_model")) or ""
        normalized["lmstudio_n_ctx"] = max(512, int(normalized.get("lmstudio_n_ctx") or 32768))
        normalized["vision_ollama_base_url"] = _coerce_text(normalized.get("vision_ollama_base_url")) or "http://localhost:11434"
        normalized["vision_ollama_model"] = _coerce_text(normalized.get("vision_ollama_model")) or "llava"
        normalized["vision_lmstudio_base_url"] = _coerce_text(normalized.get("vision_lmstudio_base_url")) or "http://localhost:8000"
        normalized["vision_lmstudio_model"] = _coerce_text(normalized.get("vision_lmstudio_model")) or ""
        normalized["vision_timeout_seconds"] = max(5, int(normalized.get("vision_timeout_seconds") or 120))
        normalized["llm_model_path"] = _coerce_text(normalized.get("llm_model_path")) or ""
        normalized["vision_model_path"] = _coerce_text(normalized.get("vision_model_path")) or ""
        normalized["vision_mm_projector_path"] = _coerce_text(normalized.get("vision_mm_projector_path")) or ""
        normalized["text_generation_temperature"] = max(0.0, min(2.0, float(normalized.get("text_generation_temperature") or 0.35)))
        normalized["text_generation_top_p"] = max(0.0, min(1.0, float(normalized.get("text_generation_top_p") or 1.0)))
        normalized["text_generation_max_tokens"] = max(64, min(4096, int(normalized.get("text_generation_max_tokens") or 768)))
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
            issues.extend([f"text:{item}" for item in list(text_validation.get("issues") or [])])

        if bundle.supports_vision:
            if projector_artifact is None:
                issues.append("missing_mmproj")
            elif projector_validation and not bool(projector_validation.get("ok")):
                issues.extend([f"mmproj:{item}" for item in list(projector_validation.get("issues") or [])])

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