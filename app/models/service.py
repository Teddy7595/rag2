from __future__ import annotations

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
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.models_dir = settings.ai_model_dir
        self.selection_path = settings.vault_dir / "model-selection.json"
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def catalog(self) -> dict[str, object]:
        bundles = self.discover_bundles()
        selection = self.load_selection(bundles)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "models_dir": str(self.models_dir),
            "summary": self._build_summary(bundles),
            "providers": self._build_provider_overview(),
            "selection": selection,
            "resolved": self._resolve_selection(selection, bundles),
            "bundles": [bundle.as_dict() for bundle in bundles],
        }

    def current_selection(self) -> dict[str, object]:
        return self.load_selection(self.discover_bundles())

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
            bundle_id = file_path.relative_to(self.models_dir).parent.as_posix()
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
        return {
            "bundle_count": len(bundles),
            "selectable_bundle_count": len(selectable_bundles),
            "text_bundle_count": len(text_bundles),
            "vision_bundle_count": len(vision_bundles),
            "projector_count": projector_count,
        }

    def _build_provider_overview(self) -> dict[str, object]:
        return {
            "text": {
                "configured_provider": _normalize_provider(_read_env("LLM_PROVIDER", "local"), "local"),
                "supported_providers": list(_TEXT_PROVIDER_OPTIONS),
                "lmstudio_base_url": _read_env("LMSTUDIO_BASE_URL", "http://localhost:8000"),
                "lmstudio_model": _coerce_text(_read_env("LMSTUDIO_MODEL")),
                "lmstudio_n_ctx": int(_read_env("LMSTUDIO_N_CTX", "32768") or "32768"),
            },
            "vision": {
                "configured_provider": _normalize_provider(_read_env("VISION_PROVIDER", "local"), "local"),
                "supported_providers": list(_VISION_PROVIDER_OPTIONS),
                "ollama_base_url": _read_env("VISION_OLLAMA_BASE_URL", "http://localhost:11434"),
                "ollama_model": _read_env("VISION_OLLAMA_MODEL", "llava"),
                "lmstudio_base_url": _read_env("VISION_LMSTUDIO_BASE_URL", _read_env("LMSTUDIO_BASE_URL", "http://localhost:8000")),
                "lmstudio_model": _coerce_text(_read_env("VISION_LMSTUDIO_MODEL") or _read_env("LMSTUDIO_MODEL")),
                "timeout_seconds": max(5, int(_read_env("VISION_TIMEOUT_SECONDS", "120") or "120")),
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
            selection["text_model_name"] = _coerce_text(_read_env("LMSTUDIO_MODEL"))

        if vision_provider == "local":
            selection["vision_bundle_id"] = self._first_bundle_id(bundles, require_vision=True)
        elif vision_provider == "ollama":
            selection["vision_model_name"] = _coerce_text(_read_env("VISION_OLLAMA_MODEL", "llava"))
        elif vision_provider == "lmstudio":
            selection["vision_model_name"] = _coerce_text(_read_env("VISION_LMSTUDIO_MODEL") or _read_env("LMSTUDIO_MODEL"))

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
                text_model_name = _coerce_text(_read_env("LMSTUDIO_MODEL"))
        else:
            text_provider = "local" if self._first_bundle_id(bundles, require_vision=False) else "lmstudio"
            if text_provider == "local":
                text_bundle_id = self._first_bundle_id(bundles, require_vision=False)
                text_model_name = None
            else:
                text_bundle_id = None
                text_model_name = _coerce_text(_read_env("LMSTUDIO_MODEL"))

        if vision_provider == "local":
            vision_bundle = bundle_lookup.get(vision_bundle_id or "")
            if not vision_bundle or not vision_bundle.supports_vision or vision_bundle.is_embedding_cache:
                vision_bundle_id = self._first_bundle_id(bundles, require_vision=True)
            vision_model_name = None
        elif vision_provider == "ollama":
            vision_bundle_id = None
            if not vision_model_name:
                vision_model_name = _coerce_text(_read_env("VISION_OLLAMA_MODEL", "llava"))
        elif vision_provider == "lmstudio":
            vision_bundle_id = None
            if not vision_model_name:
                vision_model_name = _coerce_text(_read_env("VISION_LMSTUDIO_MODEL") or _read_env("LMSTUDIO_MODEL"))
        else:
            vision_provider = "local" if self._first_bundle_id(bundles, require_vision=True) else "ollama"
            if vision_provider == "local":
                vision_bundle_id = self._first_bundle_id(bundles, require_vision=True)
                vision_model_name = None
            else:
                vision_bundle_id = None
                vision_model_name = _coerce_text(_read_env("VISION_OLLAMA_MODEL", "llava"))

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

    def _bundle_display_name(self, bundle_id: str) -> str:
        if bundle_id in {"", "."}:
            return self.models_dir.name
        return bundle_id.split("/")[-1]

    def _is_projector_file(self, file_name: str) -> bool:
        lowered = file_name.lower()
        return any(marker in lowered for marker in ("mmproj", "mm-proj", "projector"))