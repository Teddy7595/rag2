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


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    return Path(value).expanduser().resolve()


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
    ai_model_dir: Path
    vault_dir: Path
    database_url: str | None


def load_settings(project_root: Path) -> AppSettings:
    project_root = project_root.resolve()
    env_path = project_root / ".env"
    ai_model_dir = _resolve_path(
        os.getenv("AI_MODELS_DIR") or os.getenv("AI_MODEL_DIR"),
        project_root / "ai_models",
    )
    vault_dir = _resolve_path(os.getenv("VAULT_DIR"), project_root / ".vault")

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
        ai_model_dir=ai_model_dir,
        vault_dir=vault_dir,
        database_url=os.getenv("DATABASE_URL") or None,
    )


def ensure_runtime_directories(settings: AppSettings) -> None:
    settings.ai_model_dir.mkdir(parents=True, exist_ok=True)
    settings.vault_dir.mkdir(parents=True, exist_ok=True)
    (settings.vault_dir / "public").mkdir(parents=True, exist_ok=True)
    (settings.vault_dir / "uploads").mkdir(parents=True, exist_ok=True)