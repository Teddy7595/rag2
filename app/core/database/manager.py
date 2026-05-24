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
            if "interaction_messages" not in tables:
                return

            columns = {str(column.get("name") or "") for column in inspector.get_columns("interaction_messages")}
            statements: list[str] = []

            if "session_id" not in columns:
                statements.append("ALTER TABLE interaction_messages ADD COLUMN session_id VARCHAR(64)")

            if "knowledge_entries" in tables:
                ke_columns = {str(c.get("name") or "") for c in inspector.get_columns("knowledge_entries")}
                if "engram_id" not in ke_columns:
                    statements.append("ALTER TABLE knowledge_entries ADD COLUMN engram_id VARCHAR(36)")

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