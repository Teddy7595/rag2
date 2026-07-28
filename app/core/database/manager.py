from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database.base import DatabaseBase
from app.core.database.config import DatabaseSettings, load_database_settings
from app.core.settings import AppSettings


@dataclass(frozen=True)
class DatabaseManager:
    settings: DatabaseSettings
    engine: Engine
    session_factory: sessionmaker[Session]

    def create_schema(self) -> None:
        DatabaseBase.metadata.create_all(bind=self.engine)
        self._ensure_legacy_compatibility()

    def _ensure_legacy_compatibility(self) -> None:
        """Apply additive schema upgrades for existing installations.

        Tests use fresh databases so these changes target long-lived local/postgres
        deployments where create_all does not alter existing tables.
        """
        try:
            inspector = inspect(self.engine)
            tables = set(inspector.get_table_names())
            statements: list[str] = []

            # ── interaction_messages: additive upgrades ───────────────────────
            if "interaction_messages" in tables:
                columns = {str(c.get("name") or "") for c in inspector.get_columns("interaction_messages")}
                if "session_id" not in columns:
                    statements.append("ALTER TABLE interaction_messages ADD COLUMN session_id VARCHAR(64)")

            # ── knowledge_engrams: drop removed identity fields ───────────────
            # These columns were removed from the domain model and ORM. Dropping
            # them keeps the schema in sync and avoids dead storage.
            _ENGRAM_DEAD_COLUMNS = (
                "moral_threshold",
                "interaction_mode",
                "temperatura_base",
                "top_p_base",
                "max_tokens_respuesta",
            )
            if "knowledge_engrams" in tables:
                engram_columns = {str(c.get("name") or "") for c in inspector.get_columns("knowledge_engrams")}
                for col in _ENGRAM_DEAD_COLUMNS:
                    if col in engram_columns:
                        statements.append(f"ALTER TABLE knowledge_engrams DROP COLUMN {col}")
                if "raw_mode" not in engram_columns:
                    statements.append("ALTER TABLE knowledge_engrams ADD COLUMN raw_mode BOOLEAN NOT NULL DEFAULT FALSE")

            if not statements:
                return

            with self.engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
        except Exception as exc:
            # Keep app startup resilient and surface actionable diagnostics.
            print(f"[DATABASE] Legacy compatibility migration skipped: {exc}")

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def build_database_manager(app_settings: AppSettings) -> DatabaseManager:
    database_settings = load_database_settings(app_settings)
    engine_options: dict[str, object] = {"echo": database_settings.echo}

    if database_settings.is_sqlite:
        engine_options["connect_args"] = {"check_same_thread": False}
    else:
        engine_options["pool_size"] = database_settings.pool_size
        engine_options["max_overflow"] = database_settings.max_overflow
        engine_options["pool_timeout"] = database_settings.pool_timeout
        engine_options["pool_pre_ping"] = True

    engine = create_engine(database_settings.url, **engine_options)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return DatabaseManager(
        settings=database_settings,
        engine=engine,
        session_factory=session_factory,
    )