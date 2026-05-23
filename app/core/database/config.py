from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.settings import AppSettings


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


def normalize_database_url(database_url: str) -> str:
    normalized = database_url.strip()
    if normalized.startswith("postgresql://"):
        return normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    if normalized.startswith("postgres://"):
        return normalized.replace("postgres://", "postgresql+psycopg://", 1)
    return normalized


def _build_sqlite_url(sqlite_path: Path) -> str:
    resolved_path = sqlite_path.expanduser().resolve()
    return f"sqlite+pysqlite:///{resolved_path}"


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    echo: bool
    create_schema_on_start: bool
    pool_size: int
    max_overflow: int
    pool_timeout: int

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")


def load_database_settings(app_settings: AppSettings) -> DatabaseSettings:
    raw_database_url = (app_settings.database_url or "").strip()
    if raw_database_url:
        url = normalize_database_url(raw_database_url)
    else:
        url = _build_sqlite_url(app_settings.vault_dir / "rag2.sqlite3")

    return DatabaseSettings(
        url=url,
        echo=_read_bool_env("DATABASE_ECHO", default=False),
        create_schema_on_start=_read_bool_env("DATABASE_CREATE_SCHEMA_ON_START", default=True),
        pool_size=max(1, _read_int_env("DATABASE_POOL_SIZE", 5)),
        max_overflow=max(0, _read_int_env("DATABASE_MAX_OVERFLOW", 10)),
        pool_timeout=max(1, _read_int_env("DATABASE_POOL_TIMEOUT", 30)),
    )