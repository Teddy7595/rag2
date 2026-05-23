from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value.strip())
    except ValueError:
        return default


def _read_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _read_list_env(name: str) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if not raw_value:
        return ()

    values: list[str] = []
    for item in raw_value.split(","):
        normalized = item.strip().lower()
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)


def _read_csv_env(name: str) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if not raw_value:
        return ()

    values: list[str] = []
    for item in raw_value.split(","):
        value = item.strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    return Path(value).expanduser().resolve()


def _resolve_mount_path(value: str | None, default: str) -> str:
    mount_path = (value or default).strip()
    if not mount_path:
        mount_path = default
    if not mount_path.startswith("/"):
        mount_path = f"/{mount_path}"
    if mount_path != "/" and mount_path.endswith("/"):
        mount_path = mount_path.rstrip("/")
    return mount_path


def _directory_contains_gguf(directory: Path) -> bool:
    if not directory.exists() or not directory.is_dir():
        return False
    return any(directory.rglob("*.gguf"))


def _resolve_models_dir(project_root: Path) -> Path:
    configured = os.getenv("AI_MODELS_DIR") or os.getenv("AI_MODEL_DIR")
    configured_path = _resolve_path(configured, project_root / "ai_models") if configured else None

    ai_models_path = (project_root / "ai_models").resolve()
    ai_model_path = (project_root / "ai_model").resolve()

    if configured_path and _directory_contains_gguf(configured_path):
        return configured_path

    for candidate in (ai_models_path, ai_model_path):
        if _directory_contains_gguf(candidate):
            return candidate

    if configured_path:
        return configured_path
    if ai_models_path.exists():
        return ai_models_path
    return ai_model_path


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    env_path: Path
    app_name: str
    app_description: str
    app_version: str
    host: str
    port: int
    debug: bool
    admin_local_only: bool
    rate_limit_window_seconds: int
    rate_limit_max_requests: int
    ban_list: tuple[str, ...]
    conversation_guard_enabled: bool
    conversation_sanitize_enabled: bool
    conversation_timeout_enabled: bool
    conversation_telemetry_enabled: bool
    conversation_debug_trace_enabled: bool
    conversation_deadline_scale_percent: int
    conversation_intent_bundle_id: str | None
    conversation_intent_max_tokens: int
    chat_trash_retention_hours: int
    embedding_model_dir: Path
    ai_model_dir: Path
    web_frontend_dir: Path
    web_frontend_mount_path: str
    web_frontend_root_tag: str
    web_frontend_root_id: str
    web_frontend_script_type: str
    web_frontend_styles: tuple[str, ...]
    web_frontend_scripts: tuple[str, ...]
    vault_dir: Path
    database_url: str | None


def load_settings(project_root: Path) -> AppSettings:
    project_root = project_root.resolve()
    env_path = project_root / ".env"
    ai_model_dir = _resolve_models_dir(project_root)
    web_frontend_dir = _resolve_path(os.getenv("WEB_FRONTEND_DIR"), project_root / "frontend" / "dist")
    vault_dir = _resolve_path(os.getenv("VAULT_DIR"), project_root / ".vault")
    embedding_model_dir = _resolve_path(
        os.getenv("APP_EMBEDDING_MODEL_DIR"),
        project_root / "ai_models" / "embeddings" / "BAAI__bge-m3",
    )

    return AppSettings(
        project_root=project_root,
        env_path=env_path,
        app_name=os.getenv("APP_NAME", "RAG2 Modular Monolith").strip() or "RAG2 Modular Monolith",
        app_description=(
            os.getenv("APP_DESCRIPTION", "Modular monolith event-driven scaffold").strip()
            or "Modular monolith event-driven scaffold"
        ),
        app_version=os.getenv("APP_VERSION", "0.1.0").strip() or "0.1.0",
        host=os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=max(1, _read_int_env("APP_PORT", 8000)),
        debug=_read_bool_env("APP_DEBUG", default=False),
        admin_local_only=_read_bool_env("APP_ADMIN_LOCAL_ONLY", default=True),
        rate_limit_window_seconds=max(1, _read_int_env("APP_RATE_LIMIT_WINDOW_SECONDS", 60)),
        rate_limit_max_requests=max(1, _read_int_env("APP_RATE_LIMIT_MAX_REQUESTS", 120)),
        ban_list=_read_list_env("APP_BAN_LIST"),
        conversation_guard_enabled=_read_bool_env("APP_CONVERSATION_GUARD_ENABLED", default=True),
        conversation_sanitize_enabled=_read_bool_env("APP_CONVERSATION_SANITIZE_ENABLED", default=True),
        conversation_timeout_enabled=_read_bool_env("APP_CONVERSATION_TIMEOUT_ENABLED", default=True),
        conversation_telemetry_enabled=_read_bool_env("APP_CONVERSATION_TELEMETRY_ENABLED", default=True),
        conversation_debug_trace_enabled=_read_bool_env("APP_CONVERSATION_DEBUG_TRACE_ENABLED", default=False),
        conversation_deadline_scale_percent=max(10, min(500, _read_int_env("APP_CONVERSATION_DEADLINE_SCALE_PERCENT", 100))),
        conversation_intent_bundle_id=(_read_env("APP_CONVERSATION_INTENT_BUNDLE_ID", "") or None),
        conversation_intent_max_tokens=max(4, min(16, _read_int_env("APP_CONVERSATION_INTENT_MAX_TOKENS", 8))),
        chat_trash_retention_hours=max(1, min(168, _read_int_env("APP_CHAT_TRASH_RETENTION_HOURS", 24))),
        embedding_model_dir=embedding_model_dir,
        ai_model_dir=ai_model_dir,
        web_frontend_dir=web_frontend_dir,
        web_frontend_mount_path=_resolve_mount_path(os.getenv("WEB_FRONTEND_MOUNT_PATH"), "/ui-assets"),
        web_frontend_root_tag=os.getenv("WEB_FRONTEND_ROOT_TAG", "div").strip() or "div",
        web_frontend_root_id=os.getenv("WEB_FRONTEND_ROOT_ID", "app").strip() or "app",
        web_frontend_script_type=os.getenv("WEB_FRONTEND_SCRIPT_TYPE", "module").strip() or "module",
        web_frontend_styles=_read_csv_env("WEB_FRONTEND_STYLES"),
        web_frontend_scripts=_read_csv_env("WEB_FRONTEND_SCRIPTS"),
        vault_dir=vault_dir,
        database_url=os.getenv("DATABASE_URL") or None,
    )


def ensure_runtime_directories(settings: AppSettings) -> None:
    settings.ai_model_dir.mkdir(parents=True, exist_ok=True)
    settings.vault_dir.mkdir(parents=True, exist_ok=True)
    (settings.vault_dir / "public").mkdir(parents=True, exist_ok=True)
    (settings.vault_dir / "uploads").mkdir(parents=True, exist_ok=True)